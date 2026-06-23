# L4-04: Hand-off（交接机制）学习笔记

## 一、核心概念

### 1.1 什么是 Hand-off 机制

**Hand-off（交接机制）**是一种任务转移策略，允许一个 Agent 将任务或对话状态转移给另一个更专业的 Agent。这是实现多 Agent 协作的关键机制。

### 1.2 设计思想

- **专业化分工**：每个 Agent 专注于自己擅长的领域
- **智能路由**：根据任务特性自动选择最合适的处理者
- **状态传递**：交接时传递完整的任务上下文和历史
- **可追溯性**：记录任务交接历史，便于追踪和审计

### 1.3 与其他模式对比

| 特性 | 黑板模式 | 信箱模式 | 广播模式 | Hand-off |
|------|---------|---------|---------|----------|
| 通信方式 | 共享存储 | 点对点 | 一对多 | 任务转移 |
| 核心目的 | 知识共享 | 私密通信 | 事件通知 | 专业分工 |
| 耦合度 | 低 | 中等 | 低 | 中等 |
| 适用场景 | 协作求解 | 请求响应 | 实时通知 | 任务分发 |

---

## 二、架构设计

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Hand-off 架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────┐      ┌───────────────┐                   │
│  │  TaskManager│      │               │                   │
│  │   (任务管理) │      │   Agent Pool  │                   │
│  └──────┬──────┘      │   (Agent池)    │                   │
│         │             └───────┬───────┘                   │
│         │                     │                          │
│         ▼                     ▼                          │
│  ┌───────────────────────────────────────────────────┐    │
│  │              Task Flow                           │    │
│  │                                                  │    │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐   │    │
│  │  │  Agent A │───→│  Agent B │───→│  Agent C │   │    │
│  │  │ (通用)   │    │ (专家1)  │    │ (专家2)  │   │    │
│  │  └──────────┘    └──────────┘    └──────────┘   │    │
│  │       │                │                │        │    │
│  └───────┴────────────────┴────────────────┴────────┘    │
│                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 关键方法 |
|------|------|---------|
| **Task** | 任务数据结构 | `to_dict()` |
| **TaskManager** | 任务管理中心 | `create_task()`, `handoff_task()` |
| **HandoffAgent** | 具备交接能力的 Agent | `decide_handoff()`, `process_task()` |
| **AgentCapability** | Agent 能力枚举 | - |

---

## 三、核心代码解析

### 3.1 任务状态

```python
class TaskStatus(Enum):
    PENDING = "pending"       # 待处理
    IN_PROGRESS = "in_progress" # 处理中
    COMPLETED = "completed"   # 已完成
    HANDOFF = "handoff"       # 交接中
    FAILED = "failed"         # 失败
```

### 3.2 Agent 能力

```python
class AgentCapability(Enum):
    GENERAL = "general"       # 通用能力
    ANALYSIS = "analysis"     # 分析能力
    PLANNING = "planning"     # 规划能力
    FINANCE = "finance"       # 财务能力
    TECHNICAL = "technical"   # 技术能力
    # ...
```

### 3.3 任务数据结构

```python
@dataclass
class Task:
    id: str                    # 任务ID
    title: str                 # 任务标题
    description: str           # 任务描述
    status: TaskStatus         # 任务状态
    assignee: Optional[str]    # 当前负责人
    previous_assignee: Optional[str]  # 前任负责人
    context: Dict[str, Any]    # 任务上下文
    history: List[Dict]        # 历史记录
    priority: int = 1          # 优先级
```

### 3.4 任务管理器

```python
class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
    
    def create_task(self, title, description, priority=1) -> Task:
        # 创建新任务
    
    def assign_task(self, task_id, agent_id) -> bool:
        # 分配任务给 Agent
    
    async def handoff_task(self, task_id, from_agent, to_agent, reason, context=None):
        # 执行任务交接
        task.previous_assignee = task.assignee
        task.assignee = to_agent
        task.status = TaskStatus.HANDOFF
```

### 3.5 HandoffAgent

