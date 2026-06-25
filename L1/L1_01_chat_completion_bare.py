import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")

async def chat_completion_bare(messages: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": MODEL,
                "messages": messages,
                "temperature": 0.7,
            }),
        )

        response.raise_for_status()
        return response.json()

# 测试
if __name__ == "__main__":
    import asyncio
    messages = [{"role": "user", "content": "Hello, who are you?"}]
    result = asyncio.run(chat_completion_bare(messages))
    print(json.dumps(result, indent = 2))

