import asyncio
from typing import Dict, List, Optional, Callable, Any, Set
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

class BroadcastChannel(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SYSTEM = "system"

@dataclass
class BroadcastMessage:
    id: str
    sender: str
    channel: str
    content: str
    timestamp: float
    topic: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender,
            "channel": self.channel,
            "content": self.content,
            "timestamp": self.timestamp,
            "topic": self.topic
        }

class BroadcastServer:
    def __init__(self):
        self.channels: Dict[str, Set[str]] = {}
        self.listeners: Dict[str, List[Callable]] = {}
        self.client = httpx.AsyncClient(timeout=30)
    
    def create_channel(self, channel_name: str):
        if channel_name not in self.channels:
            self.channels[channel_name] = set()
            self.listeners[channel_name] = []
            print(f"📢 创建频道: {channel_name}")
    
    def join_channel(self, channel_name: str, subscriber_id: str):
        if channel_name not in self.channels:
            self.create_channel(channel_name)
        self.channels[channel_name].add(subscriber_id)
        print(f"👥 [{subscriber_id}] 加入频道: {channel_name}")
    
    def leave_channel(self, channel_name: str, subscriber_id: str):
        if channel_name in self.channels:
            self.channels[channel_name].discard(subscriber_id)
            print(f"👋 [{subscriber_id}] 离开频道: {channel_name}")
    
    def subscribe(self, channel_name: str, callback: Callable):
        if channel_name not in self.listeners:
            self.listeners[channel_name] = []
        self.listeners[channel_name].append(callback)
    
    async def broadcast(self, sender: str, channel_name: str, content: str, topic: str = "general", **kwargs):
        if channel_name not in self.channels:
            print(f"⚠️ 频道不存在: {channel_name}")
            return
        
        message = BroadcastMessage(
            id=str(uuid.uuid4())[:8],
            sender=sender,
            channel=channel_name,
            content=content,
            timestamp=datetime.now().timestamp(),
            topic=topic,
            metadata=kwargs
        )
        
        subscribers = self.channels[channel_name]
        print(f"📣 广播到频道 [{channel_name}]，{len(subscribers)} 个订阅者")
        
        for listener in self.listeners.get(channel_name, []):
            try:
                result = listener(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"❌ 监听器调用失败: {e}")
        
        return message
    
    async def direct_message(self, sender: str, recipient: str, content: str, topic: str = "direct"):
        message = BroadcastMessage(
            id=str(uuid.uuid4())[:8],
            sender=sender,
            channel=f"direct_{recipient}",
            content=content,
            timestamp=datetime.now().timestamp(),
            topic=topic
        )
        return message
    
    def get_channel_subscribers(self, channel_name: str) -> Set[str]:
        return self.channels.get(channel_name, set())
    
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
            return "AI服务不可用"
    
    async def close(self):
        await self.client.aclose()

class BroadcastAgent:
    def __init__(self, agent_id: str, name: str, server: BroadcastServer):
        self.agent_id = agent_id
        self.name = name
        self.server = server
        self.subscribed_channels: Set[str] = set()
    
    async def join_channel(self, channel_name: str):
        self.server.join_channel(channel_name, self.agent_id)
        self.subscribed_channels.add(channel_name)
        self.server.subscribe(channel_name, self._on_message)
    
    async def leave_channel(self, channel_name: str):
        self.server.leave_channel(channel_name, self.agent_id)
        self.subscribed_channels.discard(channel_name)
    
    def _on_message(self, message: BroadcastMessage):
        if message.sender != self.agent_id:
            print(f"🔔 [{self.name}] 在 [{message.channel}] 收到消息: {message.content[:30]}...")
    
    async def send_broadcast(self, channel_name: str, content: str, topic: str = "general"):
        return await self.server.broadcast(self.agent_id, channel_name, content, topic)
    
    async def send_direct(self, recipient_id: str, content: str):
        return await self.server.direct_message(self.agent_id, recipient_id, content)

async def main():
    print("="*80)
    print("🏫 L4-03: Broadcast（广播模式）")
    print("="*80)
    
    server = BroadcastServer()
    
    alice = BroadcastAgent("agent_alice", "Alice", server)
    bob = BroadcastAgent("agent_bob", "Bob", server)
    charlie = BroadcastAgent("agent_charlie", "Charlie", server)
    dave = BroadcastAgent("agent_dave", "Dave", server)
    
    await alice.join_channel("general")
    await bob.join_channel("general")
    await charlie.join_channel("general")
    await dave.join_channel("general")
    
    await alice.join_channel("tech")
    await charlie.join_channel("tech")
    
    print("\n📊 当前频道状态")
    print(f"general 频道订阅者: {server.get_channel_subscribers('general')}")
    print(f"tech 频道订阅者: {server.get_channel_subscribers('tech')}")
    
    print("\n" + "="*80)
    print("📣 Alice 在 general 频道广播")
    print("="*80)
    await alice.send_broadcast("general", "大家好！今天天气真好！")
    
    await asyncio.sleep(1)
    
    print("\n" + "="*80)
    print("📣 Charlie 在 tech 频道广播")
    print("="*80)
    await charlie.send_broadcast("tech", "Python 3.12 发布了新特性！")
    
    await asyncio.sleep(1)
    
    print("\n" + "="*80)
    print("📣 Bob 在 general 频道回复")
    print("="*80)
    await bob.send_broadcast("general", "是的，阳光明媚！")
    
    await server.close()
    
    print("\n" + "="*80)
    print("✅ 广播模式演示完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())