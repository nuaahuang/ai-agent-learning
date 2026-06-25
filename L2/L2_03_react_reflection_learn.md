# L2-03: Reflection（自我反思机制）

对应代码：[L2_03_react_reflection.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L2/L2_03_react_reflection.py)

---

## 1. 什么是 Reflection

Reflection（反思）让 Agent 具备**自我检查、自我纠错**的能力：
不再"想完做完就直接交付"，而是在每个结果产出后，再用一个"审查者"角色去验证。

```
ReAct 产出结果  →  Reflection 审查  →  正确则通过 / 错误则修正 → 二次验证
```

类比人类：写完答案后，再回头检查一遍有没有算错、有没有答非所问。

---

## 2. 为什么需要 Reflection

LLM 常见问题：
| 问题 | 示例 |
|------|------|
| 计算错误 | 运算优先级搞错 |
| 答非所问 | 没理解用户真实意图 |
| 信息遗漏 | 多步问题只答了一部分 |
| 幻觉 | 编造不存在的信息 |

Reflection 能在交付前**拦截这些错误**，显著提升答案可靠性。

---

## 3. 双角色设计

本节用两套 prompt 模拟两个角色（同一个模型扮演）：

| 角色 | prompt | 职责 |
|------|--------|------|
| **执行者** | system_prompt | 按 ReAct 推理、调用工具、给答案 |
| **审查者** | reflection_prompt | 检查结果是否正确、合理、完整 |

Reflection 的输出也是结构化的：

```python
class ReflectionResult(BaseModel):
    is_correct: bool                              # 结果是否正确
    reason: str                                   # 判断理由
    corrected_action: Optional[Action]            # 修正的动作（可选）
    corrected_final_answer: Optional[str]         # 修正的答案（可选）
```

---

## 4. 反思发生在两个时机

### 时机一：模型直接给出 Final Answer 后

```python
if react_step.final_answer:
    # Phase 2: 反思验证这个答案
    reflection_result = 审查(final_answer)
    if reflection_result.is_correct:
        return final_answer            # 通过
    else:
        # 用 corrected_final_answer 修正，再做 Phase 3 二次验证
```

### 时机二：每次 Action 执行得到 Observation 后

```python
result = tool_func(...)               # 执行工具
# Phase 2: 反思这个 Observation 是否合理
reflection_result = 审查(action, result)
if not reflection_result.is_correct and reflection_result.corrected_action:
    # 执行修正后的 Action
    corrected_result = TOOLS[corrected_action.name](...)
```

---

## 5. 多级验证（Phase 2 → Phase 3）

为了避免"修正后仍然错误"，本节设计了**二次验证**：

```
答案 → Phase 2 审查 → 不通过 → 给出修正答案
                              → Phase 3 二次审查修正答案
                              → 通过则返回 / 不通过继续循环
```

这种"修正 + 再验证"的闭环，是 Reflection 的精髓。

---

## 6. 关键参数

| 参数 | 作用 |
|------|------|
| `max_steps` | ReAct 最大步数 |
| `max_reflections` | 每步最多反思次数（防止反思死循环） |

> 反思也是有成本的：每次反思都是一次额外的 LLM 调用。要在"质量"和"成本/延迟"之间权衡。

---

## 7. 小结

- Reflection = Agent 的自我检查与纠错能力
- 双角色（执行者 + 审查者），都用结构化 JSON 输出
- 反思发生在两个时机：给出答案后、Action 执行后
- 设计了"修正 + 二次验证"闭环，提升可靠性
- 代价是额外的 LLM 调用，需权衡质量与成本
