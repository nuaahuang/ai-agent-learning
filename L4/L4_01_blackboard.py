import asyncio
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid

class BlackboardEntryType(Enum):
    """黑板条目类型"""
    FACT = "fact"           # 事实信息
    HYPOTHESIS = "hypothesis" # 假设
    PLAN = "plan"           # 计划
    RESULT = "result"       # 结果
    QUESTION = "question"   # 问题
    ACTION = "action"       # 行动建议

@dataclass
class BlackboardEntry:
    """黑板条目"""
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
    """黑板 - 多 Agent 共享的知识中心"""
    
    def __init__(self):
        self.entries: Dict[str, BlackboardEntry] = {}
        self.subscribers: List[Callable] = []
        self.lock = asyncio.Lock()
    
    async def add_entry(self, content: str, entry_type: BlackboardEntryType, 
                       author: str, priority: int = 0, tags: List[str] = None,
                       confidence: float = 1.0) -> str:
        """添加条目到黑板"""
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
        """更新黑板条目"""
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
        """移除黑板条目"""
        async with self.lock:
            if entry_id not in self.entries:
                raise ValueError(f"Entry {entry_id} not found")
            
            entry = self.entries.pop(entry_id)
            await self._notify_subscribers("remove", entry)
    
    def get_entries_by_type(self, entry_type: BlackboardEntryType) -> List[BlackboardEntry]:
        """按类型获取条目"""
        return [e for e in self.entries.values() if e.entry_type == entry_type]
    
    def get_entries_by_author(self, author: str) -> List[BlackboardEntry]:
        """按作者获取条目"""
        return [e for e in self.entries.values() if e.author == author]
    
    def get_entries_by_tag(self, tag: str) -> List[BlackboardEntry]:
        """按标签获取条目"""
        return [e for e in self.entries.values() if tag in e.tags]
    
    def get_all_entries(self) -> List[BlackboardEntry]:
        """获取所有条目，按优先级排序"""
        return sorted(self.entries.values(), key=lambda x: (-x.priority, -x.timestamp))
    
    def subscribe(self, callback: Callable):
        """订阅黑板变化"""
        self.subscribers.append(callback)
    
    async def _notify_subscribers(self, action: str, entry: BlackboardEntry):
        """通知所有订阅者"""
        for callback in self.subscribers:
            try:
                await callback(action, entry)
            except:
                pass
    
    def clear(self):
        """清空黑板"""
        self.entries.clear()
    
    def __repr__(self):
        return f"Blackboard(entries={len(self.entries)})"

class AgentRole(Enum):
    """Agent 角色"""
    ANALYZER = "analyzer"       # 分析员
    PLANNER = "planner"         # 规划师
    EXECUTOR = "executor"       # 执行者
    VERIFIER = "verifier"       # 验证者
    SUMMARIZER = "summarizer"   # 总结者

