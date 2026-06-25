# L1-03: 函数调用（Function Calling / Tool Use）

对应代码：[L1_03_function_calling.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L1/coding/L1_03_function_calling.py)

---

## 1. 核心思想

Function Calling 是 Agent 能"行动"的关键。它让 LLM 从"只会聊天"变成"能调用外部工具"：

```
LLM 本身不能查天气/查数据库/发邮件，
但它能"决定"要调用哪个工具、传什么参数，
由我们的代码真正执行，再把结果喂回去。
```

---

## 2. 工具定义（Tools Schema）

用 JSON Schema 描述工具，让模型"知道"有哪些工具可用：

```python
TOOLS_SCHEMA = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "用于查询天气",          # 模型靠它判断何时调用
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "要查询的天气地点"}
            },
            "required": ["location"]              # 必填参数
        }
    }
}]
```

> `description` 写得越清楚，模型越能准确判断"什么时候该调用这个工具、参数怎么填"。

---

## 3. 完整的 5 步闭环

这是 Function Calling 最重要的部分，也是后续 ReAct 的雏形：

```
① 带 tools 调用模型      → 模型决定是否调用工具
② 解析 tool_calls       → 拿到 function_name + arguments
③ 本地执行函数          → result = get_weather(location="北京")
④ 把结果塞回 messages   → 追加 assistant(tool_calls) + tool(result)
⑤ 再次调用模型          → 模型基于工具结果生成最终自然语言回复
```

代码对应：

```python
# ① 模型决定是否调用工具
response = await chat_completion_with_tools(messages, TOOLS_SCHEMA)

# ② 解析模型返回的 tool_calls
function_name, args = parse_tool_calls(response)

# ③ 执行本地函数
result = get_weather(**args)

# ④ 把"模型的调用请求"和"工具结果"都塞回对话历史
messages.append({
    "role": "assistant", "content": None,
    "tool_calls": response["choices"][0]["message"]["tool_calls"]
})
messages.append({
    "role": "tool",
    "tool_call_id": response["choices"][0]["message"]["tool_calls"][0]["id"],
    "content": result
})

# ⑤ 再次调用，生成最终回复
final_response = await chat_completion_with_tools(messages, TOOLS_SCHEMA)
```

---

## 4. 关键字段说明

| 字段 | 作用 |
|------|------|
| `tool_choice: "auto"` | 让模型自己决定是否调用工具（也可强制指定） |
| `tool_calls` | 模型返回的"调用意图"，含工具名和参数 |
| `tool_call_id` | 每次调用的唯一 ID，回填结果时必须对应 |
| `role: "tool"` | 专门承载工具执行结果的消息角色 |

---

## 5. 为什么参数是字符串需要 json.loads

模型返回的 `arguments` 是一个 **JSON 字符串**（不是字典），必须解析：

```python
arguments_dict = json.loads(tool_call["function"]["arguments"])
```

---

## 6. 从 Function Calling 到 ReAct

L1-03 的"5步闭环"做一次就停了。如果把它放进一个循环里——
**模型可以连续调用多个工具，直到任务完成**——就是 L2 的 ReAct。

```
单次工具调用（L1-03）  →  循环工具调用 + 推理（L2 ReAct）
```

---

## 7. 小结

- 模型出"调用意图"，代码执行，结果回填，再调一次 = 5步闭环
- `tool_call_id` 必须对应，`role:tool` 承载工具结果
- 这是 L2 ReAct 的核心机制，也是 L6 工具护栏的保护对象
