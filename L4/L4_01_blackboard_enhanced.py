import asyncio
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")

class BlackboardEntryType(Enum):
    FACT = "fact"
    HYPOTHESIS = "hypothesis"
    PLAN = "plan"
    RESULT = "result"
    QUESTION = "question"
    ACTION = "action"

@dataclass
class BlackboardEntry:
    id: str
    content: str
    entry_type: BlackboardEntryType
    author: str
    timestamp: float
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    references: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "entry_type": self.entry_type.value,
            "author": self.author,
            "timestamp": self.timestamp,
            "priority": self.priority,
            "tags": self.tags,
            "confidence": self.confidence,
            "references": self.references
        }

class Blackboard:
    def __init__(self):
        self.entries: Dict[str, BlackboardEntry] = {}
        self.subscribers: List[Callable] = []
        self.lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=30)
    
    async def add_entry(self, content: str, entry_type: BlackboardEntryType, 
                       author: str, priority: int = 0, tags: List[str] = None,
                       confidence: float = 1.0) -> str:
        async with self.lock:
            entry_id = str(uuid.uuid4())[:8]
            entry = BlackboardEntry(
                id=entry_id,
                content=content,
                entry_type=entry_type,
                author=author,
                timestamp=datetime.now().timestamp(),
                priority=priority,
                tags=tags or [],
                confidence=confidence
            )
            self.entries[entry_id] = entry
            await self._notify_subscribers("add", entry)
            return entry_id
    
    async def update_entry(self, entry_id: str, **kwargs):
        async with self.lock:
            if entry_id not in self.entries:
                raise ValueError(f"Entry {entry_id} not found")
            entry = self.entries[entry_id]
            if 'content' in kwargs:
                entry.content = kwargs['content']
            if 'priority' in kwargs:
                entry.priority = kwargs['priority']
            if 'confidence' in kwargs:
                entry.confidence = kwargs['confidence']
            if 'tags' in kwargs:
                entry.tags = kwargs['tags']
            await self._notify_subscribers("update", entry)
    
    async def remove_entry(self, entry_id: str):
        async with self.lock:
            if entry_id not in self.entries:
                raise ValueError(f"Entry {entry_id} not found")
            entry = self.entries.pop(entry_id)
            await self._notify_subscribers("remove", entry)
    
    def get_entries_by_type(self, entry_type: BlackboardEntryType) -> List[BlackboardEntry]:
        return [e for e in self.entries.values() if e.entry_type == entry_type]
    
    def get_entries_by_author(self, author: str) -> List[BlackboardEntry]:
        return [e for e in self.entries.values() if e.author == author]
    
    def get_entries_by_tag(self, tag: str) -> List[BlackboardEntry]:
        return [e for e in self.entries.values() if tag in e.tags]
    
    def get_all_entries(self) -> List[BlackboardEntry]:
        return sorted(self.entries.values(), key=lambda x: (-x.priority, -x.timestamp))
    
    def subscribe(self, callback: Callable):
        self.subscribers.append(callback)
    
    async def _notify_subscribers(self, action: str, entry: BlackboardEntry):
        for callback in self.subscribers:
            try:
                await callback(action, entry)
            except Exception as e:
                print(f"❌ 订阅者回调失败: {e}")
    
    def clear(self):
        self.entries.clear()
    
    def get_context(self) -> str:
        entries = self.get_all_entries()
        if not entries:
            return "黑板为空"
        context = "当前黑板内容:\n"
        for entry in entries[:5]:
            context += f"- [{entry.entry_type.value}] {entry.content[:50]}... (作者: {entry.author})\n"
        if len(entries) > 5:
            context += f"... 还有 {len(entries) - 5} 条更多内容"
        return context
    
    async def call_ai(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"⚠️ AI调用失败: {e}")
            return "AI服务不可用，使用默认逻辑"
    
    def __repr__(self):
        return f"Blackboard(entries={len(self.entries)})"

class AgentRole(Enum):
    ANALYZER = "analyzer"
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    SUMMARIZER = "summarizer"

