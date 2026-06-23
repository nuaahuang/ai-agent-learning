# L4-02: Mailbox（信箱模式）学习笔记

## 一、核心概念

### 1.1 什么是信箱模式

**信箱模式（Mailbox Pattern）**是一种点对点的多 Agent 通信架构，每个 Agent 拥有自己的私有"信箱"（Mailbox），消息通过消息路由器（Message Router）进行路由和投递。

### 1.2 设计思想

- **私有通信**：消息直接发送到目标 Agent 的信箱，只有收件人可以访问
- **异步通信**：发送者和接收者不需要同时在线
- **消息持久化**：消息存储在信箱中，直到被读取
- **优先级处理**：支持不同优先级的消息

### 1.3 与黑板模式对比

| 特性 | 黑板模式 | 信箱模式 |
|------|---------|---------|
| 通信方式 | 共享存储 | 点对点 |
| 可见性 | 全局可见 | 私有 |
| 耦合度 | 低 | 中等 |
| 消息流向 | 一对多 | 一对一 |
| 适用场景 | 知识共享、协作求解 | 私密通信、任务分配 |

---

## 二、架构设计

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Mailbox 架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Agent A    │    │   Agent B    │    │   Agent C    │  │
│  │              │    │              │    │              │  │
│  │  ┌────────┐  │    │  ┌────────┐  │    │  ┌────────┐  │  │
│  │  │Mailbox │  │    │  │Mailbox │  │    │  │Mailbox │  │  │
│  │  │        │  │    │  │        │  │    │  │        │  │  │
│  │  │Message1│  │←──→│  │Message2│  │←──→│  │Message3│  │  │
│  │  │Message4│  │    │  │        │  │    │  │        │  │  │
│  │  └────────┘  │    │  └────────┘  │    │  └────────┘  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│           │                  │                  │          │
│           └──────────────────┴──────────────────┘          │
│                        │                                   │
│                        ▼                                   │
│               ┌───────────────┐                            │
│               │ MessageRouter │                            │
│               │  (消息路由器)   │                            │
│               └───────────────┘                            │
│                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 关键方法 |
|------|------|---------|
| **Message** | 消息数据结构 | `mark_read()` |
| **Mailbox** | 消息存储和管理 | `add_message()`, `get_messages()` |
| **MessageRouter** | 消息路由和投递 | `route_message()`, `broadcast()` |
| **MailboxAgent** | 拥有信箱的 Agent | `send_message()`, `check_mailbox()` |

---

## 三、核心代码解析

### 3.1 消息数据结构

```python
@dataclass
class Message:
    id: str                    # 消息唯一标识
    sender: str                # 发件人ID
    recipient: str             # 收件人ID
    content: str               # 消息内容
    timestamp: float           # 发送时间
    priority: MessagePriority  # 优先级
    topic: str                 # 主题
    metadata: Dict[str, Any]   # 元数据
    read: bool                 # 是否已读
```

### 3.2 消息优先级

```python
class MessagePriority(Enum):
    LOW = 1      # 低优先级
    NORMAL = 2   # 普通优先级
    HIGH = 3     # 高优先级
    URGENT = 4   # 紧急优先级
```

### 3.3 信箱核心逻辑

```python
class Mailbox:
    def __init__(self, owner_id: str):
        self.messages: List[Message] = []  # 消息队列
        self.lock = asyncio.Lock()         # 异步锁
        self.listeners: List[Callable] = [] # 监听器
    
    async def add_message(self, message: Message):
        async with self.lock:
            self.messages.append(message)
            self._notify_listeners(message)
    
    async def get_messages(self, topic=None, priority=None, unread_only=False):
        # 支持按主题、优先级、是否已读筛选
        # 按优先级降序、时间升序排序
```

### 3.4 消息路由器（单例模式）

```python
class MessageRouter:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.mailboxes = {}
        return cls._instance
    
    async def route_message(self, message: Message):
        if message.recipient in self.mailboxes:
            await self.mailboxes[message.recipient].add_message(message)
```

### 3.5 MailboxAgent

```python
class MailboxAgent:
    def __init__(self, agent_id: str, name: str):
        self.mailbox = Mailbox(agent_id)
        self.router = MessageRouter()
        self.router.register_mailbox(agent_id, self.mailbox)
    
    async def send_message(self, recipient_id, content, priority=NORMAL, topic="general"):
        return await self.router.send_message(
            self.agent_id, recipient_id, content, priority, topic
        )
    
    async def broadcast(self, content, priority=NORMAL):
        await self.router.broadcast(self.agent_id, content, priority)
```

---

## 四、消息流程

### 4.1 点对点消息

```
┌──────────┐      ┌───────────────┐      ┌──────────┐
│  Agent A │ ───→ │ MessageRouter │ ───→ │  Agent B │
│          │      │               │      │          │
│ 发送消息 │      │  路由消息      │      │ 接收消息 │
└──────────┘      └───────────────┘      └──────────┘
```

