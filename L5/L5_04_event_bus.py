import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional, Set, Union
from enum import Enum


class EventPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    event_id: str
    event_type: str
    data: Dict[str, Any]
    timestamp: float
    source: str
    priority: EventPriority = EventPriority.NORMAL
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
            "priority": self.priority.name
        }


class EventHandler:
    def __init__(
        self,
        callback: Callable[[Event], Union[None, asyncio.Future, Any]],
        filter_func: Optional[Callable[[Event], bool]] = None,
        priority: EventPriority = EventPriority.NORMAL
    ):
        self.callback = callback
        self.filter_func = filter_func
        self.priority = priority
        self.handler_id = str(uuid.uuid4())
    
    async def handle(self, event: Event) -> None:
        if self.filter_func and not self.filter_func(event):
            return
        
        try:
            result = self.callback(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"❌ 事件处理失败 {self.handler_id}: {e}")


class EventBus:
    def __init__(self, max_concurrent_handlers: int = 10):
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._subscriber_ids: Dict[str, Set[str]] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._is_running = False
        self._dispatch_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent_handlers)
        self._lock = asyncio.Lock()
    
    async def subscribe(
        self,
        event_type: str,
        callback: Callable[[Event], Union[None, asyncio.Future, Any]],
        filter_func: Optional[Callable[[Event], bool]] = None,
        priority: EventPriority = EventPriority.NORMAL
    ) -> str:
        """订阅事件类型"""
        handler = EventHandler(callback, filter_func, priority)
        
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
                self._subscriber_ids[event_type] = set()
            
            self._subscribers[event_type].append(handler)
            self._subscriber_ids[event_type].add(handler.handler_id)
            self._subscribers[event_type].sort(key=lambda h: h.priority.value, reverse=True)
        
        return handler.handler_id
    
    async def unsubscribe(self, event_type: str, handler_id: str) -> bool:
        """取消订阅"""
        async with self._lock:
            if event_type not in self._subscribers:
                return False
            
            subscribers = self._subscribers[event_type]
            new_subscribers = [h for h in subscribers if h.handler_id != handler_id]
            
            if len(new_subscribers) == len(subscribers):
                return False
            
            self._subscribers[event_type] = new_subscribers
            self._subscriber_ids[event_type].discard(handler_id)
            
            if not self._subscribers[event_type]:
                del self._subscribers[event_type]
                del self._subscriber_ids[event_type]
            
            return True
    
    async def publish(self, event_type: str, data: Dict[str, Any], source: str = "unknown", 
                     priority: EventPriority = EventPriority.NORMAL) -> str:
        """发布事件"""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            data=data,
            timestamp=datetime.now().timestamp(),
            source=source,
            priority=priority
        )
        
        await self._event_queue.put(event)
        return event.event_id
    
    async def _dispatch(self) -> None:
        """事件分发循环"""
        while self._is_running:
            try:
                event = await self._event_queue.get()
                
                async with self._semaphore:
                    await self._handle_event(event)
                
                self._event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ 事件分发错误: {e}")
    
    async def _handle_event(self, event: Event) -> None:
        """处理单个事件"""
        event_types = [event.event_type, "*"]
        
        tasks = []
        for et in event_types:
            if et in self._subscribers:
                async with self._lock:
                    handlers = list(self._subscribers.get(et, []))
                
                for handler in handlers:
                    tasks.append(handler.handle(event))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def start(self) -> None:
        """启动事件总线"""
        if self._is_running:
            return
        
        self._is_running = True
        self._dispatch_task = asyncio.create_task(self._dispatch())
    
    async def stop(self) -> None:
        """停止事件总线"""
        self._is_running = False
        
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        await self._event_queue.join()
    
    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """获取订阅者数量"""
        if event_type:
            return len(self._subscribers.get(event_type, []))
        return sum(len(handlers) for handlers in self._subscribers.values())
    
    async def publish_sync(self, event_type: str, data: Dict[str, Any], source: str = "unknown",
                          priority: EventPriority = EventPriority.NORMAL) -> str:
        """同步发布事件（立即处理）"""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            data=data,
            timestamp=datetime.now().timestamp(),
            source=source,
            priority=priority
        )
        
        await self._handle_event(event)
        return event.event_id


