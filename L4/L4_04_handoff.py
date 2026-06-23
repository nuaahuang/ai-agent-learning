import asyncio
from typing import Dict, List, Optional, Any, Callable
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

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    HANDOFF = "handoff"
    FAILED = "failed"

class AgentCapability(Enum):
    GENERAL = "general"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    SUMMARIZATION = "summarization"
    FINANCE = "finance"
    TECHNICAL = "technical"
    CREATIVE = "creative"

@dataclass
class Task:
    id: str
    title: str
    description: str
    status: TaskStatus
    assignee: Optional[str] = None
    previous_assignee: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, str]] = field(default_factory=list)
    priority: int = 1
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assignee": self.assignee,
            "priority": self.priority,
            "created_at": self.created_at
        }

@dataclass
class HandoffRequest:
    task_id: str
    from_agent: str
    to_agent: str
    reason: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.client = httpx.AsyncClient(timeout=30)
    
    def create_task(self, title: str, description: str, priority: int = 1) -> Task:
        task = Task(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority
        )
        self.tasks[task.id] = task
        print(f"📋 创建任务: {task.id} - {title}")
        return task
    
    def assign_task(self, task_id: str, agent_id: str) -> bool:
        if task_id in self.tasks:
            self.tasks[task_id].assignee = agent_id
            self.tasks[task_id].status = TaskStatus.IN_PROGRESS
            self.tasks[task_id].updated_at = datetime.now().timestamp()
            print(f"👤 任务 {task_id} 已分配给 {agent_id}")
            return True
        return False
    
    async def handoff_task(self, task_id: str, from_agent: str, to_agent: str, reason: str, context: Dict = None):
        if task_id not in self.tasks:
            print(f"⚠️ 任务不存在: {task_id}")
            return False
        
        task = self.tasks[task_id]
        task.previous_assignee = task.assignee
        task.assignee = to_agent
        task.status = TaskStatus.HANDOFF
        task.updated_at = datetime.now().timestamp()
        
        if context:
            task.context.update(context)
        
        task.history.append({
            "action": "handoff",
            "from": from_agent,
            "to": to_agent,
            "reason": reason,
            "timestamp": datetime.now().timestamp()
        })
        
        print(f"🔄 任务交接: {from_agent} → {to_agent} (原因: {reason})")
        return True
    
    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)
    
    def update_task_status(self, task_id: str, status: TaskStatus):
        if task_id in self.tasks:
            self.tasks[task_id].status = status
            self.tasks[task_id].updated_at = datetime.now().timestamp()
    
    def get_tasks_by_assignee(self, agent_id: str) -> List[Task]:
        return [t for t in self.tasks.values() if t.assignee == agent_id]
    
    async def close(self):
        await self.client.aclose()

