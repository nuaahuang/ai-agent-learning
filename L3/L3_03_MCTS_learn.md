# L3-03: Monte Carlo Tree Search (MCTS) 学习笔记

## 🎲 什么是 Monte Carlo Tree Search

MCTS 是一种基于随机模拟的启发式搜索算法，特别适合在状态空间巨大、不确定环境中进行决策。

### MCTS 的核心思想

```
传统搜索 vs MCTS

传统搜索（如深度优先）:
  ┌─────────────────────────────┐
  │ 探索所有可能路径            │
  │ 计算量巨大                  │
  │ 无法处理不确定性            │
  └─────────────────────────────┘

MCTS:
  ┌─────────────────────────────┐
  │ 随机模拟探索               │
  │ 基于回报评估路径           │
  │ 动态平衡探索与利用         │
  └─────────────────────────────┘
```

---

## 🔄 MCTS 的四个核心步骤

### 1. Select（选择）

从根节点开始，使用 **UCT 算法**选择最优子节点：

```python
def uct_score(self, exploration_weight: float = 1.414) -> float:
    exploitation = self.wins / self.visits
    exploration = exploration_weight * sqrt(log(parent_visits) / self.visits)
    return exploitation + exploration
```

**UCT 公式**：
- **利用（Exploitation）**：`wins / visits` - 选择已知的好路径
- **探索（Exploration）**：`C * sqrt(log(N) / n)` - 尝试未充分探索的路径

### 2. Expand（扩展）

当到达叶子节点时，生成新的子节点：

```python
async def _expand(self, node, question):
    if node.is_leaf():
        thoughts = await generate_thoughts(context, question)
        for thought in thoughts:
            child_node = create_node(THOUGHT, thought)
            node.add_child(child_node)
```

### 3. Simulate（模拟）

从新扩展的节点进行**随机模拟**，直到到达终止状态：

```python
async def _simulate(self, node, question, depth=0):
    if depth >= max_depth or node.terminal:
        return await evaluate_node(node, question)
    
    # 随机选择子节点继续模拟
    thoughts = await generate_thoughts(context, question)
    thought = random.choice(thoughts)
    return await evaluate_thought(thought, question)
```

### 4. Backpropagate（回溯）

将模拟结果（回报）反向传播到路径上的所有节点：

```python
def _backpropagate(self, node, reward):
    while node is not None:
        node.visits += 1
        node.wins += reward
        node = node.parent
```

---

## 📊 MCTS 算法流程图

```
                     ┌─────────────┐
                     │   根节点    │
                     └──────┬──────┘
                            │
                            ▼
                 ┌─────────────────┐
                 │   Select        │
                 │ (UCT选择最优)   │
                 └──────┬──────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │   到达叶子节点？    │
              └───────┬─────────────┘
                      │
            ┌─────────┴─────────┐
            │ YES               │ NO
            ▼                   ▼
   ┌───────────────┐    ┌─────────────┐
   │   Expand      │    │ 继续Select  │
   │ (扩展新节点)   │    └──────┬──────┘
   └───────┬───────┘           │
           │                   │
           ▼                   │
   ┌───────────────┐           │
   │   Simulate    │◄──────────┘
   │ (随机模拟)     │
   └───────┬───────┘
           │
           ▼
   ┌───────────────┐
   │ Backpropagate │
   │ (回溯更新)     │
   └───────┬───────┘
           │
           ▼
   ┌───────────────┐
   │  重复N次      │
   └───────┬───────┘
           │
           ▼
   ┌───────────────┐
   │ 返回最优路径   │
   └───────────────┘
```

---

## 🧪 测试结果分析

### 测试1：地球体积 vs 月球体积

```
最优路径:
  root → thought → action(calculator) → result(49.34) → thought → answer

关键指标:
  - 根节点访问次数: 30
  - 最优子节点价值: 0.911
  - 计算结果: 49.34倍
```

### 测试2：光从地球到月球的时间

```
最优路径:
  root → thought → action(search) → result(未找到) → thought → answer

关键指标:
  - 根节点访问次数: 30
  - 最优子节点价值: 0.777
  - 答案: 1.2-1.4秒
```

---

## ⚡ MCTS 的特点

### 优点

| 特性 | 说明 |
|------|------|
| **无需完整状态空间** | 不需要预先知道所有可能状态 |
| **自适应探索** | 自动平衡探索与利用 |
| **概率保证** | 理论上收敛到最优解 |
| **并行友好** | 可并行进行多个模拟 |

### 缺点

| 特性 | 说明 |
|------|------|
| **计算量大** | 需要大量模拟 |
| **收敛慢** | 复杂问题需要更多迭代 |
| **依赖模拟质量** | 模拟策略影响结果 |

---

## 🔧 关键参数

### 1. `max_iterations`（最大迭代次数）
- 越大越精确，但计算时间越长
- 推荐值：50-200

### 2. `max_depth`（最大深度）
- 限制搜索深度
- 防止无限递归

### 3. `exploration_weight`（探索权重）
- 默认值：√2 ≈ 1.414
- 越大越倾向探索新路径
- 越小越倾向利用已知好路径

---

## 🤝 MCTS 与其他推理框架对比

| 框架 | 特点 | 适用场景 |
|------|------|----------|
| **ReAct** | 线性推理链 | 简单问题 |
| **ToT** | 树状搜索 | 中等复杂度 |
| **GoT** | 图结构 | 复杂多步骤 |
| **MCTS** | 随机模拟 | 不确定性环境 |

### 选择建议

```
问题复杂度 → 选择框架
    ↓
简单问题 → ReAct
    ↓
中等问题 → ToT
    ↓
复杂问题 → GoT
    ↓
不确定环境 → MCTS
```

---

## 📝 总结

### MCTS 的核心价值

1. **处理不确定性**：在信息不完全的情况下做出决策
2. **动态平衡**：自动调整探索与利用的比例
3. **无需完整知识**：不需要预先知道所有状态

### 适用场景

- 🎮 游戏 AI（围棋、象棋等）
- 🤖 机器人路径规划
- 📈 决策系统
- 🧠 复杂推理问题

### 关键要点

```
MCTS = 随机模拟 + UCT选择 + 回溯更新

核心公式:
UCT = 利用 + 探索
    = (wins/visits) + C * sqrt(log(parent_visits) / visits)
```