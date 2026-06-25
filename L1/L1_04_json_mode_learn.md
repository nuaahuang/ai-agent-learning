# L1-04: JSON Mode（结构化输出）

> 本节为概念补充（L1 目录暂无对应代码）。Function Calling 已演示了"结构化"，JSON Mode 是另一种强制结构化手段。

---

## 1. 为什么需要 JSON Mode

Agent 经常需要把 LLM 输出**喂给下游代码**处理。如果模型返回的是自由文本，解析起来非常脆弱。JSON Mode 强制模型只输出合法 JSON。

---

## 2. 用法

请求体加入 `response_format`：

```python
json={
    "model": MODEL,
    "messages": messages,
    "response_format": {"type": "json_object"}   # 强制 JSON 输出
}
```

> 注意：使用 JSON Mode 时，通常要在 `system` 或 `user` prompt 里**明确说明期望的 JSON 结构**，否则字段名可能不稳定。

---

## 3. JSON Mode vs Function Calling

| 维度 | JSON Mode | Function Calling |
|------|-----------|------------------|
| 目的 | 拿到结构化**数据** | 让模型决定调用**工具** |
| 输出 | 一个 JSON 对象 | tool_calls（工具名+参数） |
| 典型场景 | 信息抽取、分类、打分 | 查天气、查库、执行动作 |

---

## 4. 小结

- `response_format` 强制结构化输出，方便下游解析
- 配合 prompt 中明确的字段说明，效果最稳
- 在 L2 结构化推理、L8 评估打分的输出格式中广泛使用