class HandoffAgent:
    def __init__(self, agent_id: str, name: str, capabilities: List[AgentCapability], task_manager: TaskManager):
        self.agent_id = agent_id
        self.name = name
        self.capabilities = capabilities
        self.task_manager = task_manager
    
    def can_handle(self, task: Task) -> bool:
        context = task.context
        for cap in self.capabilities:
            if cap.value.lower() in task.title.lower() or cap.value.lower() in task.description.lower():
                return True
            if "domain" in context and context["domain"] == cap.value:
                return True
        return False
    
    def get_capability_score(self, task: Task) -> float:
        score = 0.0
        for cap in self.capabilities:
            if cap.value.lower() in task.title.lower():
                score += 0.3
            if cap.value.lower() in task.description.lower():
                score += 0.3
            if "domain" in task.context and task.context["domain"] == cap.value:
                score += 0.4
        return min(score, 1.0)
    
    async def process_task(self, task: Task):
        print(f"\n🚀 [{self.name}] 开始处理任务: {task.title}")
        print(f"📝 描述: {task.description}")
        
        system_prompt = "你是一个专业的任务处理助手。请分析任务并提供处理方案。"
        response = await self._call_ai(f"任务: {task.title}\n描述: {task.description}\n请提供处理方案", system_prompt)
        
        print(f"💡 [{self.name}] 处理结果: {response[:50]}...")
        
        task.context["processed_by"] = self.agent_id
        task.context["processing_result"] = response
        
        return response
    
    async def decide_handoff(self, task: Task, available_agents: List['HandoffAgent']) -> Optional[str]:
        other_agents = [a for a in available_agents if a.agent_id != self.agent_id]
        
        if not other_agents:
            return None, None
        
        system_prompt = "你是一个任务分配专家。请判断当前任务是否需要交接给其他专家处理。"
        prompt = f"""
        当前任务: {task.title}
        当前处理者: {self.name}
        我的能力: {[c.value for c in self.capabilities]}
        
        其他可用专家:
        {chr(10).join([f"- {a.name}: {[c.value for c in a.capabilities]}" for a in other_agents])}
        
        是否需要交接？如果需要，请选择最合适的专家。
        回答格式: 需要交接给 [专家名称]，原因：[原因]
        或者: 不需要交接，我可以处理。
        """
        
        response = await self._call_ai(prompt, system_prompt)
        
        if "需要交接给" in response:
            for agent in other_agents:
                if agent.name in response:
                    reason = response.split("原因：")[-1] if "原因：" in response else "需要专业处理"
                    return agent.agent_id, reason
        
        return None, None
    
    async def handoff_async(self, task: Task, to_agent: 'HandoffAgent', reason: str, 
                          callback: Optional[Callable] = None) -> Dict[str, Any]:
        """异步交接：不等待目标 Agent 完成，立即返回"""
        print(f"\n🔄 [{self.name}] 发起异步交接 → [{to_agent.name}]")
        
        # 1. 记录交接
        await self.task_manager.handoff_task(task.id, self.agent_id, to_agent.agent_id, reason)
        
        # 2. 创建后台任务处理
        asyncio.create_task(self._process_async(to_agent, task, callback))
        
        # 3. 立即返回
        return {
            "status": "handoff_initiated",
            "task_id": task.id,
            "from_agent": self.name,
            "to_agent": to_agent.name,
            "reason": reason
        }
    
    async def _process_async(self, next_agent: 'HandoffAgent', task: Task, 
                            callback: Optional[Callable]):
        """后台处理任务"""
        try:
            print(f"\n⏳ [{next_agent.name}] 后台开始处理...")
            await next_agent.process_task(task)
            self.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
            print(f"\n✅ [{next_agent.name}] 后台处理完成")
            
            # 执行回调
            if callback:
                result = callback(task, next_agent)
                if asyncio.iscoroutine(result):
                    await result
                    
        except Exception as e:
            print(f"\n❌ [{next_agent.name}] 后台处理失败: {e}")
            self.task_manager.update_task_status(task.id, TaskStatus.FAILED)
    
    async def handoff_with_await(self, task: Task, to_agent: 'HandoffAgent', reason: str) -> Task:
        """同步交接：等待目标 Agent 完成"""
        print(f"\n🔄 [{self.name}] 发起同步交接 → [{to_agent.name}]")
        
        # 1. 记录交接
        await self.task_manager.handoff_task(task.id, self.agent_id, to_agent.agent_id, reason)
        
        # 2. 等待目标 Agent 完成
        await to_agent.process_task(task)
        
        # 3. 更新状态
        self.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
        
        return task
    
    async def _call_ai(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self.task_manager.client.post(
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
            return "AI服务不可用"

async def main():
    print("="*80)
    print("🏫 L4-04: Hand-off（交接机制）")
    print("="*80)
    
    task_manager = TaskManager()
    
    general_agent = HandoffAgent(
        "agent_general",
        "通用助手",
        [AgentCapability.GENERAL],
        task_manager
    )
    
    finance_agent = HandoffAgent(
        "agent_finance",
        "财务专家",
        [AgentCapability.FINANCE, AgentCapability.ANALYSIS],
        task_manager
    )
    
    tech_agent = HandoffAgent(
        "agent_tech",
        "技术专家",
        [AgentCapability.TECHNICAL, AgentCapability.EXECUTION],
        task_manager
    )
    
    agents = [general_agent, finance_agent, tech_agent]
    
    print(f"\n🤖 可用 Agent:")
    for agent in agents:
        print(f"  - {agent.name}: {[c.value for c in agent.capabilities]}")
    
    print("\n" + "="*80)
    print("🔄 演示1: 同步交接")
    print("="*80)
    
    task1 = task_manager.create_task(
        "财务报表分析",
        "分析2024年Q1财务报表，计算利润率和增长率",
        priority=2
    )
    
    task_manager.assign_task(task1.id, general_agent.agent_id)
    await general_agent.process_task(task1)
    
    target_agent_id, reason = await general_agent.decide_handoff(task1, agents)
    if target_agent_id:
        target_agent = next(a for a in agents if a.agent_id == target_agent_id)
        await general_agent.handoff_with_await(task1, target_agent, reason)
    
    print("\n" + "="*80)
    print("🔄 演示2: 异步交接")
    print("="*80)
    
    task2 = task_manager.create_task(
        "系统架构设计",
        "设计一个分布式微服务架构系统",
        priority=1
    )
    
    task_manager.assign_task(task2.id, general_agent.agent_id)
    await general_agent.process_task(task2)
    
    target_agent_id, reason = await general_agent.decide_handoff(task2, agents)
    if target_agent_id:
        target_agent = next(a for a in agents if a.agent_id == target_agent_id)
        
        # 异步交接：不等待，立即返回
        print(f"\n📤 发起异步交接...")
        result = await general_agent.handoff_async(task2, target_agent, reason, 
                                                   callback=lambda t, a: print(f"📬 回调通知: 任务由 {a.name} 完成"))
        
        print(f"📋 立即返回结果: {result}")
        print(f"⏩ 主流程继续执行，不等待后台任务完成...")
    
    # 等待一段时间，让后台任务完成
    print(f"\n⏳ 等待后台任务完成...")
    await asyncio.sleep(5)
    
    print("\n" + "="*80)
    print("📊 最终任务状态")
    print("="*80)
    for task in task_manager.tasks.values():
        print(f"\n任务: {task.title}")
        print(f"状态: {task.status.value}")
        print(f"当前负责人: {task.assignee}")
        print(f"历史记录: {len(task.history)} 条")
        for h in task.history:
            print(f"  - {h}")
    
    await task_manager.close()
    
    print("\n" + "="*80)
    print("✅ Hand-off 机制演示完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())