### 4.2 广播消息

```
                    ┌───────────────┐
                    │ MessageRouter │
                    │   (广播)      │
                    └───────┬───────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │  Agent A │      │  Agent B │      │  Agent C │
    │  (发送者) │      │  (接收者) │      │  (接收者) │
    └──────────┘      └──────────┘      └──────────┘
```

### 4.3 消息处理流程

```python
# 1. Agent A 发送消息
await alice.send_message("agent_bob", "Hello!", priority=HIGH)

# 2. 消息路由器路由
# MessageRouter: agent_alice → agent_bob

# 3. Agent B 收到通知
# 🔔 [Bob] 收到新消息 (优先级:HIGH): Hello!...

# 4. Agent B 检查信箱
messages = await bob.check_mailbox()

# 5. 消息标记为已读
for msg in messages:
    msg.mark_read()
```

---

## 五、关键特性

### 5.1 优先级队列

消息按优先级排序，高优先级消息优先处理：

```python
# 获取消息时按优先级降序排序
return sorted(filtered, key=lambda x: (-x.priority.value, x.timestamp))
```

### 5.2 消息过滤

支持多种过滤方式：

| 过滤条件 | 说明 |
|---------|------|
| `topic` | 按主题筛选 |
| `priority` | 按优先级筛选 |
| `unread_only` | 只获取未读消息 |

### 5.3 异步通知机制

```python
def add_listener(self, listener: Callable[[Message], None]):
    self.listeners.append(listener)

def _notify_listeners(self, message: Message):
    for listener in self.listeners:
        listener(message)
```

### 5.4 线程安全

使用 `asyncio.Lock` 保证并发安全：

```python
async def add_message(self, message: Message):
    async with self.lock:
        self.messages.append(message)
```

---

## 六、应用场景

### 6.1 适用场景

| 场景 | 说明 |
|------|------|
| **任务分配** | 管理者向执行者发送任务 |
| **私密通信** | 两个 Agent 之间的秘密协商 |
| **请求-响应** | Client-Server 模式的通信 |
| **事件通知** | 订阅特定主题的消息 |

### 6.2 典型用例

```python
# 场景：任务分配
manager = MailboxAgent("manager", "经理")
worker = MailboxAgent("worker", "员工")

# 经理分配任务
await manager.send_message(
    "worker",
    "请完成项目报告",
    priority=MessagePriority.HIGH,
    topic="work"
)

# 员工完成后回复
await worker.send_message(
    "manager",
    "报告已完成，请查收",
    topic="work"
)
```

---

## 七、代码优化建议

### 7.1 消息持久化

当前消息只存储在内存中，服务重启后会丢失。可以添加持久化支持：

```python
class Mailbox:
    def __init__(self, owner_id: str, persist_path: str = None):
        self.persist_path = persist_path
        # 加载持久化消息
        if persist_path and os.path.exists(persist_path):
            self._load_messages()
    
    async def _save_messages(self):
        # 保存消息到文件/数据库
        pass
    
    def _load_messages(self):
        # 从文件/数据库加载消息
        pass
```

### 7.2 消息过期

添加消息过期机制：

```python
async def cleanup_expired_messages(self, max_age_hours: int = 24):
    async with self.lock:
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        self.messages = [m for m in self.messages if m.timestamp > cutoff]
```

### 7.3 消息确认

添加消息确认机制：

```python
async def send_message_with_ack(self, recipient_id, content, timeout=30):
    message = await self.send_message(recipient_id, content)
    
    # 等待确认
    for _ in range(timeout):
        if message.acknowledged:
            return True
        await asyncio.sleep(1)
    
    return False
```

---

## 八、总结

### 8.1 核心要点

1. **私有通信**：每个 Agent 有独立的信箱，消息私密
2. **异步解耦**：发送者和接收者解耦，支持异步通信
3. **优先级处理**：支持消息优先级，重要消息优先处理
4. **灵活过滤**：支持按主题、优先级、状态过滤消息
5. **线程安全**：使用异步锁保证并发安全

### 8.2 设计模式应用

| 模式 | 应用位置 |
|------|---------|
| **单例模式** | MessageRouter |
| **观察者模式** | Mailbox 监听器 |
| **策略模式** | 可扩展的消息处理 |

### 8.3 与其他模式对比

| 模式 | 通信方式 | 核心特点 |
|------|---------|---------|
| Blackboard | 共享存储 | 全局可见，知识共享 |
| Mailbox | 点对点 | 私有通信，请求响应 |
| Broadcast | 一对多 | 广播通知，事件分发 |

---

## 九、参考资料

1. [Actor Model](https://en.wikipedia.org/wiki/Actor_model)
2. [Message Passing Interface](https://en.wikipedia.org/wiki/Message_Passing_Interface)
3. [RabbitMQ Tutorial](https://www.rabbitmq.com/getstarted.html)