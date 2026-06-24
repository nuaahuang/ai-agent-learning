import asyncio
import time
import hashlib
import json
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict, defaultdict
import numpy as np


@dataclass
class CacheEntry:
    question: str
    embedding: List[float]
    answer: str
    usage: Dict[str, int]
    timestamp: float
    hit_count: int = 0
    ttl: int = 3600
    
    @property
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


class SemanticCache:
    def __init__(
        self,
        similarity_threshold: float = 0.8,
        max_entries: int = 1000,
        ttl: int = 3600,
        strategy: str = "lru"
    ):
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self.ttl = ttl
        self.strategy = strategy
        
        self._entries: Dict[str, CacheEntry] = {}
        self._embeddings: List[Tuple[str, List[float]]] = []
        self._lru_order = OrderedDict()
    
    def _compute_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = (sum(a * a for a in vec1)) ** 0.5
        norm2 = (sum(b * b for b in vec2)) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)
    
    def _generate_key(self, question: str) -> str:
        return hashlib.md5(question.lower().strip().encode()).hexdigest()
    
    def _compute_embedding(self, text: str) -> List[float]:
        if len(text) == 0:
            return [0.0] * 384
        
        text = text.lower().strip()
        features = defaultdict(float)
        
        for i in range(len(text) - 1):
            bigram = text[i:i+2]
            features[bigram] += 1.0
        
        for i in range(len(text) - 2):
            trigram = text[i:i+3]
            features[trigram] += 1.0
        
        keywords = ["人工智能", "ai", "机器学习", "深度学习", "python", "编程", "区别", "定义", "概念", "解释"]
        for kw in keywords:
            if kw in text:
                features[kw] += 5.0
        
        embedding = np.zeros(384)
        for i, (feature, weight) in enumerate(sorted(features.items())[:384]):
            embedding[i] = weight
        
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding.tolist()
        return (embedding / norm).tolist()
    
    def _evict(self):
        if len(self._entries) < self.max_entries:
            return
        
        if self.strategy == "lru":
            oldest_key = next(iter(self._lru_order))
            self._remove_entry(oldest_key)
        elif self.strategy == "fifo":
            oldest_key = min(
                self._entries.keys(),
                key=lambda k: self._entries[k].timestamp
            )
            self._remove_entry(oldest_key)
        elif self.strategy == "lfu":
            least_freq_key = min(
                self._entries.keys(),
                key=lambda k: self._entries[k].hit_count
            )
            self._remove_entry(least_freq_key)
    
    def _remove_entry(self, key: str):
        if key in self._entries:
            del self._entries[key]
            if key in self._lru_order:
                del self._lru_order[key]
            self._embeddings = [(k, e) for k, e in self._embeddings if k != key]
    
    def _update_lru(self, key: str):
        if key in self._lru_order:
            del self._lru_order[key]
        self._lru_order[key] = time.time()
    
    def lookup(self, question: str) -> Optional[CacheEntry]:
        question = question.strip()
        exact_key = self._generate_key(question)
        
        if exact_key in self._entries:
            entry = self._entries[exact_key]
            if not entry.is_expired:
                entry.hit_count += 1
                self._update_lru(exact_key)
                return entry
            else:
                self._remove_entry(exact_key)
        
        question_embedding = self._compute_embedding(question)
        
        best_match = None
        best_similarity = 0.0
        
        for key, embedding in self._embeddings:
            if key in self._entries:
                entry = self._entries[key]
                if entry.is_expired:
                    self._remove_entry(key)
                    continue
                
                similarity = self._compute_cosine_similarity(question_embedding, embedding)
                if similarity > best_similarity and similarity >= self.similarity_threshold:
                    best_similarity = similarity
                    best_match = key
        
        if best_match:
            entry = self._entries[best_match]
            entry.hit_count += 1
            self._update_lru(best_match)
            return entry
        
        return None
    
    def store(self, question: str, answer: str, usage: Dict[str, int] = None):
        question = question.strip()
        key = self._generate_key(question)
        
        if key in self._entries:
            entry = self._entries[key]
            entry.answer = answer
            entry.usage = usage or {}
            entry.timestamp = time.time()
            entry.hit_count += 1
            self._update_lru(key)
            return
        
        self._evict()
        
        embedding = self._compute_embedding(question)
        entry = CacheEntry(
            question=question,
            embedding=embedding,
            answer=answer,
            usage=usage or {},
            timestamp=time.time(),
            ttl=self.ttl
        )
        
        self._entries[key] = entry
        self._embeddings.append((key, embedding))
        self._update_lru(key)
    
    def get_stats(self) -> Dict[str, Any]:
        total_entries = len(self._entries)
        expired_entries = sum(1 for e in self._entries.values() if e.is_expired)
        total_hits = sum(e.hit_count for e in self._entries.values())
        
        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "total_hits": total_hits,
            "average_hits_per_entry": total_hits / max(total_entries, 1),
            "cache_size_bytes": sum(len(e.question) + len(e.answer) for e in self._entries.values()) * 2
        }
    
    def clear_expired(self):
        expired_keys = [k for k, e in self._entries.items() if e.is_expired]
        for key in expired_keys:
            self._remove_entry(key)
        return len(expired_keys)