class EventBusAgentMixin:
    """用于Agent的EventBus集成Mixin"""
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._subscribed_handlers: List[tuple] = []
    
    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
    
    async def subscribe_to_event(
        self,
        event_type: str,
        callback: Callable[[Event], Union[None, asyncio.Future, Any]],
        filter_func: Optional[Callable[[Event], bool]] = None,
        priority: EventPriority = EventPriority.NORMAL
    ) -> None:
        """订阅事件"""
        if not self._event_bus:
            raise ValueError("EventBus 未设置")
        
        handler_id = await self._event_bus.subscribe(event_type, callback, filter_func, priority)
        self._subscribed_handlers.append((event_type, handler_id))
    
    async def unsubscribe_all(self) -> None:
        """取消所有订阅"""
        if not self._event_bus:
            return
        
        for event_type, handler_id in self._subscribed_handlers:
            await self._event_bus.unsubscribe(event_type, handler_id)
        
        self._subscribed_handlers.clear()
    
    async def publish_event(self, event_type: str, data: Dict[str, Any],
                           priority: EventPriority = EventPriority.NORMAL) -> str:
        """发布事件"""
        if not self._event_bus:
            raise ValueError("EventBus 未设置")
        
        return await self._event_bus.publish(event_type, data, source=self.agent_id, priority=priority)


class LoggerAgent(EventBusAgentMixin):
    """日志记录Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        super().__init__(event_bus)
        self.agent_id = agent_id
    
    async def start(self) -> None:
        await self.subscribe_to_event("*", self._handle_all_events)
    
    async def _handle_all_events(self, event: Event) -> None:
        time_str = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(f"📝 [{time_str}] [{event.source}] [{event.event_type}] {event.data}")


class TaskAgent(EventBusAgentMixin):
    """任务处理Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        super().__init__(event_bus)
        self.agent_id = agent_id
        self.task_count = 0
    
    async def start(self) -> None:
        await self.subscribe_to_event(
            "task.created",
            self._handle_task_created,
            filter_func=lambda e: e.data.get("priority") == "high"
        )
        await self.subscribe_to_event("task.completed", self._handle_task_completed)
    
    async def _handle_task_created(self, event: Event) -> None:
        self.task_count += 1
        task_data = event.data
        print(f"🔧 [{self.agent_id}] 收到高优先级任务: {task_data['task_name']}")
        
        await asyncio.sleep(1)
        
        await self.publish_event(
            "task.completed",
            {
                "task_id": task_data["task_id"],
                "task_name": task_data["task_name"],
                "status": "completed",
                "handler": self.agent_id
            }
        )
    
    async def _handle_task_completed(self, event: Event) -> None:
        print(f"✅ [{self.agent_id}] 任务完成: {event.data['task_name']}")


class AlertAgent(EventBusAgentMixin):
    """告警Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        super().__init__(event_bus)
        self.agent_id = agent_id
    
    async def start(self) -> None:
        await self.subscribe_to_event(
            "system.error",
            self._handle_error,
            priority=EventPriority.CRITICAL
        )
    
    async def _handle_error(self, event: Event) -> None:
        print(f"🚨 [{self.agent_id}] 系统错误: {event.data.get('message', '未知错误')}")


async def main():
    print("="*80)
    print("🏭 L5-04: Event Bus 事件总线演示")
    print("="*80)
    
    event_bus = EventBus(max_concurrent_handlers=5)
    await event_bus.start()
    
    logger = LoggerAgent("logger", event_bus)
    await logger.start()
    
    task_agent = TaskAgent("task_agent", event_bus)
    await task_agent.start()
    
    alert_agent = AlertAgent("alert_agent", event_bus)
    await alert_agent.start()
    
    print("\n📤 发布事件...")
    
    await event_bus.publish(
        "task.created",
        {"task_id": "t1", "task_name": "处理用户请求", "priority": "high"},
        source="api_gateway",
        priority=EventPriority.HIGH
    )
    
    await event_bus.publish(
        "task.created",
        {"task_id": "t2", "task_name": "生成报告", "priority": "normal"},
        source="api_gateway",
        priority=EventPriority.NORMAL
    )
    
    await event_bus.publish(
        "system.error",
        {"error_code": "E001", "message": "数据库连接超时"},
        source="database",
        priority=EventPriority.CRITICAL
    )
    
    await event_bus.publish(
        "user.login",
        {"user_id": "u123", "username": "张三", "ip": "192.168.1.1"},
        source="auth_service"
    )
    
    await asyncio.sleep(2)
    
    await event_bus.stop()
    
    await logger.unsubscribe_all()
    await task_agent.unsubscribe_all()
    await alert_agent.unsubscribe_all()
    
    print("\n✅ Event Bus 演示完成")


if __name__ == "__main__":
    asyncio.run(main())