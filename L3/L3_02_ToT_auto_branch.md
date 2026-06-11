# Tree of Thoughts (ToT) - 自动分支策略版

## 📋 概述

这是 Tree of Thoughts (ToT) 推理框架的**自动分支策略版本**，在基础全分支策略之上，实现了基于分支质量评估的动态分支数调整机制。

**核心特点**：根据每个思考分支的评估分数，自动决定下一步探索的分支数量。

---

## 🚀 核心特性：自动分支策略

### 策略原理

自动分支策略的核心思想是：**根据当前分支的质量动态调整探索广度**。

| 场景 | 条件 | 分支数决策 | 原因 |
|------|------|-----------|------|
| **简单问题** | 存在高分分支 (>=8.0) | 减少分支数 | 已有明确最优路径 |
| **中等问题** | 平均分中等 (5.0-8.0) | 中等分支数 | 保持平衡探索 |
| **困难问题** | 平均分较低 (<3.0) | 增加分支数 | 需要更多探索 |

### 分支因子计算逻辑

```python
def _calculate_dynamic_branching_factor(self, scores):
    avg_score = sum(scores) / len(scores)
    max_score = max(scores)
    
    if max_score >= 8.0:
        # 有高分分支，聚焦最优路径
        high_count = sum(1 for s in scores if s >= 8.0)
        return min(max(1, high_count), 5)
    
    elif avg_score >= 5.0:
        # 中等分数，平衡探索
        return 3
    
    elif avg_score < 3.0:
        # 低分数，增加探索
        return 5
    
    else:
        return 3
```

### 决策流程图

```
评估分支分数
    ↓
有分支 >= 8.0 ?
    ├─ 是 → 分支数 = 高分分支数量（最多5个）
    └─ 否 → 平均分 >= 5.0 ?
                 ├─ 是 → 分支数 = 3
                 └─ 否 → 平均分 < 3.0 ?
                              ├─ 是 → 分支数 = 5
                              └─ 否 → 分支数 = 3
```

---

## 🧹 分支过滤机制

### 低质量分支过滤

```python
def _filter_promising_branches(self, thoughts, scores):
    # 移除分数 < 2.0 的低质量分支
    filtered = [(t, s) for t, s in zip(thoughts, scores) if s >= 2.0]
    
    # 确保至少保留最小分支数
    if len(filtered) < self.min_branching_factor:
        filtered = sorted(zip(thoughts, scores), key=lambda x: -x[1])[:self.min_branching_factor]
    
    return filtered
```

### 过滤规则

| 规则 | 阈值 | 说明 |
|------|------|------|
| 质量阈值 | >= 2.0 | 低于此分数的分支被移除 |
| 最小保留 | min_branching_factor | 确保至少保留指定数量的分支 |

---

## ⚙️ 参数说明

| 参数 | 默认值 | 类型 | 说明 |
|------|-------|------|------|
| `min_branching_factor` | 1 | int | 最小分支数 |
| `max_branching_factor` | 5 | int | 最大分支数 |
| `max_depth` | 3 | int | 最大搜索深度 |

### 阈值配置

```python
self.thresholds = {
    "high": 8.0,    # 高分阈值
    "medium": 5.0,  # 中等分数阈值
    "low": 3.0      # 低分阈值
}
```

---

## 🔄 执行流程

```
用户提问
    ↓
生成初始思考方向（使用 max_branching_factor）
    ↓
评估所有分支
    ↓
过滤低质量分支（<2.0）
    ↓
计算动态分支因子
    ↓
选择 Top-K 分支执行
    ↓
递归处理下一层
    ↓
找到最优路径
    ↓
生成最终答案
```

---

## 🧪 测试结果

### 测试用例

| 测试 | 问题 | 结果 | 动态分支数 |
|------|------|------|-----------|
| 测试1 | 地理计算问题 | ✅ 地球直径是月球的约3.669倍 | 3 |
| 测试2 | 编程语言问题 | ✅ Python最先被创建 | 4 |
| 测试3 | 圆面积计算 | ✅ 面积78.5平方厘米 | 3 |

### 与基础版对比

| 特性 | 基础版（全分支） | 自动分支版 |
|------|----------------|-----------|
| 分支数 | 固定（如3） | 动态（1-5） |
| 资源消耗 | 固定 | 自适应 |
| 简单问题 | 固定3分支 | 减少到1-2分支 |
| 困难问题 | 固定3分支 | 增加到5分支 |
| 效率 | 固定 | 动态优化 |

---

## 📁 文件结构

```
L3/
├── L3_01_ToT.py              # 基础版（全分支策略）
├── L3_02_ToT_auto_branch.py  # 自动分支策略版（本文件）
├── L3_02_ToT_auto_branch.md  # 本说明文档
├── L3_03_ToT_optimized.py    # 优化版（剪枝+早停+衰减）
└── L3_03_ToT_optimized.md    # 优化版说明文档
```

---

## 🎯 使用方法

```python
from L3_02_ToT_auto_branch import TreeOfThoughtsAutoBranch

# 创建自动分支策略 ToT 实例
tot = TreeOfThoughtsAutoBranch(
    min_branching_factor=1,
    max_branching_factor=5,
    max_depth=3
)

# 解决问题
result = await tot.solve("你的问题")
print(result)

# 关闭客户端
await tot.close()
```

---

## 🔧 核心类与方法

### TreeOfThoughtsAutoBranch 类

| 方法 | 功能 |
|------|------|
| `__init__()` | 初始化参数和阈值 |
| `solve(question)` | 主推理入口 |
| `_calculate_dynamic_branching_factor()` | 动态计算分支数 |
| `_filter_promising_branches()` | 过滤低质量分支 |
| `_generate_thoughts()` | 生成思考方向 |
| `_evaluate_branches()` | 评估分支质量 |
| `_decide_action()` | 决定执行动作 |
| `_execute_action()` | 执行工具 |
| `_find_best_path()` | 寻找最优路径 |
| `close()` | 清理资源 |

---

## ⚡ 优化效果

### 优势

1. **效率提升**：简单问题快速收敛，避免不必要的分支探索
2. **探索充分**：困难问题自动增加分支，确保充分探索
3. **资源优化**：根据问题难度动态分配计算资源
4. **质量过滤**：自动剔除低质量分支，减少噪音

### 适用场景

| 场景 | 推荐使用 |
|------|---------|
| 简单事实问题 | ✅ 自动分支（快速收敛） |
| 复杂推理问题 | ✅ 自动分支（充分探索） |
| 资源受限环境 | ✅ 自动分支（资源优化） |
| 需要固定行为 | ❌ 基础版更合适 |

---

## 📝 版本对比

| 版本 | 分支策略 | 核心特性 | 适用场景 |
|------|---------|---------|---------|
| L3_01_ToT.py | 全分支（固定） | 固定分支数 | 教学、演示 |
| L3_02_ToT_auto_branch.py | 自动分支（动态） | 动态分支数 | 实际应用 |
| L3_03_ToT_optimized.py | 优化策略 | 剪枝+早停+衰减 | 高性能场景 |