import httpx
import json
from typing import Dict, Any, List, Optional
import re
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")

def search_tool(query: str) -> str:
    """模拟搜索工具"""
    mock_data = {
        "2024年GDP增长率": "根据IMF预测，2024年全球GDP增长率约为3.1%。",
        "法国人口": "法国2023年人口约6800万。",
        "Python创始人": "Python由Guido van Rossum在1991年创建。"
    }

    return mock_data.get(query, f"未找到关于'{query}'的信息")

def calculator_tool(expression: str) -> str:
    """计算器工具"""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"计算结果：{result}"
    except Exception as e:
        return f"计算错误：{e}"

def get_current_time() -> str:
    """获取当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

TOOLS = {
    "search": search_tool,
    "calculator": calculator_tool,
    "get_current_time": get_current_time
}

# ========================
# 3. ReAct 解析器（核心！）
# ========================

def parse_react_step(model_output: str) -> Dict[str, Optional[str]]:
    """
    解析 ReAct 格式的输出
    
    期望格式：
    Thought: 我需要思考...
    Action: tool_name(arguments)
    
    或
    Thought: 我有足够信息
    Final Answer: 最终答案
    """

    result = {
        "thought": None,
        "action": None,
        "action_name": None,
        "action_args": None,
        "final_answer": None
    }

    # 提取 Thought
    thought_match = re.search(r"Thought:\s*(.+?)(?=\nAction:|\nFinal Answer:|$)", 
                            model_output, re.DOTALL)

    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    # 提取 Action
    action_match = re.search(r'Action:\s*(\w+)\(\s*(?:"([^"]+)"|((?:[^()]+|\([^()]*\))*))\s*\)', model_output)
    if action_match:
        result["action"] = action_match.group(0).strip()
        result["action_name"] = action_match.group(1)
        result["action_args"] = action_match.group(2) or action_match.group(3)
    
    # 提取 Final Answer
    answer_match = re.search(r"Final Answer:\s*(.+)", model_output, re.DOTALL)
    if answer_match:
        result["final_answer"] = answer_match.group(1).strip()

    return result

# ========================
# 4. ReAct 主循环（最核心！）
# ========================

async def react_agent_loop(user_query: str, max_steps: int = 5) -> str:
    """
    ReAct 主循环
    """
    # 初始化对话历史
    messages = [{
        "role": "system",
        "content": """你是一个遵循 ReAct 框架的助手。

            请按照以下格式回答：
            1. 先写 Thought: ...（你的推理过程）
            2. 如果需要工具，写 Action: tool_name(arguments)
            3. 如果不需要工具，写 Final Answer: ...（直接给出答案）

            可用工具：
            - search(query: str): 搜索信息
            - calculator(expression: str): 计算数学表达式
            - get_current_time(): 获取当前时间

            示例：
            用户：法国的GDP是多少？
            Thought: 我需要先搜索法国的最新GDP数据
            Action: search("法国2024年GDP")
        """
    }, {
        "role": "user",
        "content": user_query
    }]
    
    print(f"\n🤔 用户提问: {user_query}")
    print("-" * 50)


    async with httpx.AsyncClient(timeout=30) as client:
        for step in range(1, max_steps + 1):
            print(f"\n🔄 第 {step} 步:")

            # 1. 调用模型
            response = await client.post(
                 f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 500
                })
            )

            response.raise_for_status()
            response_data = response.json()

            model_output = response_data["choices"][0]["message"]["content"]

            print(f"  模型输出:\n{model_output}")

            # 2. 解析 ReAct 格式
            parsed = parse_react_step(model_output)

            # 3. 如果是 Thought，添加到历史
            if parsed["thought"]:
                    messages.append({
                        "role": "assistant",
                        "content": f"Thought: {parsed['thought']}"
                    })
            
            # 4. 检查是否结束
            if parsed["final_answer"]:
                    print(f"\n✅ 完成！最终答案:\n{parsed['final_answer']}")
                    return parsed["final_answer"]

            # 5. 执行 Action
            if parsed["action"] and parsed["action_name"] in TOOLS:
                tool_name = parsed["action_name"]
                tool_args = parsed["action_args"]
                
                print(f"  执行工具: {tool_name}({tool_args})")
                
                # 调用工具
                tool_result = TOOLS[tool_name](tool_args)
                print(f"  工具结果: {tool_result}")
                
                # 添加到对话历史
                messages.append({
                    "role": "assistant",
                    "content": f"Action: {parsed['action']}"
                })
                messages.append({
                    "role": "user",  # 注意：这是模拟的"环境反馈"
                    "content": f"Observation: {tool_result}"
                })
            else:
                # Action 格式错误
                print(f"❌ Action 格式错误: {parsed['action']}")
                break
    
    return "达到最大步数仍未得到答案"

# ========================
# 5. 测试用例
# ========================
async def main():
    # 测试 1: 需要搜索的问题
    print("测试 1: 复杂搜索")
    await react_agent_loop("2024年法国的GDP增长率是多少？和德国比谁更高？")
    
    print("\n" + "="*50 + "\n")
    
    # 测试 2: 需要计算的问题
    print("测试 2: 计算问题")
    await react_agent_loop("(15 + 27) * 3 等于多少？")
    
    print("\n" + "="*50 + "\n")
    
    # 测试 3: 简单问题
    print("测试 3: 简单问题")
    await react_agent_loop("Python是什么语言？")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())