# Tree of Thoughts (ToT) - 基础版

## 📋 概述

这是 Tree of Thoughts (ToT) 推理框架的**基础版本**，实现了经典的全分支搜索策略。

**核心特点**：使用固定的分支因子进行广度优先搜索，适合教学和演示目的。

---

## 🚀 核心概念

### Tree of Thoughts 原理

Tree of Thoughts 是一种让大语言模型进行**深思熟虑**推理的框架。它将推理过程建模为一棵搜索树：

| 节点类型 | 说明 |
|---------|------|
| **ROOT** | 根节点，代表原始问题 |
| **THOUGHT** | 思考节点，代表一个推理步骤 |
| **ACTION** | 行动节点，代表工具调用 |
| **RESULT** | 结果节点，代表工具执行结果 |
| **ANSWER** | 答案节点，代表最终结论 |

### 搜索策略

基础版采用**固定分支因子的广度优先搜索**：

```
问题 (ROOT)
    ├─ 思考1 ── 行动1 ── 结果1
    ├─ 思考2 ── 行动2 ── 结果2
    └─ 思考3 ── 行动3 ── 结果3
            ├─ 思考3.1 ── 行动3.1 ── 结果3.1
            └─ 思考3.2 ── 行动3.2 ── 结果3.2
```

---

## 🔄 执行流程

### 完整推理流程

```
用户提问
    ↓
创建根节点 (ROOT)
    ↓
┌─────────────────────────────────────────────────────────┐
│                    BFS 遍历循环                         │
├─────────────────────────────────────────────────────────┤
│  for each node in current_level:                       │
│      ├─ 生成 branching_factor 个思考方向               │
│      ├─ 评估每个思考的质量 (0-10分)                   │
│      ├─ 选择 Top-K 分支 (K=branching_factor)         │
│      ├─ 为每个分支决定行动 (工具调用或直接推理)        │
│      └─ 执行行动，创建结果节点                        │
└─────────────────────────────────────────────────────────┘
    ↓
找到最优路径 (DFS 回溯)
    ↓
生成最终答案
```

### 关键步骤详解

#### Step 1: 生成思考方向

```python
def _generate_thoughts(context, question):
    # 调用 LLM 生成多个思考方向
    # 使用较高温度 (0.8) 鼓励多样性
```

#### Step 2: 评估分支质量

```python
def _evaluate_branches(branches, question):
    # 调用 LLM 评估每个分支的可行性
    # 返回 0-10 分的评分
```

#### Step 3: 选择 Top-K 分支

```python
top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:branching_factor]
```

#### Step 4: 执行行动

```python
def _execute_action(decision):
    # 根据决策执行工具或直接推理
```

---

## ⚙️ 参数说明

| 参数 | 默认值 | 类型 | 说明 |
|------|-------|------|------|
| `branching_factor` | 3 | int | 每个节点的分支数（固定） |
| `max_depth` | 3 | int | 最大搜索深度 |

### 参数配置建议

| 场景 | branching_factor | max_depth | 说明 |
|------|-----------------|-----------|------|
| 简单问题 | 2-3 | 2-3 | 快速解决 |
| 中等问题 | 3-5 | 3-4 | 平衡探索 |
| 复杂问题 | 5-7 | 4-5 | 充分探索 |

---

## 🧰 工具系统

### 可用工具

| 工具名称 | 功能 | 参数 |
|---------|------|------|
| `search` | 搜索信息 | `query: str` |
| `calculator` | 数学计算 | `expression: str` |

### 工具调用流程

```
思考节点
    ↓
决定行动 (_decide_action)
    ↓
执行工具 (_execute_action)
    ↓
创建结果节点 (RESULT)
```

---

## 🧪 测试结果

### 测试用例

| 测试 | 问题 | 结果 |
|------|------|------|
| 测试1 | 地球直径是月球直径的几倍？ | ✅ 约3.67倍 |
| 测试2 | Python、Java和JavaScript哪个最先被创建？ | ✅ Python最先创建 |
| 测试3 | 半径5厘米的圆面积是多少？ | ✅ 78.5平方厘米 |

