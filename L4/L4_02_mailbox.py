import asyncio
from typing import Dict, List, Optional, Callable, Any
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

class MessagePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class Message:
    id: str
    sender: str
    recipient: str
    content: str
    timestamp: float
    priority: MessagePriority = MessagePriority.NORMAL
    topic: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)
    read: bool = False
    
    def mark_read(self):
        self.read = True
    
    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "topic": self.topic,
            "read": self.read
        }

class Mailbox:
    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.messages: List[Message] = []
        self.lock = asyncio.Lock()
        self.listeners: List[Callable[[Message], None]] = []
    
    async def add_message(self, message: Message):
        async with self.lock:
            self.messages.append(message)
            self._notify_listeners(message)
    
    async def get_messages(self, 
                          topic: Optional[str] = None,
                          priority: Optional[MessagePriority] = None,
                          unread_only: bool = False) -> List[Message]:
        async with self.lock:
            filtered = self.messages
            
            if topic:
                filtered = [m for m in filtered if m.topic == topic]
            if priority:
                filtered = [m for m in filtered if m.priority == priority]
            if unread_only:
                filtered = [m for m in filtered if not m.read]
            
            return sorted(filtered, key=lambda x: (-x.priority.value, x.timestamp))
    
    async def get_unread_count(self) -> int:
        async with self.lock:
            return sum(1 for m in self.messages if not m.read)
    
    async def mark_all_read(self):
        async with self.lock:
            for message in self.messages:
                message.mark_read()
    
    async def delete_message(self, message_id: str) -> bool:
        async with self.lock:
            for i, msg in enumerate(self.messages):
                if msg.id == message_id:
                    del self.messages[i]
                    return True
            return False
    
    def add_listener(self, listener: Callable[[Message], None]):
        self.listeners.append(listener)
    
    def _notify_listeners(self, message: Message):
        for listener in self.listeners:
            try:
                listener(message)
            except Exception as e:
                print(f"❌ 监听器调用失败: {e}")
    
    def clear(self):
        self.messages.clear()

class MessageRouter:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MessageRouter, cls).__new__(cls)
            cls._instance.mailboxes: Dict[str, Mailbox] = {}
            cls._instance.client = httpx.AsyncClient(timeout=30)
        return cls._instance
    
    def register_mailbox(self, owner_id: str, mailbox: Mailbox):
        self.mailboxes[owner_id] = mailbox
    
    def unregister_mailbox(self, owner_id: str):
        if owner_id in self.mailboxes:
            del self.mailboxes[owner_id]
    
    async def route_message(self, message: Message):
        if message.recipient in self.mailboxes:
            await self.mailboxes[message.recipient].add_message(message)
            print(f"📬 消息已投递: {message.sender} → {message.recipient}")
        else:
            print(f"⚠️ 收件人不存在: {message.recipient}")
    
    async def send_message(self, sender: str, recipient: str, content: str,
                          priority: MessagePriority = MessagePriority.NORMAL,
                          topic: str = "general", **kwargs):
        message = Message(
            id=str(uuid.uuid4())[:8],
            sender=sender,
            recipient=recipient,
            content=content,
            timestamp=datetime.now().timestamp(),
            priority=priority,
            topic=topic,
            metadata=kwargs
        )
        await self.route_message(message)
        return message
    
    async def broadcast(self, sender: str, content: str, 
                       priority: MessagePriority = MessagePriority.NORMAL,
                       topic: str = "broadcast"):
        for recipient_id in self.mailboxes:
            if recipient_id != sender:
                await self.send_message(sender, recipient_id, content, priority, topic)
    
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
            return "AI服务不可用，使用默认响应"
    
    async def close(self):
        await self.client.aclose()

class MailboxAgent:
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.mailbox = Mailbox(agent_id)
        self.router = MessageRouter()
        self.router.register_mailbox(agent_id, self.mailbox)
        self.mailbox.add_listener(self._on_new_message)
        self.running = False
        self.task = None
    
    def _on_new_message(self, message: Message):
        print(f"🔔 [{self.name}] 收到新消息 (优先级:{message.priority.name}): {message.content[:30]}...")
    
    async def start(self):
        """启动消息处理循环"""
        self.running = True
        self.task = asyncio.create_task(self.process_messages())
        print(f"🚀 [{self.name}] 消息处理循环已启动")
    
    async def send_message(self, recipient_id: str, content: str,
                          priority: MessagePriority = MessagePriority.NORMAL,
                          topic: str = "general", **kwargs):
        return await self.router.send_message(
            self.agent_id, recipient_id, content, priority, topic, **kwargs
        )
    
    async def broadcast(self, content: str, 
                       priority: MessagePriority = MessagePriority.NORMAL):
        await self.router.broadcast(self.agent_id, content, priority)
    
    async def check_mailbox(self, topic: Optional[str] = None,
                           unread_only: bool = True) -> List[Message]:
        messages = await self.mailbox.get_messages(topic=topic, unread_only=unread_only)
        for msg in messages:
            msg.mark_read()
        return messages
    
    async def get_unread_count(self) -> int:
        return await self.mailbox.get_unread_count()
    
    async def process_messages(self):
        """后台消息处理循环"""
        while self.running:
            messages = await self.check_mailbox()
            for msg in messages:
                await self._process_message(msg)
            await asyncio.sleep(0.5)
    
    async def _process_message(self, message: Message):
        print(f"\n📩 [{self.name}] 处理消息:")
        print(f"  发件人: {message.sender}")
        print(f"  主题: {message.topic}")
        print(f"  优先级: {message.priority.name}")
        print(f"  内容: {message.content}")
        
        system_prompt = "你是一个消息处理助手。请简洁地回复收到的消息，不要超过50字。"
        response = await self.router.call_ai(f"收到消息: {message.content}\n请给出简短回复:", system_prompt)
        
        print(f"  回复: {response}")
        await self.send_message(message.sender, response, topic=message.topic)
    
    async def stop(self):
        """停止消息处理循环"""
        self.running = False
        if self.task:
            await self.task
        self.router.unregister_mailbox(self.agent_id)
        print(f"🛑 [{self.name}] 消息处理循环已停止")

async def main():
    print("="*80)
    print("🏫 L4-02: Mailbox（信箱模式）")
    print("="*80)
    
    alice = MailboxAgent("agent_alice", "Alice")
    bob = MailboxAgent("agent_bob", "Bob")
    charlie = MailboxAgent("agent_charlie", "Charlie")
    
    await alice.start()
    await bob.start()
    await charlie.start()
    
    print(f"\n📧 创建信箱并启动消息处理: {alice.name}, {bob.name}, {charlie.name}")
    
    await alice.send_message("agent_bob", "嗨 Bob，最近怎么样？", 
                           priority=MessagePriority.HIGH)
    
    await asyncio.sleep(3)
    
    await bob.send_message("agent_alice", "我很好，谢谢！你呢？")
    
    await asyncio.sleep(3)
    
    await charlie.broadcast("大家好！我是新来的 Charlie！")
    
    await asyncio.sleep(3)
    
    print("\n" + "="*80)
    print("📊 各信箱状态")
    print("="*80)
    
    print(f"\n[{alice.name}] 未读消息: {await alice.get_unread_count()}")
    print(f"[{bob.name}] 未读消息: {await bob.get_unread_count()}")
    print(f"[{charlie.name}] 未读消息: {await charlie.get_unread_count()}")
    
    await alice.stop()
    await bob.stop()
    await charlie.stop()
    await MessageRouter().close()
    
    print("\n" + "="*80)
    print("✅ 信箱模式演示完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())