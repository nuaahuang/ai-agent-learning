# L2-02: JSON Mode + ReAct（结构化的 ReAct）

对应代码：[L2_02_react_jsonmode.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L2/L2_02_react_jsonmode.py)

---

## 1. 为什么要用 JSON Mode

L2-01 用正则解析模型的文本输出，问题很明显：

| 问题 | 表现 |
|------|------|
| 格式脆弱 | 模型多个空格/换行/引号，正则就匹配失败 |
| 难维护 | 正则越写越复杂，难以覆盖所有情况 |
| 不可靠 | 复杂 Action 参数难以用正则准确提取 |

**JSON Mode 把"格式约束"交给模型本身**：让模型直接输出结构化 JSON，
配合 Pydantic 验证，做到 **100% 可解析，零正则**。

---

## 2. 用 Pydantic 定义输出结构

```python
class Action(BaseModel):
    name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")

class ReActStep(BaseModel):
    """ReAct 单步输出的结构化格式"""
    thought: str = Field(..., description="推理过程")
    action: Optional[Action] = Field(None, description="要执行的动作，不需要则为null")
    final_answer: Optional[str] = Field(None, description="最终答案，有则结束")
```

Pydantic 的好处：
- 自动**类型校验**（字段类型不对会报错）
- 自动**解析**（dict → 对象）
- 字段的 `description` 还能写进 prompt 帮助模型理解

---

## 3. 系统提示词约定 JSON 格式

prompt 里明确告诉模型输出什么结构：

```json
{
  "thought": "你的推理过程",
  "action": {"name": "工具名称", "arguments": {}},
  "final_answer": null
}
```

并强调规则：
1. `action` 和 `final_answer` 不能同时非空
2. 需要工具时设 `action`，`final_answer` 设 null
3. 不需要工具时设 `final_answer`，`action` 设 null
4. 工具参数必须是字典格式

---

## 4. 主循环（JSON 版）

和 L2-01 主循环结构一样，区别在解析部分：

```python
# L2-01: 正则解析（脆弱）
parsed = parse_react_step(model_output)

# L2-02: JSON + Pydantic（健壮）
parsed_json = json.loads(model_output)
react_step = ReActStep(**parsed_json)   # Pydantic 自动校验
```

执行 Action 时根据工具名分发参数：

```python
if action.name == "search":
    result = tool_func(action.arguments.get("query", ""))
elif action.name == "calculator":
    result = tool_func(action.arguments.get("expression", ""))
elif action.name == "get_current_time":
    result = tool_func()
```

---

## 5. L2-01 vs L2-02 对比

| 维度 | L2-01（正则） | L2-02（JSON Mode） |
|------|--------------|-------------------|
| 输出格式 | 纯文本 Thought/Action | JSON 对象 |
| 解析方式 | 正则表达式 | json.loads + Pydantic |
| 可靠性 | 脆弱，易失败 | 100% 可解析 |
| 参数表达 | 难表达复杂参数 | 天然支持嵌套字典 |
| 可维护性 | 差 | 好 |

---

## 6. 小结

- JSON Mode 把格式约束交给模型，彻底告别脆弱的正则
- Pydantic 提供类型校验 + 自动解析，工程上更可靠
- 这是生产级 Agent 的标准做法，后续 L2-03/L2-04 都基于它
- 注意：用 JSON Mode 时 prompt 必须明确说明字段结构
