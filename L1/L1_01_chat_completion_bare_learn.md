# L1-01: 裸调用 Chat Completions

对应代码：[L1_01_chat_completion_bare.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L1/coding/L1_01_chat_completion_bare.py)

---

## 0. 为什么从"裸调用"开始

很多人学 Agent 直接上 LangChain / LlamaIndex 等框架，结果框架一报错就抓瞎。
本章坚持用 `httpx` 裸调 HTTP API，目的是看清楚最本质的东西：

```
Agent 的本质 = 一个 while 循环 + 不断地调用 LLM 的 HTTP 接口 + 解析返回
```

只要理解了"一次 HTTP 请求/响应"的全貌，后面的流式、工具调用、ReAct 都只是它的变体。

### 环境配置（三件套）

所有 L1 代码都依赖三个环境变量（通过 `.env` + `python-dotenv` 加载）：

| 变量 | 含义 | 示例 |
|------|------|------|
| `API_KEY` | 鉴权密钥 | `sk-xxxx` |
| `BASE_URL` | 服务地址 | `https://api.deepseek.com` |
| `MODEL` | 模型名 | `deepseek-chat` |

```python
load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")
```

> 这套配置在 L1-L8 全程复用。OpenAI 兼容协议是事实标准，DeepSeek/Qwen/Kimi 等都兼容 `/chat/completions` 接口。

---

## 1. 核心概念

最基础的一次"问答"，就是向 `/chat/completions` 发一个 POST 请求：

```python
async def chat_completion_bare(messages):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",   # 鉴权
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": MODEL,
                "messages": messages,                    # 对话历史
                "temperature": 0.7,                      # 随机性
            }),
        )
        response.raise_for_status()                      # 非2xx抛异常
        return response.json()
```

---

## 2. 请求体三大要素

| 字段 | 作用 | 说明 |
|------|------|------|
| `model` | 指定模型 | 决定能力与价格 |
| `messages` | 对话历史 | **LLM 是无状态的**，每次都要把完整上下文传过去 |
| `temperature` | 采样随机性 | 0=确定/严谨，1=发散/创意，一般 0.7 |

---

## 3. messages 的角色（role）

```python
messages = [
    {"role": "system",    "content": "你是一个助手"},   # 系统设定（可选）
    {"role": "user",      "content": "你好"},           # 用户输入
    {"role": "assistant", "content": "你好，有什么..."}, # 模型回复
]
```

| role | 含义 |
|------|------|
| `system` | 全局设定/人设/约束（优先级最高） |
| `user` | 用户提问 |
| `assistant` | 模型历史回复 |
| `tool` | 工具执行结果（见 L1-03） |

> **关键认知**：LLM 没有"记忆"。所谓"多轮对话"，是客户端每次把整段 `messages` 重新发过去模拟出来的。

---

## 4. 返回结构

```json
{
  "choices": [
    {"message": {"role": "assistant", "content": "我是一个AI助手"}}
  ],
  "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}
}
```

取回复内容：`response["choices"][0]["message"]["content"]`

---

## 5. 小结

- 一次问答 = 一个带 `messages` 的 POST 请求
- LLM 无状态，上下文必须由客户端每次完整带上
- 这是所有 LLM 交互的底座，后续流式、工具调用都是它的变体