class SemanticCacheLLMClient:
    def __init__(self, cache: SemanticCache):
        self.cache = cache
        self._total_requests = 0
        self._cache_hits = 0
    
    async def call_llm(self, messages: list, **kwargs) -> Dict[str, Any]:
        question = messages[-1]["content"] if messages else ""
        self._total_requests += 1
        
        cached_entry = self.cache.lookup(question)
        if cached_entry:
            self._cache_hits += 1
            return {
                "content": cached_entry.answer,
                "usage": cached_entry.usage,
                "cached": True
            }
        
        await asyncio.sleep(0.1)
        
        answer = f"这是关于'{question[:30]}...'的详细回答"
        usage = {"prompt_tokens": len(question) // 4, "completion_tokens": 150}
        
        self.cache.store(question, answer, usage)
        
        return {
            "content": answer,
            "usage": usage,
            "cached": False
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        cache_stats = self.cache.get_stats()
        hit_rate = self._cache_hits / max(self._total_requests, 1) * 100
        
        return {
            "total_requests": self._total_requests,
            "cache_hits": self._cache_hits,
            "hit_rate": hit_rate,
            **cache_stats
        }


async def test_semantic_cache():
    print("\n" + "-" * 60)
    print("🧠 语义缓存测试")
    print("-" * 60)
    
    cache = SemanticCache(similarity_threshold=0.7, max_entries=10)
    client = SemanticCacheLLMClient(cache)
    
    test_questions = [
        "什么是人工智能？",
        "AI是什么？",
        "什么是AI?",
        "请解释人工智能的概念",
        "机器学习和深度学习有什么区别？",
        "ML和DL的区别是什么？",
        "机器学习与深度学习的差异",
        "什么是Python?",
        "Python编程语言是什么?",
    ]
    
    print("测试语义缓存命中效果:\n")
    
    for i, question in enumerate(test_questions, 1):
        result = await client.call_llm([{"role": "user", "content": question}])
        status = "✅ 缓存命中" if result["cached"] else "🔄 LLM调用"
        print(f"{i:2d}. {question[:30]:<30} {status}")
    
    metrics = client.get_metrics()
    print(f"\n缓存统计:")
    print(f"  总请求: {metrics['total_requests']}")
    print(f"  缓存命中: {metrics['cache_hits']}")
    print(f"  命中率: {metrics['hit_rate']:.1f}%")
    print(f"  缓存条目数: {metrics['total_entries']}")


async def test_different_thresholds():
    print("\n" + "-" * 60)
    print("⚙️ 不同相似度阈值测试")
    print("-" * 60)
    
    thresholds = [0.5, 0.7, 0.9]
    
    for threshold in thresholds:
        cache = SemanticCache(similarity_threshold=threshold)
        client = SemanticCacheLLMClient(cache)
        
        questions = [
            "什么是人工智能？",
            "AI是什么？",
            "人工智能的定义是什么？",
            "机器学习是什么？",
        ]
        
        for question in questions:
            await client.call_llm([{"role": "user", "content": question}])
        
        metrics = client.get_metrics()
        print(f"阈值 {threshold}: 命中 {metrics['cache_hits']}/{metrics['total_requests']} ({metrics['hit_rate']:.1f}%)")


async def test_eviction_strategy():
    print("\n" + "-" * 60)
    print("🔄 缓存淘汰策略测试")
    print("-" * 60)
    
    strategies = ["lru", "fifo", "lfu"]
    
    for strategy in strategies:
        cache = SemanticCache(max_entries=3, strategy=strategy)
        
        questions = ["Q1", "Q2", "Q3", "Q4", "Q5"]
        
        for q in questions:
            await asyncio.sleep(0.01)
            cache.store(q, f"Answer for {q}", {})
        
        cache.lookup("Q1")
        cache.lookup("Q1")
        cache.lookup("Q2")
        
        q1_entry = cache._entries.get('Q1')
        q1_hits = q1_entry.hit_count if q1_entry else 0
        print(f"策略 {strategy}: 剩余 {len(cache._entries)} 条，命中最多的是 Q1({q1_hits}次)")


async def main():
    print("=" * 80)
    print("🧠 L6-03: Semantic Cache（语义缓存）")
    print("=" * 80)
    
    await test_semantic_cache()
    await test_different_thresholds()
    await test_eviction_strategy()
    
    print("\n" + "=" * 80)
    print("✅ Semantic Cache 演示完成")
    print("=" * 80)
    
    print("""
💡 核心功能:
   - 基于语义相似性匹配（余弦相似度）
   - 支持精确匹配和语义匹配两种模式
   - 三种缓存淘汰策略: LRU、FIFO、LFU
   - 可配置相似度阈值
   - 自动TTL过期清理
   - 命中统计和性能指标
""")


if __name__ == "__main__":
    asyncio.run(main())