class BlackboardAgent:
    def __init__(self, name: str, role: AgentRole, blackboard: Blackboard):
        self.name = name
        self.role = role
        self.blackboard = blackboard
        self.blackboard.subscribe(self._on_blackboard_update)
        self.should_run = False
    
    async def _on_blackboard_update(self, action: str, entry: BlackboardEntry):
        print(f"🔔 [{self.name}] 收到黑板更新: {action} - {entry.entry_type.value}")
        
        if action == "add":
            if entry.entry_type == BlackboardEntryType.FACT and self.role == AgentRole.PLANNER:
                print(f"✨ [{self.name}] 检测到新事实，准备制定计划")
                self.should_run = True
            
            elif entry.entry_type == BlackboardEntryType.PLAN and self.role == AgentRole.EXECUTOR:
                print(f"✨ [{self.name}] 检测到新计划，准备执行")
                self.should_run = True
            
            elif entry.entry_type == BlackboardEntryType.RESULT and self.role == AgentRole.VERIFIER:
                print(f"✨ [{self.name}] 检测到新结果，准备验证")
                self.should_run = True
            
            elif entry.entry_type == BlackboardEntryType.FACT and self.role == AgentRole.SUMMARIZER:
                facts = self.blackboard.get_entries_by_type(BlackboardEntryType.FACT)
                results = self.blackboard.get_entries_by_type(BlackboardEntryType.RESULT)
                if len(facts) >= 2 and len(results) >= 1:
                    print(f"✨ [{self.name}] 信息充足，准备总结")
                    self.should_run = True
    
    async def analyze(self, question: str):
        if self.role != AgentRole.ANALYZER:
            return
        
        system_prompt = "你是一个问题分析专家。请分析给定问题，识别关键要素和需要的信息。"
        prompt = f"""请分析以下问题：
问题: {question}

请输出：
1. 问题的核心目标
2. 需要收集的关键信息
3. 可能的解决步骤

输出格式清晰，使用中文。"""
        
        analysis = await self.blackboard.call_ai(prompt, system_prompt)
        
        await self.blackboard.add_entry(
            analysis,
            BlackboardEntryType.FACT,
            author=self.name,
            priority=5,
            tags=["analysis", "question"]
        )
        print(f"📊 [{self.name}] 完成问题分析")
    
    async def plan(self):
        if self.role != AgentRole.PLANNER:
            return
        
        facts = self.blackboard.get_entries_by_type(BlackboardEntryType.FACT)
        if not facts:
            await self.blackboard.add_entry(
                "暂无足够信息制定计划，请先收集事实",
                BlackboardEntryType.QUESTION,
                author=self.name,
                priority=3
            )
            return
        
        facts_text = "\n".join([f"- {f.content[:100]}..." for f in facts])
        
        system_prompt = "你是一个计划制定专家。基于给定事实制定详细执行计划。"
        prompt = f"""基于以下事实制定执行计划：

事实：
{facts_text}

请输出详细的执行计划，包括：
1. 具体步骤
2. 预期结果
3. 成功标准

使用中文输出。"""
        
        plan = await self.blackboard.call_ai(prompt, system_prompt)
        
        await self.blackboard.add_entry(
            plan,
            BlackboardEntryType.PLAN,
            author=self.name,
            priority=10,
            tags=["plan", "action"]
        )
        print(f"📝 [{self.name}] 制定执行计划")
    
    async def execute(self):
        if self.role != AgentRole.EXECUTOR:
            return
        
        plans = self.blackboard.get_entries_by_type(BlackboardEntryType.PLAN)
        if not plans:
            await self.blackboard.add_entry(
                "暂无执行计划，请先制定计划",
                BlackboardEntryType.QUESTION,
                author=self.name,
                priority=3
            )
            return
        
        latest_plan = plans[-1]
        
        system_prompt = "你是一个任务执行专家。模拟执行计划并返回结果。"
        prompt = f"""执行以下计划：

计划：
{latest_plan.content}

请模拟执行此计划，并输出：
1. 执行步骤
2. 执行结果
3. 遇到的问题（如有）

使用中文输出。"""
        
        result = await self.blackboard.call_ai(prompt, system_prompt)
        
        await self.blackboard.add_entry(
            result,
            BlackboardEntryType.RESULT,
            author=self.name,
            priority=8,
            tags=["result", "execution"]
        )
        print(f"⚡ [{self.name}] 执行任务完成")
    
    async def verify(self):
        if self.role != AgentRole.VERIFIER:
            return
        
        results = self.blackboard.get_entries_by_type(BlackboardEntryType.RESULT)
        if not results:
            return
        
        latest_result = results[-1]
        plans = self.blackboard.get_entries_by_type(BlackboardEntryType.PLAN)
        plan_text = plans[-1].content if plans else "无计划"
        
        system_prompt = "你是一个结果验证专家。验证执行结果是否符合计划要求。"
        prompt = f"""验证以下执行结果：

计划：
{plan_text}

执行结果：
{latest_result.content}

请输出：
1. 结果是否符合计划
2. 验证置信度（0-100%）
3. 改进建议（如有）

使用中文输出。"""
        
        verification = await self.blackboard.call_ai(prompt, system_prompt)
        
        await self.blackboard.add_entry(
            verification,
            BlackboardEntryType.FACT,
            author=self.name,
            priority=7,
            tags=["verification", "fact"]
        )
        print(f"✅ [{self.name}] 验证完成")
    
    async def summarize(self):
        if self.role != AgentRole.SUMMARIZER:
            return
        
        entries = self.blackboard.get_all_entries()
        if not entries:
            return
        
        entries_text = "\n".join([f"- [{e.entry_type.value}] {e.content[:80]}..." for e in entries])
        
        system_prompt = "你是一个总结专家。请对整个任务进行总结。"
        prompt = f"""请总结以下任务过程：

任务记录：
{entries_text}

请输出：
1. 问题描述
2. 解决步骤
3. 最终结果
4. 关键发现

使用中文输出。"""
        
        summary = await self.blackboard.call_ai(prompt, system_prompt)
        
        await self.blackboard.add_entry(
            summary,
            BlackboardEntryType.RESULT,
            author=self.name,
            priority=15,
            tags=["summary", "final"]
        )
        print(f"📌 [{self.name}] 生成总结")
    
    async def run(self, task: str = None):
        print(f"\n🚀 [{self.name}] 开始执行，角色: {self.role.value}")
        
        if self.role == AgentRole.ANALYZER and task:
            await self.analyze(task)
        elif self.role == AgentRole.PLANNER:
            if not self.should_run:
                print(f"⏭️ [{self.name}] 未检测到触发条件，跳过")
                return
            await self.plan()
            self.should_run = False
        elif self.role == AgentRole.EXECUTOR:
            if not self.should_run:
                print(f"⏭️ [{self.name}] 未检测到触发条件，跳过")
                return
            await self.execute()
            self.should_run = False
        elif self.role == AgentRole.VERIFIER:
            if not self.should_run:
                print(f"⏭️ [{self.name}] 未检测到触发条件，跳过")
                return
            await self.verify()
            self.should_run = False
        elif self.role == AgentRole.SUMMARIZER:
            if not self.should_run:
                print(f"⏭️ [{self.name}] 未检测到触发条件，跳过")
                return
            await self.summarize()
            self.should_run = False

