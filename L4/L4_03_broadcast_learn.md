# L4-03: Broadcast（广播模式）学习笔记

## 一、核心概念

### 1.1 什么是广播模式

**广播模式（Broadcast Pattern）**是一种一对多的通信架构，一个发送者可以向多个订阅者同时发送消息。订阅者需要先加入特定频道才能接收广播消息。

### 1.2 设计思想

- **发布-订阅模式**：发送者发布消息到频道，所有订阅该频道的接收者都会收到
- **频道隔离**：不同频道之间消息相互隔离
- **松耦合**：发送者不知道具体的接收者是谁

### 1.3 与其他模式对比

| 特性 | 黑板模式 | 信箱模式 | 广播模式 |
|------|---------|---------|---------|
| 通信方式 | 共享存储 | 点对点 | 一对多 |
| 可见性 | 全局可见 | 私有 | 频道内可见 |
| 耦合度 | 低 | 中等 | 低 |
| 消息流向 | 一对多 | 一对一 | 一对多 |
| 适用场景 | 知识共享 | 私密通信 | 事件通知 |

---

## 二、架构设计

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                   Broadcast 架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐    ┌─────────────────┐                │
│  │  Broadcaster │───→│ BroadcastServer │                │
│  │   (广播者)    │    │   (广播服务器)   │                │
│  └──────────────┘    └────────┬────────┘                │
│                               │                          │
│              ┌────────────────┼────────────────┐         │
│              ▼                ▼                ▼         │
│         ┌─────────┐    ┌─────────┐    ┌─────────┐       │
│         │ Channel │    │ Channel │    │ Channel │       │
│         │ general │    │  tech   │    │  news   │       │
│         └────┬────┘    └────┬────┘    └────┬────┘       │
│              │              │              │              │
│      ┌───────┼───────┐  ┌───┴───┐   ┌─────┴─────┐      │
│      ▼       ▼       ▼  ▼       ▼   ▼           ▼      │
│   ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐    │
│   │Agent ││Agent ││Agent ││Agent ││Agent ││Agent │    │
│   │  A   ││  B   ││  C   ││  D   ││  E   ││  F   │    │
│   └──────┘└──────┘└──────┘└──────┘└──────┘└──────┘    │
│                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 关键方法 |
|------|------|---------|
| **BroadcastMessage** | 消息数据结构 | `to_dict()` |
| **BroadcastServer** | 广播服务器 | `broadcast()`, `create_channel()` |
| **BroadcastAgent** | 参与广播的 Agent | `join_channel()`, `send_broadcast()` |

---

## 三、核心代码解析

### 3.1 消息数据结构

```python
@dataclass
class BroadcastMessage:
    id: str                    # 消息唯一标识
    sender: str                # 发送者ID
    channel: str               # 频道名称
    content: str               # 消息内容
    timestamp: float           # 发送时间
    topic: str                 # 主题
    metadata: Dict[str, Any]   # 元数据
```

### 3.2 广播服务器

```python
class BroadcastServer:
    def __init__(self):
        self.channels: Dict[str, Set[str]] = {}  # 频道 -> 订阅者集合
        self.listeners: Dict[str, List[Callable]] = {}  # 频道 -> 监听器
    
    def create_channel(self, channel_name: str):
        # 创建新频道
        if channel_name not in self.channels:
            self.channels[channel_name] = set()
            self.listeners[channel_name] = []
    
    def join_channel(self, channel_name: str, subscriber_id: str):
        # 订阅者加入频道
        self.channels[channel_name].add(subscriber_id)
    
    async def broadcast(self, sender, channel_name, content, topic="general"):
        # 广播消息到频道
        for listener in self.listeners.get(channel_name, []):
            listener(message)
```

### 3.3 广播 Agent

```python
class BroadcastAgent:
    def __init__(self, agent_id, name, server):
        self.agent_id = agent_id
        self.name = name
        self.server = server
        self.subscribed_channels = set()
    
    async def join_channel(self, channel_name):
        self.server.join_channel(channel_name, self.agent_id)
        self.subscribed_channels.add(channel_name)
        self.server.subscribe(channel_name, self._on_message)
    
    def _on_message(self, message):
        # 收到消息时的回调
        print(f"🔔 [{self.name}] 在 [{message.channel}] 收到消息")
    
    async def send_broadcast(self, channel_name, content, topic="general"):
        return await self.server.broadcast(self.agent_id, channel_name, content, topic)
```

---

## 四、消息流程

### 4.1 加入频道

```python
# Agent 加入频道
await alice.join_channel("general")
await bob.join_channel("general")
await charlie.join_channel("general")
```

### 4.2 广播消息

