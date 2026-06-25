import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")

async def chat_completion_stream(messages: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": MODEL, "messages": messages, "stream": True}
            ) as response :
                async for chunk in response.aiter_lines():
                    if chunk.startswith("data:"):
                        data_str = chunk.replace("data:", "").strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            #核心： 提取增量内容
                            delta = data_json["choices"][0]["delta"].get("content", "")
                            print(delta, end="", flush=True)
                        except json.JSONDecodeError:
                            pass
        

# 测试
if __name__ == "__main__":
    import asyncio
    messages = [{"role": "user", "content": "Hello, who are you?"}]
    result = asyncio.run(chat_completion_stream(messages))
    print(json.dumps(result, indent = 2))