async def main():
    print("="*80)
    print("🏫 L4-01: Blackboard（黑板模式）增强版")
    print("="*80)
    
    blackboard = Blackboard()
    print(f"📋 创建黑板: {blackboard}")
    
    analyzer = BlackboardAgent("分析员-AI", AgentRole.ANALYZER, blackboard)
    planner = BlackboardAgent("规划师-AI", AgentRole.PLANNER, blackboard)
    executor = BlackboardAgent("执行者-AI", AgentRole.EXECUTOR, blackboard)
    verifier = BlackboardAgent("验证者-AI", AgentRole.VERIFIER, blackboard)
    summarizer = BlackboardAgent("总结者-AI", AgentRole.SUMMARIZER, blackboard)
    
    task = "分析地球和月球的体积差异，并计算地球体积是月球体积的几倍"
    
    print(f"\n🎯 任务: {task}")
    print("-"*60)
    
    await analyzer.run(task)
    await asyncio.sleep(1)
    
    await planner.run()
    await asyncio.sleep(1)
    
    await executor.run()
    await asyncio.sleep(1)
    
    await verifier.run()
    await asyncio.sleep(1)
    
    await summarizer.run()
    
    print("\n" + "="*80)
    print("📊 黑板最终状态")
    print("="*80)
    
    for entry in blackboard.get_all_entries():
        print(f"\n[{entry.id}] [{entry.entry_type.value}] (优先级:{entry.priority})")
        print(f"作者: {entry.author}")
        print(f"内容:\n{entry.content}")
        print(f"标签: {entry.tags}")
    
    print("\n" + "="*80)
    print("✅ 黑板模式增强版演示完成")
    print("="*80)
    
    await blackboard.client.aclose()

if __name__ == "__main__":
    asyncio.run(main())