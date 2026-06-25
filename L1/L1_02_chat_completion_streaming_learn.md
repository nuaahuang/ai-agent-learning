# L1-02: 流式输出（Streaming）

对应代码：[L1_02_chat_completion_streaming.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L1/coding/L1_02_chat_completion_streaming.py)

---

## 1. 为什么需要流式

非流式：等模型把整段话生成完，才一次性返回 → 用户要干等几秒。
流式：模型生成一个字就推一个字（像打字机）→ 首字响应快、体验好。

---

## 2. 实现要点

请求体多加 `"stream": True`，响应改用 `client.stream(...)` 逐行读取：

```python
async with client.stream(
    "POST", f"{BASE_URL}/chat/completions",
    headers={...},
    json={"model": MODEL, "messages": messages, "stream": True}
) as response:
    async for chunk in response.aiter_lines():
        if chunk.startswith("data:"):
            data_str = chunk.replace("data:", "").strip()
            if data_str == "[DONE]":          # 结束标志
                break
            data_json = json.loads(data_str)
            # 核心：提取增量内容 delta
            delta = data_json["choices"][0]["delta"].get("content", "")
            print(delta, end="", flush=True)
```

---

## 3. SSE 协议（Server-Sent Events）

流式基于 SSE，服务器把数据一行行推过来，格式固定：

```
data: {"choices":[{"delta":{"content":"我"}}]}
data: {"choices":[{"delta":{"content":"是"}}]}
data: {"choices":[{"delta":{"content":"助手"}}]}
data: [DONE]
```

---

## 4. 流式 vs 非流式的关键差异

| 维度 | 非流式 | 流式 |
|------|--------|------|
| 返回字段 | `message.content` | `delta.content`（增量片段） |
| 结束判断 | 一次性返回完 | 收到 `[DONE]` |
| 体验 | 等待整段 | 逐字呈现 |
| 完整内容 | 直接拿到 | 需自己把 delta 拼接起来 |

> 注意：流式下每个 chunk 只是**一小片增量**，要得到完整回复需要把所有 `delta.content` 累加。

---

## 5. 小结

- 加 `stream: true`，逐行读 SSE，拼接 `delta.content`
- 结束标志是 `[DONE]`
- 流式的本质只是"分片返回"，适合提升交互体验，在 L5 可观测性/实时反馈中也会用到
