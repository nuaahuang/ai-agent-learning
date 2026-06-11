# Tree of Thoughts (ToT) 优化版

## 📋 概述

这是一个优化版的 Tree of Thoughts (ToT) 推理框架，在基础版本之上增加了三大核心优化特性：

1. **🔪 优化剪枝策略** - 动态过滤低质量分支
2. **⚡ 早停机制** - 提前终止无效搜索
3. **📉 路径评分衰减** - 考虑深度和历史因素

---

## 🚀 特性详解

### 1. 优化剪枝策略

#### 1.1 质量阈值剪枝
- 设置剪枝阈值（默认 2.0），自动移除分数低于阈值的分支
- 确保至少保留最小分支数，避免过度剪枝

#### 1.2 兄弟节点竞争剪枝
- 比较兄弟节点的分数
- 移除分数低于最高分 40% 的劣势分支
- 保持搜索聚焦于高质量路径

```python
def _filter_promising_branches(self, thoughts, scores):
    # 移除低质量分支
    filtered = [(t, s) for t, s in zip(thoughts, scores) if s >= 2.0]
    
    # 保持最小分支数
    if len(filtered) < self.min_branching_factor:
        filtered = sorted(zip(thoughts, scores), key=lambda x: -x[1])[:self.min_branching_factor]
```

---

### 2. 早停机制 (Early Stopping)

#### 触发条件

| 条件 | 阈值 | 说明 |
|------|------|------|
| 高分路径 | >= 9.0 | 找到高质量路径时提前终止 |
| 低质量收敛 | < 3.0 且深度 >= max_depth-1 | 避免无效搜索 |

#### 效果
- 简单问题一步解决，无需完整遍历
- 减少不必要的 API 调用
- 显著提升推理效率

---

### 3. 路径评分衰减

#### 衰减公式

```
path_score = current_score × (decay_factor ^ depth) + parent.path_score × 0.3
```

#### 参数说明
- **decay_factor**: 深度衰减因子（默认 0.9）
- **depth**: 当前节点深度
- **parent.path_score**: 父节点路径分数的 30% 继承

#### 设计意图
- 偏好较短的推理路径
- 继承历史路径质量
- 避免过度深入低质量分支

---

## ⚙️ 可调参数

| 参数 | 默认值 | 类型 | 说明 |
|------|-------|------|------|
| `min_branching_factor` | 1 | int | 最小分支数 |
| `max_branching_factor` | 5 | int | 最大分支数 |
| `max_depth` | 3 | int | 最大搜索深度 |
| `early_stop_threshold` | 9.0 | float | 早停阈值 |
| `decay_factor` | 0.9 | float | 深度衰减因子 |
| `pruning_threshold` | 2.0 | float | 剪枝阈值 |

---

## 🧪 测试结果

### 测试用例

| 测试 | 问题 | 结果 | 早停 | 路径分数 |
|------|------|------|------|---------|
| 测试1 | 地球直径是月球直径的几倍？ | ✅ 约3.67倍 | ⚡ 是 | 9.00 |
| 测试2 | 中国和印度哪个人口更多？ | ✅ 印度多约1600万 | ⚡ 是 | 9.00 |
| 测试3 | 半径5厘米的圆面积是多少？ | ✅ 78.5平方厘米 | ⚡ 是 | 10.00 |

### 性能对比

| 指标 | 基础版 | 优化版 |
|------|-------|-------|
| 简单问题步数 | 3步 | 1步 |
| API调用次数 | 固定 | 动态减少 |
| 资源消耗 | 固定 | 自适应 |

---

## 📁 文件结构

```
L3/
├── L3_01_ToT.py              # 基础版（全分支策略）
├── L3_02_ToT_auto_branch.py  # 自动分支策略版
├── L3_03_ToT_optimized.py    # 优化版（剪枝+早停+衰减）
└── L3_03_ToT_optimized.md    # 本说明文档
```

---

## 🎯 使用方法

```python
from L3_03_ToT_optimized import TreeOfThoughtsOptimized

# 创建优化版 ToT 实例
tot = TreeOfThoughtsOptimized(
    min_branching_factor=1,
    max_branching_factor=5,
    max_depth=3,
    early_stop_threshold=9.0,
    decay_factor=0.9,
    pruning_threshold=2.0
)

# 解决问题
result = await tot.solve("你的问题")
print(result)

# 关闭客户端
await tot.close()
```

---

## 🔧 核心类与方法

### TreeOfThoughtsOptimized 类

| 方法 | 功能 |
|------|------|
| `__init__()` | 初始化参数和阈值 |
| `solve(question)` | 主推理入口 |
| `_calculate_dynamic_branching_factor()` | 动态计算分支数 |
| `_filter_promising_branches()` | 剪枝低质量分支 |
| `_calculate_path_score()` | 计算路径分数（含衰减） |
| `_check_early_stop()` | 检查早停条件 |
| `_find_best_path()` | 寻找最优路径 |
| `close()` | 清理资源 |

---

## ⚡ 优化效果总结

1. **效率提升**：简单问题快速收敛
2. **资源节省**：避免无效搜索
3. **质量保证**：过滤低质量分支
4. **深度感知**：考虑搜索深度的评分机制

---

## 📝 版本历史

| 版本 | 特性 | 日期 |
|------|------|------|
| v1.0 | 基础全分支策略 | - |
| v2.0 | 自动分支策略 | - |
| v3.0 | 剪枝+早停+路径衰减 | 2026-06-11 |