```python
class HandoffAgent:
    def __init__(self, agent_id, name, capabilities, task_manager):
        self.agent_id = agent_id
        self.name = name
        self.capabilities = capabilities
    
    def can_handle(self, task: Task) -> bool:
        # 判断是否能处理该任务
    
    async def decide_handoff(self, task, available_agents):
        # 决定是否需要交接
        other_agents = [a for a in available_agents if a.agent_id != self.agent_id]
        # 调用 AI 决策
    
    async def process_task(self, task):
        # 处理任务
```

---

## 四、交接流程

### 4.1 流程图示

```
┌─────────────────────────────────────────────────────────────┐
│                    Hand-off 流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                           │
│  1. 创建任务                                               │
│     │                                                      │
│     ▼                                                      │
│  2. 分配给初始 Agent                                       │
│     │                                                      │
│     ▼                                                      │
│  3. Agent 处理任务                                         │
│     │                                                      │
│     ▼                                                      │
│  4. 决定是否交接 (AI决策)                                   │
│     │                                                      │
│     ├── 是 ──→ 5. 执行交接                                 │
│     │              │                                        │
│     │              ▼                                        │
│     │         6. 目标 Agent 继续处理                        │
│     │              │                                        │
│     │              ▼                                        │
│     │         7. 完成任务                                   │
│     │                                                      │
│     └── 否 ──→ 直接完成任务                                 │
│                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 代码示例

```python
# 1. 创建任务
task = task_manager.create_task("财务报表分析", "分析Q1财务报表")

# 2. 分配给通用助手
task_manager.assign_task(task.id, general_agent.agent_id)

# 3. 处理任务
await general_agent.process_task(task)

# 4. 决定是否交接
target_id, reason = await general_agent.decide_handoff(task, agents)

# 5. 执行交接
if target_id:
    await task_manager.handoff_task(task.id, general_agent.agent_id, target_id, reason)
    
    # 6. 目标 Agent 处理
    target_agent = next(a for a in agents if a.agent_id == target_id)
    await target_agent.process_task(task)
    
    # 7. 完成任务
    task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
```

---

## 五、关键特性

### 5.1 能力匹配

```python
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
```

### 5.2 智能决策

```python
async def decide_handoff(self, task, available_agents):
    # 调用 AI 判断是否需要交接
    prompt = f"""
    当前任务: {task.title}
    当前处理者: {self.name}
    我的能力: {[c.value for c in self.capabilities]}
    
    其他可用专家:
    {chr(10).join([f"- {a.name}: {[c.value for c in a.capabilities]}" for a in other_agents])}
    """
    
    response = await self._call_ai(prompt, system_prompt)
    
    if "需要交接给" in response:
        # 返回目标 Agent 和原因
```

### 5.3 上下文传递

```python
async def handoff_task(self, task_id, from_agent, to_agent, reason, context=None):
    task = self.tasks[task_id]
    
    # 传递上下文
    if context:
        task.context.update(context)
    
    # 记录历史
    task.history.append({
        "action": "handoff",
        "from": from_agent,
        "to": to_agent,
        "reason": reason
    })
```

---

## 六、应用场景

### 6.1 适用场景

| 场景 | 说明 |
|------|------|
| **专业分工** | 通用 Agent 接收任务，专业 Agent 处理 |
| **任务路由** | 根据任务类型自动分配到合适的 Agent |
| **能力扩展** | 当当前 Agent 能力不足时转移任务 |
| **负载均衡** | 将任务分配给负载较低的 Agent |

### 6.2 典型用例

```python
# 场景：客服系统
class CustomerServiceAgent(HandoffAgent):
    async def handle_inquiry(self, inquiry):
        if "账单" in inquiry:
            # 交接给财务专家
            await self.handoff_to_finance(inquiry)
        elif "技术问题" in inquiry:
            # 交接给技术支持
            await self.handoff_to_tech(inquiry)
        else:
            # 自己处理
            self.process(inquiry)