### 执行示例

```
🌳 Tree of Thoughts 开始推理
问题: 地球的半径是6371公里，月球的半径是1737公里。地球的直径是月球直径的几倍？
分支因子: 3, 最大深度: 3

📊 深度 1: 当前有 1 个节点
  📍 节点 node_1: 地球的半径是6371公里...
  🌱 生成 3 个思考方向...
  📝 评估思考方向...
    [0] 分数=9.0: 地球直径是半径的两倍...
    [1] 分数=8.5: 检查单位是否一致...
    [2] 分数=8.0: 先计算半径比值...
    🔧 为分支 0 决定行动...
      ✅ 结果: 计算结果...

🏆 选择最优路径
最优路径:
  0. [root] 地球的半径是6371公里...
  1. [thought] 地球直径是半径的两倍...
  2. [result] Action: calculator...

🎯 最终答案:
地球的直径是月球直径的约3.67倍。
```

---

## 🎯 使用方法

```python
from L3_01_ToT import TreeOfThoughts

# 创建 ToT 实例（使用默认参数）
tot = TreeOfThoughts(branching_factor=3, max_depth=3)

# 解决问题
result = await tot.solve("你的问题")
print(result)

# 关闭客户端
await tot.close()
```

### 完整示例

```python
import asyncio
from L3_01_ToT import TreeOfThoughts

async def main():
    tot = TreeOfThoughts(branching_factor=3, max_depth=3)
    try:
        result = await tot.solve("地球到月球的距离是多少？")
        print(result)
    finally:
        await tot.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🔧 核心类与方法

### TreeOfThoughts 类

| 方法 | 功能 |
|------|------|
| `__init__(branching_factor, max_depth)` | 初始化参数 |
| `solve(question)` | 主推理入口 |
| `_generate_thoughts(context, question)` | 生成思考方向 |
| `_evaluate_branches(branches, question)` | 评估分支质量 |
| `_decide_action(thought, context)` | 决定执行动作 |
| `_execute_action(decision)` | 执行工具 |
| `_find_best_path()` | 寻找最优路径 |
| `_generate_final_answer(question, path)` | 生成最终答案 |
| `close()` | 清理资源 |

### TreeNode 数据类

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id` | str | 节点唯一标识 |
| `node_type` | NodeType | 节点类型 |
| `content` | str | 节点内容 |
| `score` | float | 评估分数 |
| `parent` | TreeNode | 父节点 |
| `children` | List[TreeNode] | 子节点列表 |

---

## ⚡ 适用场景

| 场景 | 推荐使用 | 原因 |
|------|---------|------|
| ✅ 教学演示 | 是 | 逻辑清晰，易于理解 |
| ✅ 算法学习 | 是 | 基础实现，便于扩展 |
| ✅ 简单问题 | 是 | 固定分支数足够 |
| ❌ 复杂问题 | 否 | 建议使用自动分支版 |
| ❌ 资源受限 | 否 | 建议使用优化版 |

---

## 📝 版本对比

| 版本 | 分支策略 | 复杂度 | 适用场景 |
|------|---------|-------|---------|
| **L3_01_ToT.py** | 固定分支 | 低 | 教学、演示 |
| L3_02_ToT_auto_branch.py | 动态分支 | 中 | 实际应用 |
| L3_03_ToT_optimized.py | 优化策略 | 高 | 高性能场景 |

---

## 🔬 扩展建议

如果你想基于基础版进行扩展，可以考虑以下方向：

1. **动态分支**：根据评估分数调整分支数
2. **剪枝策略**：过滤低质量分支
3. **早停机制**：找到高分路径时提前终止
4. **路径评分衰减**：考虑深度因素
5. **多轮反思**：对结果进行反思验证

这些扩展在后续版本中已有实现，可参考 `L3_02_ToT_auto_branch.py` 和 `L3_03_ToT_optimized.py`。