```
┌──────────────┐      ┌─────────────────┐      ┌──────────┐
│  Broadcaster │ ───→ │ BroadcastServer │ ───→ │ Channel  │
│    Alice     │      │                 │      │  general │
└──────────────┘      └─────────────────┘      └────┬─────┘
                                                    │
                          ┌─────────────────────────┼─────────────────────────┐
                          ▼                         ▼                         ▼
                    ┌──────────┐            ┌──────────┐            ┌──────────┐
                    │ Subscriber│            │ Subscriber│            │ Subscriber│
                    │    Bob    │            │  Charlie  │            │   Dave    │
                    └──────────┘            └──────────┘            └──────────┘
```

### 4.3 代码示例

```python
# 1. 创建服务器和 Agent
server = BroadcastServer()
alice = BroadcastAgent("agent_alice", "Alice", server)
bob = BroadcastAgent("agent_bob", "Bob", server)

# 2. 加入频道
await alice.join_channel("general")
await bob.join_channel("general")

# 3. 广播消息
await alice.send_broadcast("general", "大家好！")

# 输出：
# 🔔 [Bob] 在 [general] 收到消息: 大家好！...
```

---

## 五、关键特性

### 5.1 频道管理

| 操作 | 说明 |
|------|------|
| `create_channel()` | 创建新频道 |
| `join_channel()` | 加入频道 |
| `leave_channel()` | 离开频道 |
| `get_channel_subscribers()` | 获取频道订阅者列表 |

### 5.2 消息过滤

通过频道实现消息隔离：

```python
# tech 频道的消息只有 tech 订阅者能收到
await charlie.send_broadcast("tech", "Python 新特性")
# 只有 Alice 和 Charlie 能收到（他们订阅了 tech 频道）
```

### 5.3 发布-订阅模式

```python
# 订阅频道（添加监听器）
self.server.subscribe(channel_name, self._on_message)

# 发布消息（触发所有监听器）
for listener in self.listeners.get(channel_name, []):
    listener(message)
```

---

## 六、应用场景

### 6.1 适用场景

| 场景 | 说明 |
|------|------|
| **事件通知** | 系统事件广播给所有相关服务 |
| **实时通信** | 聊天室、即时消息 |
| **状态同步** | 多个服务之间同步状态 |
| **新闻推送** | 订阅特定主题的新闻 |

### 6.2 典型用例

```python
# 场景：系统通知
system = BroadcastAgent("system", "系统", server)
user1 = BroadcastAgent("user1", "用户1", server)
user2 = BroadcastAgent("user2", "用户2", server)

await user1.join_channel("notifications")
await user2.join_channel("notifications")

await system.send_broadcast("notifications", "系统将在10分钟后维护")
# 所有订阅者都会收到通知
```

---

## 七、代码优化建议

### 7.1 频道权限控制

```python
class BroadcastServer:
    def __init__(self):
        self.channel_permissions: Dict[str, Dict[str, bool]] = {}
    
    def set_permission(self, channel_name, agent_id, can_send=False, can_receive=True):
        if channel_name not in self.channel_permissions:
            self.channel_permissions[channel_name] = {}
        self.channel_permissions[channel_name][agent_id] = {
            "send": can_send,
            "receive": can_receive
        }
    
    async def broadcast(self, sender, channel_name, content):
        # 检查发送权限
        permissions = self.channel_permissions.get(channel_name, {}).get(sender, {})
        if not permissions.get("send", False):
            print(f"❌ [{sender}] 没有发送权限")
            return
```

### 7.2 消息持久化

```python
async def save_message(self, message):
    # 保存到数据库
    pass

async def get_history(self, channel_name, limit=100):
    # 获取历史消息
    pass
```

### 7.3 消息确认

```python
async def broadcast_with_ack(self, sender, channel_name, content, timeout=30):
    message = await self.broadcast(sender, channel_name, content)
    
    # 等待确认
    start_time = time.time()
    while time.time() - start_time < timeout:
        acks = self.get_acks(message.id)
        if len(acks) >= len(self.channels[channel_name]) * 0.8:
            return True
        await asyncio.sleep(1)
    
    return False
```

---

## 八、总结

### 8.1 核心要点

1. **一对多通信**：一个发送者，多个接收者
2. **频道隔离**：消息只在特定频道内传播
3. **松耦合**：发送者和接收者解耦
4. **订阅机制**：需要主动订阅才能接收消息

### 8.2 设计模式应用

| 模式 | 应用位置 |
|------|---------|
| **发布-订阅模式** | 频道订阅机制 |
| **观察者模式** | 监听器机制 |

### 8.3 与其他模式对比

| 模式 | 通信方式 | 核心特点 |
|------|---------|---------|
| Blackboard | 共享存储 | 全局可见 |
| Mailbox | 点对点 | 私有通信 |
| **Broadcast** | **一对多** | **频道订阅** |

---

## 九、参考资料

1. [Publish–subscribe pattern](https://en.wikipedia.org/wiki/Publish%E2%80%93subscribe_pattern)
2. [WebSocket Broadcasting](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
3. [Redis Pub/Sub](https://redis.io/docs/interact/pubsub/)