class BlackboardAgent:
    """基于黑板的 Agent"""
    
    def __init__(self, name: str, role: AgentRole, blackboard: Blackboard):
        self.name = name
        self.role = role
        self.blackboard = blackboard
        self.blackboard.subscribe(self._on_blackboard_update)
    
    async def _on_blackboard_update(self, action: str, entry: BlackboardEntry):
        """黑板更新回调"""
        print(f"🔔 [{self.name}] 收到黑板更新: {action} - {entry.entry_type.value}: {entry.content[:30]}...")
    
    async def analyze(self, question: str):
        """分析问题（分析员角色）"""
        if self.role != AgentRole.ANALYZER:
            return
        
        analysis = f"问题分析: {question}\n关键要素: 1) 明确问题目标 2) 收集相关信息 3) 制定解决方案"
        await self.blackboard.add_entry(
            analysis,
            BlackboardEntryType.FACT,
            author=self.name,
            priority=5,
            tags=["analysis", "question"]
        )
        print(f"📊 [{self.name}] 完成问题分析")
    
    async def plan(self):
        """制定计划（规划师角色）"""
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
        
        plan = "执行计划:\n1. 从黑板收集所有相关事实\n2. 分析可行方案\n3. 选择最优方案\n4. 执行并验证"
        await self.blackboard.add_entry(
            plan,
            BlackboardEntryType.PLAN,
            author=self.name,
            priority=10,
            tags=["plan", "action"]
        )
        print(f"📝 [{self.name}] 制定执行计划")
    
    async def execute(self):
        """执行任务（执行者角色）"""
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
        
        result = f"执行结果: 已完成计划 '{plans[-1].content[:30]}...' 的执行"
        await self.blackboard.add_entry(
            result,
            BlackboardEntryType.RESULT,
            author=self.name,
            priority=8,
            tags=["result", "execution"]
        )
        print(f"⚡ [{self.name}] 执行任务完成")
    
    async def verify(self):
        """验证结果（验证者角色）"""
        if self.role != AgentRole.VERIFIER:
            return
        
        results = self.blackboard.get_entries_by_type(BlackboardEntryType.RESULT)
        if not results:
            return
        
        verification = f"验证结果: '{results[-1].content[:30]}...' 已通过验证，置信度: 0.95"
        await self.blackboard.add_entry(
            verification,
            BlackboardEntryType.FACT,
            author=self.name,
            priority=7,
            tags=["verification", "fact"]
        )
        print(f"✅ [{self.name}] 验证通过")
    
    async def summarize(self):
        """总结（总结者角色）"""
        if self.role != AgentRole.SUMMARIZER:
            return
        
        entries = self.blackboard.get_all_entries()
        if not entries:
            return
        
        summary = "📋 任务总结:\n"
        for entry in entries:
            summary += f"- [{entry.entry_type.value}] {entry.content[:50]}... (作者: {entry.author})\n"
        
        await self.blackboard.add_entry(
            summary,
            BlackboardEntryType.RESULT,
            author=self.name,
            priority=15,
            tags=["summary", "final"]
        )
        print(f"📌 [{self.name}] 生成总结")
    
    async def run(self, task: str = None):
        """执行 Agent 的主要逻辑"""
        print(f"\n🚀 [{self.name}] 开始执行，角色: {self.role.value}")
        
        if self.role == AgentRole.ANALYZER and task:
            await self.analyze(task)
        elif self.role == AgentRole.PLANNER:
            await self.plan()
        elif self.role == AgentRole.EXECUTOR:
            await self.execute()
        elif self.role == AgentRole.VERIFIER:
            await self.verify()
        elif self.role == AgentRole.SUMMARIZER:
            await self.summarize()

async def main():
    """黑板模式演示"""
    print("="*80)
    print("🏫 L4-01: Blackboard（黑板模式）演示")
    print("="*80)
    
    # 创建黑板
    blackboard = Blackboard()
    print(f"📋 创建黑板: {blackboard}")
    
    # 创建不同角色的 Agent
    analyzer = BlackboardAgent("分析员-AI", AgentRole.ANALYZER, blackboard)
    planner = BlackboardAgent("规划师-AI", AgentRole.PLANNER, blackboard)
    executor = BlackboardAgent("执行者-AI", AgentRole.EXECUTOR, blackboard)
    verifier = BlackboardAgent("验证者-AI", AgentRole.VERIFIER, blackboard)
    summarizer = BlackboardAgent("总结者-AI", AgentRole.SUMMARIZER, blackboard)
    
    # 定义任务
    task = "分析地球和月球的体积差异，并计算地球体积是月球体积的几倍"
    
    print(f"\n🎯 任务: {task}")
    print("-"*60)
    
    # 按顺序执行各 Agent
    await analyzer.run(task)
    await asyncio.sleep(0.5)
    
    await planner.run()
    await asyncio.sleep(0.5)
    
    await executor.run()
    await asyncio.sleep(0.5)
    
    await verifier.run()
    await asyncio.sleep(0.5)
    
    await summarizer.run()
    
    # 显示黑板最终状态
    print("\n" + "="*80)
    print("📊 黑板最终状态")
    print("="*80)
    
    for entry in blackboard.get_all_entries():
        print(f"\n[{entry.id}] [{entry.entry_type.value}] (优先级:{entry.priority})")
        print(f"作者: {entry.author}")
        print(f"内容: {entry.content}")
        print(f"标签: {entry.tags}")
    
    print("\n" + "="*80)
    print("✅ 黑板模式演示完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())