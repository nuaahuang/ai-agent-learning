import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional, Set, Union
from enum import Enum
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")


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
        handler = EventHandler(callback, filter_func, priority)
        
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
                self._subscriber_ids[event_type] = set()
            
            self._subscribers[event_type].append(handler)
            self._subscriber_ids[event_type].add(handler.handler_id)
        
        return handler.handler_id
    
    async def unsubscribe(self, event_type: str, handler_id: str) -> bool:
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
        if self._is_running:
            return
        
        self._is_running = True
        self._dispatch_task = asyncio.create_task(self._dispatch())
    
    async def stop(self) -> None:
        self._is_running = False
        
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        await self._event_queue.join()


class RealLLMAgent:
    """真实调用大模型的Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        self.agent_id = agent_id
        self.event_bus = event_bus
        self.client = httpx.AsyncClient(timeout=60)
        self._subscribed_handlers: List[tuple] = []
    
    async def _call_ai(self, prompt: str, system_prompt: str = "") -> str:
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
                    "max_tokens": 1000
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"⚠️ [{self.agent_id}] AI调用失败: {e}")
            return f"错误: {str(e)}"
    
    async def start(self) -> None:
        await self.event_bus.subscribe("user.query", self._handle_user_query)
    
    async def _handle_user_query(self, event: Event) -> None:
        query = event.data.get("query", "")
        print(f"🤖 [{self.agent_id}] 收到用户查询: {query}")
        
        system_prompt = """你是一位专业的AI助手。请用简洁明了的语言回答用户的问题。"""
        response = await self._call_ai(query, system_prompt)
        
        await self.event_bus.publish(
            "llm.response",
            {
                "query": query,
                "response": response,
                "source": self.agent_id,
                "timestamp": datetime.now().timestamp()
            },
            source=self.agent_id,
            priority=EventPriority.HIGH
        )
    
    async def close(self):
        await self.client.aclose()


class QueryParserAgent:
    """查询解析Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        self.agent_id = agent_id
        self.event_bus = event_bus
    
    async def start(self) -> None:
        await self.event_bus.subscribe("user.message", self._parse_message)
    
    async def _parse_message(self, event: Event) -> None:
        message = event.data.get("message", "")
        print(f"🔍 [{self.agent_id}] 解析消息: {message}")
        
        intent = self._detect_intent(message)
        entities = self._extract_entities(message)
        
        await self.event_bus.publish(
            "user.query",
            {
                "query": message,
                "intent": intent,
                "entities": entities,
                "original_source": event.source
            },
            source=self.agent_id
        )
    
    def _detect_intent(self, message: str) -> str:
        if any(keyword in message.lower() for keyword in ["帮助", "怎么", "如何"]):
            return "help"
        elif any(keyword in message.lower() for keyword in ["搜索", "查找", "查询"]):
            return "search"
        elif any(keyword in message.lower() for keyword in ["总结", "摘要"]):
            return "summarize"
        return "general"
    
    def _extract_entities(self, message: str) -> List[str]:
        return []


class ResponseFormatterAgent:
    """响应格式化Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        self.agent_id = agent_id
        self.event_bus = event_bus
    
    async def start(self) -> None:
        await self.event_bus.subscribe("llm.response", self._format_response)
    
    async def _format_response(self, event: Event) -> None:
        query = event.data.get("query", "")
        response = event.data.get("response", "")
        
        print(f"📝 [{self.agent_id}] 格式化响应")
        
        formatted = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 用户问题: {query}

💡 AI回答:
{response}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await self.event_bus.publish(
            "system.output",
            {
                "content": formatted,
                "query": query
            },
            source=self.agent_id
        )


class OutputAgent:
    """输出展示Agent"""
    
    def __init__(self, agent_id: str, event_bus: EventBus):
        self.agent_id = agent_id
        self.event_bus = event_bus
    
    async def start(self) -> None:
        await self.event_bus.subscribe("system.output", self._display_output)
    
    async def _display_output(self, event: Event) -> None:
        content = event.data.get("content", "")
        print(f"\n{content}")


async def main():
    print("="*80)
    print("🏭 L5-04: Event Bus + 真实大模型调用演示")
    print("="*80)
    
    event_bus = EventBus(max_concurrent_handlers=5)
    await event_bus.start()
    
    llm_agent = RealLLMAgent("llm_agent", event_bus)
    await llm_agent.start()
    
    parser = QueryParserAgent("parser", event_bus)
    await parser.start()
    
    formatter = ResponseFormatterAgent("formatter", event_bus)
    await formatter.start()
    
    output = OutputAgent("output", event_bus)
    await output.start()
    
    user_input = input("\n请输入你的问题: ") or "AI Agent是什么？"
    
    print(f"\n📤 发布用户消息事件...")
    
    await event_bus.publish(
        "user.message",
        {"message": user_input, "user_id": "user001"},
        source="user_interface",
        priority=EventPriority.HIGH
    )
    
    await asyncio.sleep(10)
    
    await event_bus.stop()
    await llm_agent.close()
    
    print("\n✅ Event Bus + 大模型调用演示完成")


if __name__ == "__main__":
    asyncio.run(main())