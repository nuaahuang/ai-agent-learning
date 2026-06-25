import httpx
import json
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("MODEL", "deepseek-chat")

def get_weather(location: str) -> str:
    """
    模拟天气查询工具
    """
    return f"天气查询结果：{location}的天气是晴朗的"

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "用于查询天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "要查询的天气地点"
                    }
                },
                "required": ["location"]
            }
        }
    }
]

# =======
# 裸调用chat completion
# =======
async def chat_completion_with_tools(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]]
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.7
            }
        )
        response.raise_for_status()
        return response.json()

# =====
# 解析 tool_calls
# =====
def parse_tool_calls(response_json: Dict[str, Any]) -> tuple[str, dict]:
    """
    返回：（function_name, arguments_dict)
    """
    message = response_json["choices"][0]["message"]

    if "tool_calls" not in message:
        raise ValueError("模型没有返回 tool_calls, 可能未触发函数调用")
    
    tool_call = message["tool_calls"][0]
    function_name = tool_call["function"]["name"]
    arguments_dict = json.loads(tool_call["function"]["arguments"])
    return function_name, arguments_dict

async def main():
    messages = [
        {"role": "user", "content": "北京的天气"}
    ]

    # step 1: 模型决定是否调用工具
    print("model thinking...")
    response = await chat_completion_with_tools(messages, TOOLS_SCHEMA)
    
    print(response)
    # step 2: 解析模型返回
    function_name, args = parse_tool_calls(response)
    print(f"\n Model wants to call:")
    print(f" Function: {function_name}")
    print(f" Arguments: {args}")

    # step 3: 执行本地函数
    if function_name == "get_weather":
        result = get_weather(**args)
        print(f"\n tool executed locally:")
        print(f" result: {result}")

        # step 4: 把工具结果塞回对话
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": response["choices"][0]["message"]["tool_calls"]
        })

        messages.append({
            "role": "tool",
            "tool_call_id": response["choices"][0]["message"]["tool_calls"][0]["id"],
            "content": result
        })
        # step 5: 再次调用模型，生成最终自然语言回复
        final_response = await chat_completion_with_tools(messages, TOOLS_SCHEMA)
        final_answer = final_response["choices"][0]["message"]["content"]

        print(f"\n final answer for model:")
        print(f" {final_answer}")
    else:
        print("unknwn function")


if __name__ == "__main__":
    import asyncio 
    asyncio.run(main())