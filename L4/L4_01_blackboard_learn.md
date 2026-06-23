# L4-01: Blackboard（黑板模式）学习笔记

## 🏫 什么是黑板模式

**黑板模式（Blackboard Pattern）** 是一种多 Agent 协作架构，其中多个 Agent 通过共享的"黑板"进行通信和协作。

### 核心概念

```
┌─────────────────────────────────────────────────────┐
│                    Blackboard                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │  Fact   │ │ Plan    │ │ Result  │ │ Question│  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│     ↑            ↑           ↑            ↑        │
└─────│────────────│───────────│────────────│────────┘
      │            │           │            │
┌─────┴────────────┴───────────┴────────────┴────────┐
│                   Agents                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │Analyzer │ │ Planner │ │Executor │ │Verifier │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 核心组件

### 1. Blackboard（黑板）
```python
class Blackboard:
    def __init__(self):
        self.entries = {}      # 存储所有条目
        self.subscribers = []  # 订阅者列表
        self.lock = asyncio.Lock()  # 线程安全锁
```

### 2. BlackboardEntry（黑板条目）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 唯一标识 |
| content | str | 条目内容 |
| entry_type | Enum | 条目类型（事实/计划/结果等） |
| author | str | 创建者 |
| priority | int | 优先级 |
| confidence | float | 置信度 |
| tags | List | 标签 |

### 3. 条目类型

```python
class BlackboardEntryType(Enum):
    FACT = "fact"           # 事实信息
    HYPOTHESIS = "hypothesis" # 假设
    PLAN = "plan"           # 计划
    RESULT = "result"       # 结果
    QUESTION = "question"   # 问题
    ACTION = "action"       # 行动建议
```

---

## 🤖 Agent 角色

### 典型角色分配

| 角色 | 职责 | 示例 |
|------|------|------|
| **Analyzer** | 分析问题 | 识别关键要素 |
| **Planner** | 制定计划 | 生成执行步骤 |
| **Executor** | 执行任务 | 调用工具 |
| **Verifier** | 验证结果 | 检查正确性 |
| **Summarizer** | 总结归纳 | 生成最终报告 |

### Agent 工作流程

```python
async def run(self, task):
    # 1. 观察黑板
    entries = self.blackboard.get_all_entries()
    
    # 2. 根据角色执行任务
    if self.role == AgentRole.ANALYZER:
        await self.analyze(task)
    
    # 3. 发布结果到黑板
    await self.blackboard.add_entry(result, ...)
    
    # 4. 通知其他 Agent
    # (自动通过订阅机制)
```

---

## 🔄 通信机制

### 订阅-通知模式

```python
def subscribe(self, callback):
    """订阅黑板变化"""
    self.subscribers.append(callback)

async def _notify_subscribers(self, action, entry):
    """通知所有订阅者"""
    for callback in self.subscribers:
        await callback(action, entry)
```

### 事件类型

| 事件 | 触发时机 |
|------|----------|
| `add` | 添加新条目 |
| `update` | 更新条目 |
| `remove` | 删除条目 |

---

## 📊 演示结果分析

### 执行流程

```
分析员 → 规划师 → 执行者 → 验证者 → 总结者
    ↓        ↓        ↓        ↓        ↓
  fact →   plan  → result →  fact  → result
```

### 黑板最终状态

```
优先级排序:
1. [result] 任务总结 (优先级:15)
2. [plan]   执行计划 (优先级:10)
3. [result] 执行结果 (优先级:8)
4. [fact]   验证结果 (优先级:7)
5. [fact]   问题分析 (优先级:5)
```

---

## ⚡ 黑板模式的优势

### 优点

| 特性 | 说明 |
|------|------|
| **解耦** | Agent 之间不直接通信 |
| **共享知识** | 所有 Agent 访问同一知识库 |
| **灵活扩展** | 可随时添加新 Agent |
| **容错性** | 单个 Agent 失败不影响整体 |
| **可追溯** | 完整的决策历史记录 |

### 适用场景

- 🤝 多专家协作系统
- 🔬 知识密集型任务
- 📋 复杂问题分解
- 🔄 迭代式问题解决

---

## 🔧 关键实现细节

### 线程安全

```python
async def add_entry(self, content, ...):
    async with self.lock:
        # 原子操作
        self.entries[entry_id] = entry
        await self._notify_subscribers("add", entry)
```

### 优先级系统

```python
def get_all_entries(self):
    # 按优先级降序，时间戳降序
    return sorted(entries, key=lambda x: (-x.priority, -x.timestamp))
```

---

## 📝 总结

### 黑板模式核心要点

1. **共享存储**：所有 Agent 访问同一个黑板
2. **异步通信**：通过订阅-通知机制
3. **角色分工**：不同 Agent 负责不同任务
4. **知识积累**：信息持久化在黑板上

### 与其他模式对比

| 模式 | 通信方式 | 耦合度 | 适用场景 |
|------|---------|--------|----------|
| 黑板模式 | 共享存储 | 低 | 知识密集型 |
| 信箱模式 | 点对点 | 中 | 私密通信 |
| 广播模式 | 一对多 | 低 | 通知场景 |

### 下一步

接下来学习 **L4-02: Mailbox（信箱模式）**，了解点对点异步通信机制。