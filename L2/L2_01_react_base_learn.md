# L2-01: ReAct 基础（Reasoning + Acting）

对应代码：[L2_01_react_base.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L2/L2_01_react_base.py)

---

## 1. 什么是 ReAct

ReAct = **Reasoning（推理）+ Acting（行动）** 交替进行的范式。
它是单 Agent 最核心的工作模式，让模型像人一样"边想边做"：

```
想（Thought）→ 做（Action）→ 看结果（Observation）→ 再想 → ... → 最终答案
```

对比 L1-03 的单次函数调用：
- L1-03：模型决定调用一次工具 → 拿结果 → 回复（一锤子买卖）
- L2-01：**把这个过程放进循环**，模型可以连续多步推理和调用工具，直到解决问题

---

## 2. ReAct 的输出格式

本节用**纯文本 + 正则解析**实现（最原始、最能看清本质）：

```
Thought: 我需要先搜索法国的最新GDP数据
Action: search("法国2024年GDP")
```

或者推理完成时：

```
Thought: 我已经有足够信息了
Final Answer: 法国2024年GDP增长率约为...
```

三种关键标记：
| 标记 | 含义 |
|------|------|
| `Thought:` | 模型的推理过程 |
| `Action:` | 要调用的工具 `tool_name(args)` |
| `Final Answer:` | 推理结束，给出最终答案 |

---

## 3. 解析器（parse_react_step）

用正则把模型的文本输出拆成结构化字段：

```python
# 提取 Thought
thought_match = re.search(r"Thought:\s*(.+?)(?=\nAction:|\nFinal Answer:|$)",
                          model_output, re.DOTALL)
# 提取 Action: tool_name(args)
action_match = re.search(r'Action:\s*(\w+)\(\s*(?:"([^"]+)"|(...))\s*\)', model_output)
# 提取 Final Answer
answer_match = re.search(r"Final Answer:\s*(.+)", model_output, re.DOTALL)
```

> **痛点**：正则解析非常脆弱。模型只要格式稍有偏差（多个空格、换行、引号），就解析失败。这正是 L2-02 引入 JSON Mode 的原因。

---

## 4. ReAct 主循环（最核心）

```python
async def react_agent_loop(user_query, max_steps=5):
    messages = [{"role": "system", "content": "...ReAct格式说明..."},
                {"role": "user", "content": user_query}]

    for step in range(1, max_steps + 1):
        # 1. 调用模型
        model_output = ...
        # 2. 解析 ReAct 格式
        parsed = parse_react_step(model_output)
        # 3. Thought 加入历史
        # 4. 如果有 Final Answer → 结束返回
        if parsed["final_answer"]:
            return parsed["final_answer"]
        # 5. 执行 Action，把 Observation 塞回历史
        tool_result = TOOLS[tool_name](tool_args)
        messages.append({"role": "user", "content": f"Observation: {tool_result}"})
```

### 关键设计点

| 点 | 说明 |
|----|------|
| **max_steps** | 防止无限循环，到达上限强制停止 |
| **Observation 用 user 角色** | 模拟"环境反馈"塞回对话，让模型看到工具结果 |
| **temperature=0.1** | 推理任务要稳定，降低随机性 |

---

## 5. 工具集

本节定义了 3 个模拟工具：

```python
TOOLS = {
    "search": search_tool,            # 模拟搜索（mock 数据）
    "calculator": calculator_tool,    # eval 计算表达式
    "get_current_time": get_current_time
}
```

> ⚠️ `calculator_tool` 用了 `eval`，虽然限制了 `__builtins__`，但生产环境仍有风险（见 L6-05 工具护栏）。

---

## 6. 小结

- ReAct = 推理 + 行动的循环，是单 Agent 的核心范式
- 本节用纯文本 + 正则实现，能看清最底层机制
- **正则解析很脆弱** → 引出 L2-02 的 JSON Mode 方案
- 一次工具调用（L1-03）放进循环 = ReAct（L2-01）
