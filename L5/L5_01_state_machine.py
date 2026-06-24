from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable, List, Union
from dataclasses import dataclass
from enum import Enum
import asyncio
import uuid
from datetime import datetime


class AgentEventType(Enum):
    TASK_ASSIGN = "task_assign"
    TASK_START = "task_start"
    TASK_PAUSE = "task_pause"
    TASK_RESUME = "task_resume"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    TASK_CANCEL = "task_cancel"
    MESSAGE_RECEIVED = "message_received"
    TIMEOUT = "timeout"


@dataclass
class AgentEvent:
    type: AgentEventType
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
    source: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()


class AgentState(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        pass

    def on_exit(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        pass

    @abstractmethod
    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional['AgentState']:
        pass


class IdleState(AgentState):
    def get_name(self) -> str:
        return "idle"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "等待任务"
        agent.context['last_activity'] = datetime.now().timestamp()
        print(f"🤖 [{agent.agent_id}] 进入空闲状态")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_ASSIGN:
            agent.context['task'] = event.data
            return TaskAssignedState()
        elif event.type == AgentEventType.MESSAGE_RECEIVED:
            return ProcessingState()
        return None


class TaskAssignedState(AgentState):
    def get_name(self) -> str:
        return "task_assigned"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "任务已分配"
        task = agent.context.get('task', {})
        print(f"📋 [{agent.agent_id}] 任务已分配: {task.get('name', '未命名任务')}")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_START:
            return RunningState()
        elif event.type == AgentEventType.TASK_CANCEL:
            return CancelledState()
        return None


class RunningState(AgentState):
    def get_name(self) -> str:
        return "running"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "执行中"
        agent.context['start_time'] = datetime.now().timestamp()
        print(f"🚀 [{agent.agent_id}] 开始执行任务")
        asyncio.create_task(self._execute_task(agent))

    async def _execute_task(self, agent: 'StatefulAgent'):
        task = agent.context.get('task', {})
        duration = task.get('duration', 3)
        progress = 0
        
        while progress < 100 and agent.get_state_name() == "running":
            await asyncio.sleep(1)
            progress += 25
            agent.context['progress'] = progress
            print(f"⏳ [{agent.agent_id}] 任务进度: {progress}%")
        
        if agent.get_state_name() == "running":
            agent.send_event(AgentEvent(AgentEventType.TASK_COMPLETE))

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_PAUSE:
            return PausedState()
        elif event.type == AgentEventType.TASK_COMPLETE:
            return CompletedState()
        elif event.type == AgentEventType.TASK_ERROR:
            return ErrorState()
        elif event.type == AgentEventType.TASK_CANCEL:
            return CancelledState()
        elif event.type == AgentEventType.TIMEOUT:
            return ErrorState()
        return None


class PausedState(AgentState):
    def get_name(self) -> str:
        return "paused"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "已暂停"
        agent.context['pause_time'] = datetime.now().timestamp()
        print(f"⏸️ [{agent.agent_id}] 任务已暂停")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_RESUME:
            return RunningState()
        elif event.type == AgentEventType.TASK_CANCEL:
            return CancelledState()
        return None


class CompletedState(AgentState):
    def get_name(self) -> str:
        return "completed"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "已完成"
        agent.context['end_time'] = datetime.now().timestamp()
        start_time = agent.context.get('start_time')
        if start_time:
            duration = agent.context['end_time'] - start_time
            agent.context['duration'] = duration
        print(f"✅ [{agent.agent_id}] 任务完成，耗时: {duration:.2f}秒" if start_time else f"✅ [{agent.agent_id}] 任务完成")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_ASSIGN:
            agent.context['task'] = event.data
            return TaskAssignedState()
        return None


class ErrorState(AgentState):
    def get_name(self) -> str:
        return "error"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "执行错误"
        if event and event.data:
            agent.context['error'] = event.data.get('error', '未知错误')
        print(f"❌ [{agent.agent_id}] 任务执行错误: {agent.context.get('error', '未知错误')}")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_START:
            return RunningState()
        elif event.type == AgentEventType.TASK_CANCEL:
            return CancelledState()
        return None


class CancelledState(AgentState):
    def get_name(self) -> str:
        return "cancelled"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "已取消"
        print(f"🚫 [{agent.agent_id}] 任务已取消")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_ASSIGN:
            agent.context['task'] = event.data
            return TaskAssignedState()
        return None


class ProcessingState(AgentState):
    def get_name(self) -> str:
        return "processing"

    def on_enter(self, agent: 'StatefulAgent', event: Optional[AgentEvent] = None) -> None:
        agent.context['status'] = "处理中"
        print(f"🔄 [{agent.agent_id}] 正在处理消息")

    def handle_event(self, agent: 'StatefulAgent', event: AgentEvent) -> Optional[AgentState]:
        if event.type == AgentEventType.TASK_COMPLETE:
            return IdleState()
        return None


class AgentStateMachine:
    def __init__(self, agent: 'StatefulAgent', initial_state: AgentState):
        self.agent = agent
        self.current_state = initial_state
        self.context: Dict[str, Any] = {}
        self.state_history: List[AgentState] = []
        self.transition_listeners: List[Callable[['AgentState', 'AgentState', AgentEvent], None]] = []
        
        initial_state.on_enter(agent)
        self.state_history.append(initial_state)

    def add_transition_listener(self, listener: Callable[['AgentState', 'AgentState', AgentEvent], None]) -> None:
        self.transition_listeners.append(listener)

    def send_event(self, event: AgentEvent) -> bool:
        next_state = self.current_state.handle_event(self.agent, event)
        
        if next_state and next_state != self.current_state:
            self._transition(next_state, event)
            return True
        return False

    def _transition(self, next_state: AgentState, event: AgentEvent) -> None:
        previous_state = self.current_state
        
        previous_state.on_exit(self.agent, event)
        next_state.on_enter(self.agent, event)
        
        self.current_state = next_state
        self.state_history.append(next_state)
        
        for listener in self.transition_listeners:
            listener(previous_state, next_state, event)

    def get_state_name(self) -> str:
        return self.current_state.get_name()

    def get_history(self) -> List[str]:
        return [state.get_name() for state in self.state_history]


class StatefulAgent:
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.context: Dict[str, Any] = {
            'created_at': datetime.now().timestamp(),
            'agent_id': agent_id,
            'agent_name': name
        }
        self.state_machine = AgentStateMachine(self, IdleState())
        self.state_machine.add_transition_listener(self._on_state_change)

    def _on_state_change(self, from_state: AgentState, to_state: AgentState, event: AgentEvent):
        print(f"🔀 [{self.agent_id}] 状态转换: {from_state.get_name()} -> {to_state.get_name()} (事件: {event.type.value})")

    def send_event(self, event: AgentEvent):
        self.state_machine.send_event(event)

    def get_state_name(self) -> str:
        return self.state_machine.get_state_name()

    def get_context(self) -> Dict[str, Any]:
        return {**self.context, **self.state_machine.context}


class TaskAgent(StatefulAgent):
    def __init__(self, agent_id: str, name: str):
        super().__init__(agent_id, name)
    
    async def assign_task(self, task_name: str, duration: int = 3):
        task_data = {
            'name': task_name,
            'duration': duration,
            'assigned_at': datetime.now().timestamp()
        }
        self.send_event(AgentEvent(AgentEventType.TASK_ASSIGN, data=task_data))
    
    async def start_task(self):
        self.send_event(AgentEvent(AgentEventType.TASK_START))
    
    async def pause_task(self):
        self.send_event(AgentEvent(AgentEventType.TASK_PAUSE))
    
    async def resume_task(self):
        self.send_event(AgentEvent(AgentEventType.TASK_RESUME))
    
    async def cancel_task(self):
        self.send_event(AgentEvent(AgentEventType.TASK_CANCEL))


async def main():
    print("="*80)
    print("🏭 L5-01: 状态机 (State Machine) - Agent生命周期管理")
    print("="*80)
    
    agent = TaskAgent("task_agent_001", "任务执行Agent")
    
    print(f"\n🤖 创建Agent: {agent.name} ({agent.agent_id})")
    print(f"当前状态: {agent.get_state_name()}")
    print(f"上下文: {agent.get_context()}")
    
    print("\n" + "-"*60)
    print("步骤1: 分配任务")
    print("-"*60)
    await agent.assign_task("数据处理任务", duration=4)
    print(f"当前状态: {agent.get_state_name()}")
    
    print("\n" + "-"*60)
    print("步骤2: 启动任务")
    print("-"*60)
    await agent.start_task()
    
    await asyncio.sleep(2)
    
    print("\n" + "-"*60)
    print("步骤3: 暂停任务")
    print("-"*60)
    await agent.pause_task()
    
    await asyncio.sleep(1)
    
    print("\n" + "-"*60)
    print("步骤4: 恢复任务")
    print("-"*60)
    await agent.resume_task()
    
    await asyncio.sleep(3)
    
    print("\n" + "-"*60)
    print("步骤5: 任务完成")
    print("-"*60)
    print(f"最终状态: {agent.get_state_name()}")
    print(f"状态历史: {agent.state_machine.get_history()}")
    
    final_context = agent.get_context()
    print(f"\n任务统计:")
    print(f"  - 任务名称: {final_context.get('task', {}).get('name')}")
    print(f"  - 执行耗时: {final_context.get('duration', 0):.2f}秒")
    print(f"  - 最终进度: {final_context.get('progress', 0)}%")
    
    print("\n" + "="*80)
    print("✅ 状态机演示完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())