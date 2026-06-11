# L3-02: Graph of Thoughts (GoT) 学习笔记

## 📋 概述

**Graph of Thoughts (GoT)** 是一种比 Tree of Thoughts 更灵活的推理框架。它将推理过程建模为一个**有向图**，而不是严格的树形结构。

### GoT vs ToT 的核心区别

| 特性 | Tree of Thoughts | Graph of Thoughts |
|------|-----------------|------------------|
| 结构 | 树结构 | 图结构 |
| 路径 | 严格层次化 | 任意连接 |
| 回溯 | 有限 | 灵活回溯 |
| 复杂度 | 较低 | 较高 |
| 灵活性 | 受限 | 高度灵活 |

---

## 🚀 GoT 核心概念

### 1. 图节点类型

```python
class NodeType(Enum):
    INPUT = "input"     # 输入节点（问题）
    THOUGHT = "thought" # 思考节点
    ACTION = "action"   # 行动节点
    RESULT = "result"   # 结果节点
    ANSWER = "answer"   # 答案节点
    REFLECT = "reflect" # 反思节点
```

### 2. 节点数据结构

```python
@dataclass
class GraphNode:
    node_id: str           # 节点唯一标识
    node_type: NodeType    # 节点类型
    content: str           # 节点内容
    score: float = 0.0     # 评估分数
    visited: bool = False  # 是否已访问
    timestamp: float       # 创建时间
    metadata: Dict         # 元数据
```

### 3. 边数据结构

```python
@dataclass
class Edge:
    from_node_id: str       # 起始节点
    to_node_id: str         # 目标节点
    label: Optional[str]    # 边的标签（如 "thought", "action"）
    weight: float = 1.0     # 边的权重
    directed: bool = True   # 是否有向
```

---

## 🔄 GoT 执行流程

### 完整推理流程

```
用户提问
    ↓
创建 INPUT 节点
    ↓
┌─────────────────────────────────────────────────────┐
│              BFS 图遍历循环                        │
├─────────────────────────────────────────────────────┤
│  for each node in queue:                           │
│      ├─ 生成多个思考方向 → 创建 THOUGHT 节点       │
│      ├─ 评估思考节点质量                          │
│      ├─ 决定行动 → 创建 ACTION 节点              │
│      ├─ 执行工具 → 创建 RESULT 节点              │
│      ├─ 如果无需工具 → 创建 ANSWER 节点          │
│      └─ 反思推理路径 → 决定是否继续              │
└─────────────────────────────────────────────────────┘
    ↓
寻找最优路径（DFS）
    ↓
生成最终答案
```

### 关键步骤详解

#### Step 1: 生成思考

```python
def _generate_thoughts(context, question, num_thoughts=4):
    # 根据上下文生成多个思考方向
    # 使用较高温度 (0.8) 鼓励多样性
```

#### Step 2: 评估节点

```python
def _evaluate_nodes(node_ids, question):
    # 评估每个节点的质量和有用性
    # 返回 0-10 分的评分
```

#### Step 3: 决定行动

```python
def _decide_action(thought, context):
    # 决定是否调用工具
    # 或直接生成答案
```

#### Step 4: 反思机制

```python
def _reflect_on_path(path, question):
    # 反思当前推理路径是否正确
    # 决定是否继续搜索或回溯
```

---

## 🧪 测试结果

### 测试用例

| 测试 | 问题 | 结果 |
|------|------|------|
| 测试1 | 地球直径是月球直径的几倍？ | ✅ 约3.67倍 |
| 测试2 | 中国和印度哪个人口更多？ | ✅ 印度多约3000万 |
| 测试3 | 光从地球到月球需要多长时间？ | ❌ 未找到解决方案 |

### 测试1 详细输出

```
最优路径:
  0. [input] 地球的半径是6371公里...
  1. [thought] 或许需要比较直径，地球直径=2×6371=12742公里...
  2. [answer] Final Answer: 倍数为12742/3474≈3.67
```

---

## ⚡ GoT 的优势

### 1. 灵活性

- 节点之间可以任意连接
- 支持跳转到图中的任意节点
- 不受严格层次结构限制

### 2. 回溯能力

- 可以从任意节点重新开始
- 支持多次反思和调整
- 避免陷入局部最优

### 3. 并行探索

- 多个路径可以同时探索
- 支持异步评估和比较
- 提高推理效率

### 4. 动态扩展

- 根据需要动态添加节点
- 节点可以有多个前驱和后继
- 更接近人类思维模式

---

## 🔧 核心类与方法

### GraphOfThoughts 类

| 方法 | 功能 |
|------|------|
| `__init__()` | 初始化参数 |
| `solve(question)` | 主推理入口 |
| `_create_node()` | 创建新节点 |
| `_add_edge()` | 添加边 |
| `_get_neighbors()` | 获取邻居节点 |
| `_get_predecessors()` | 获取前驱节点 |
| `_generate_thoughts()` | 生成思考方向 |
| `_evaluate_nodes()` | 评估节点质量 |
| `_decide_action()` | 决定行动 |
| `_execute_action()` | 执行工具 |
| `_reflect_on_path()` | 反思路径 |
| `_find_best_path()` | 寻找最优路径 |
| `close()` | 清理资源 |

---

## 📊 GoT vs ToT 对比

### 结构对比

```
Tree of Thoughts:              Graph of Thoughts:

    问题                          问题
      │                            │
    ┌─┴─┐                        ┌─┴─┐
    │ │ │                        │ │ │
   思考 思考 思考               思考 思考 思考
    │   │   │                     │\  │ /
   行动 行动 行动                 │ \ │/
    │   │   │                    行动──行动
   结果 结果 结果                   │  │
    │   │   │                   结果 结果
    └─┬─┴─┬─┘                    │  │
      └───┘                      └──┘
        │                         │
      答案                       答案
```

### 特性对比

| 特性 | ToT | GoT |
|------|-----|-----|
| 结构类型 | 树 | 图 |
| 路径限制 | 层次化 | 任意 |
| 回溯能力 | 有限 | 灵活 |
| 复杂度 | O(b^d) | O(n^2) |
| 内存消耗 | 较低 | 较高 |
| 适用场景 | 简单推理 | 复杂推理 |

---

## 🎯 使用建议

### 何时使用 GoT

1. **复杂推理问题**：需要多步骤、多方向探索
2. **需要回溯**：可能需要返回修改之前的决策
3. **创意生成**：需要发散性思维
4. **多模态推理**：结合多种工具和信息源

### 何时使用 ToT

1. **简单问题**：直接可以得出答案
2. **资源受限**：内存或时间有限
3. **教学演示**：逻辑清晰，易于理解

---

## 🔬 扩展方向

1. **图可视化**：使用 NetworkX 或 PyVis 可视化推理图
2. **并行处理**：同时评估多个路径
3. **强化学习**：使用奖励机制优化路径选择
4. **记忆机制**：保存和重用推理图
5. **多智能体协作**：多个 GoT 协作解决问题

---

## 📝 总结

Graph of Thoughts 是 Tree of Thoughts 的自然扩展，通过将推理过程建模为图结构，提供了更高的灵活性和更强的推理能力。虽然复杂度更高，但在处理复杂问题时表现更出色。