```

---

## 七、代码优化建议

### 7.1 智能路由优化

```python
class TaskRouter:
    def __init__(self, agents):
        self.agents = agents
    
    def find_best_agent(self, task):
        scores = []
        for agent in self.agents:
            score = agent.get_capability_score(task)
            scores.append((agent, score))
        
        # 选择分数最高的 Agent
        return max(scores, key=lambda x: x[1])[0]
```

### 7.2 交接策略

```python
class HandoffStrategy(Enum):
    ALWAYS = "always"           # 总是交接
    WHEN_NEEDED = "when_needed" # 需要时交接
    NEVER = "never"             # 永不交接

class HandoffAgent:
    def __init__(self, handoff_strategy=HandoffStrategy.WHEN_NEEDED):
        self.handoff_strategy = handoff_strategy
    
    async def decide_handoff(self, task, available_agents):
        if self.handoff_strategy == HandoffStrategy.NEVER:
            return None, None
        # ...
```

### 7.3 同步 vs 异步 Hand-off

```python
class HandoffAgent:
    # 同步交接：等待目标 Agent 完成
    async def handoff_with_await(self, task, to_agent, reason) -> Task:
        await self.task_manager.handoff_task(task.id, self.agent_id, to_agent.agent_id, reason)
        await to_agent.process_task(task)  # 阻塞等待
        self.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
        return task
    
    # 异步交接：立即返回，后台处理
    async def handoff_async(self, task, to_agent, reason, callback=None) -> Dict:
        await self.task_manager.handoff_task(task.id, self.agent_id, to_agent.agent_id, reason)
        asyncio.create_task(self._process_async(to_agent, task, callback))  # 后台处理
        return {"status": "handoff_initiated", "task_id": task.id}
    
    async def _process_async(self, next_agent, task, callback):
        try:
            await next_agent.process_task(task)
            self.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
            if callback:
                callback(task, next_agent)
        except Exception as e:
            self.task_manager.update_task_status(task.id, TaskStatus.FAILED)
```

**使用示例**：

```python
# 同步：需要等待完成
await agent_a.handoff_with_await(task, agent_b, "需要专业处理")

# 异步：立即返回，后台处理
result = await agent_a.handoff_async(
    task, 
    agent_b, 
    "需要专业处理",
    callback=lambda t, a: print(f"任务由 {a.name} 完成")
)
print("立即返回，继续其他任务...")  # 不阻塞
```

### 7.4 交接确认

```python
async def handoff_with_confirmation(self, task_id, from_agent, to_agent, reason):
    # 向目标 Agent 发送交接请求
    request = HandoffRequest(
        task_id=task_id,
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason
    )
    
    # 等待确认
    confirmation = await self._send_handoff_request(request)
    
    if confirmation.accepted:
        await self.handoff_task(task_id, from_agent, to_agent, reason)
        return True
    
    return False
```

---

## 八、总结

### 8.1 核心要点

1. **专业化分工**：不同 Agent 负责不同领域
2. **智能决策**：基于 AI 判断是否需要交接
3. **状态传递**：完整传递任务上下文和历史
4. **可追溯性**：记录所有交接历史

### 8.2 设计模式应用

| 模式 | 应用位置 |
|------|---------|
| **策略模式** | 交接策略选择 |
| **代理模式** | Agent 代理处理任务 |
| **责任链模式** | 任务在多个 Agent 之间传递 |

### 8.3 与其他模式对比

| 模式 | 核心特点 | 适用场景 |
|------|---------|---------|
| Blackboard | 共享知识 | 协作求解 |
| Mailbox | 点对点通信 | 私密通信 |
| Broadcast | 一对多通知 | 事件广播 |
| **Hand-off** | **任务转移** | **专业分工** |

---

## 九、参考资料

1. [Agent Communication Protocols](https://arxiv.org/abs/2308.01952)
2. [Multi-Agent Systems](https://en.wikipedia.org/wiki/Multi-agent_system)
3. [Task Allocation in Multi-Agent Systems](https://www.sciencedirect.com/topics/computer-science/task-allocation)