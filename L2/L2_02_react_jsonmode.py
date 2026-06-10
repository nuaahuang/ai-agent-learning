import httpx
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import asyncio

API_KEY = ""
BASE_URL = "https://api.deepseek.com"

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
# 3. 用 Pydantic 定义 ReAct 输出结构
# ========================

class Action(BaseModel):
    name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")

class ReActStep(BaseModel):
    """ReAct 单步输出的结构化格式"""
    thought: str = Field(..., description="推理过程")
    action: Optional[Action] = Field(None, description="要执行的动作，如果不需要则为null")
    final_answer: Optional[str] = Field(None, description="最终答案，如果有则结束")

# ========================
# 4. 主循环（JSON Mode 版本）
# ========================

async def react_json_mode_agent(
    user_query: str,
    max_steps: int = 5
) -> str:
    """
    使用 JSON Mode 的 ReAct Agent
    100% 可解析，没有正则表达式
    """
    
    # 系统提示词
    system_prompt = """
你是一个遵循 ReAct 框架的助手。

请严格按照以下 JSON 格式输出，不要包含任何其他内容：

{
  "thought": "你的推理过程",
  "action": {
    "name": "工具名称",
    "arguments": {}
  },
  "final_answer": null
}

或者不需要工具时：

{
  "thought": "你的推理过程",
  "action": null,
  "final_answer": "最终答案"
}

规则：
1. "action" 和 "final_answer" 不能同时非空
2. 如果需要工具，设置 "action" 字段，final_answer 设为 null
3. 如果不需要工具，设置 "final_answer" 字段，action 设为 null
4. 工具参数必须是字典格式

可用工具：
- search: 搜索信息，参数: {"query": "搜索内容"}
- calculator: 计算数学表达式，参数: {"expression": "1+1"}
- get_current_time: 获取当前时间，参数: {}

请一步步思考，不要跳过推理步骤。
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]
    
    print(f"\n🤔 用户提问: {user_query}")
    print("-" * 50)
    
    async with httpx.AsyncClient(timeout=30) as client:
        for step in range(1, max_steps + 1):
            print(f"\n🔄 第 {step} 步:")
            try:
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

                # 2. 提取 JSON 输出
                model_output = response_data["choices"][0]["message"]["content"]
                print(f"  模型原始输出:\n{json.dumps(json.loads(model_output), indent=2, ensure_ascii=False)}")

                # 3. 解析 JSON
                try:
                    parsed_json = json.loads(model_output)
                    
                    # 4. 用 Pydantic 验证和解析
                    react_step = ReActStep(**parsed_json)
                    
                except Exception as e:
                    print(f"❌ JSON 解析失败: {e}")
                    print(f"   原始输出: {model_output}")
                    return f"JSON 解析失败: {e}"

                # 5. 打印 Thought
                if react_step.thought:
                    print(f"  🤔 Thought: {react_step.thought}")
                    messages.append({
                        "role": "assistant",
                        "content": f"Thought: {react_step.thought}"
                    })
                
                # 6. 检查是否结束
                if react_step.final_answer:
                    print(f"\n✅ 完成！最终答案:\n{react_step.final_answer}")
                    return react_step.final_answer

                # 7. 执行 Action
                if react_step.action:
                    action = react_step.action
                    
                    if action.name not in TOOLS:
                        print(f"❌ 未知工具: {action.name}")
                        messages.append({
                            "role": "user",
                            "content": f"Observation: 未知工具 '{action.name}'"
                        })
                        continue
                    
                    # 执行工具
                    print(f"  🛠️ Action: {action.name}({action.arguments})")
                    
                    try:
                        # 根据工具类型调用
                        tool_func = TOOLS[action.name]
                        
                        if action.name == "search":
                            result = tool_func(action.arguments.get("query", ""))
                        elif action.name == "calculator":
                            result = tool_func(action.arguments.get("expression", ""))
                        elif action.name == "get_current_time":
                            result = tool_func()
                        else:
                            result = "未知工具"
                        
                        print(f"  📊 Observation: {result}")
                        
                        # 添加到对话历史
                        messages.append({
                            "role": "assistant",
                            "content": f"Action: {action.name}({json.dumps(action.arguments, ensure_ascii=False)})"
                        })
                        messages.append({
                            "role": "user",
                            "content": f"Observation: {result}"
                        })
                        
                    except Exception as e:
                        error_msg = f"工具执行错误: {e}"
                        print(f"  ❌ {error_msg}")
                        messages.append({
                            "role": "user",
                            "content": f"Observation: {error_msg}"
                        })
                else:
                    print("  ⚠️ 没有 Action 也没有 Final Answer，模型可能格式错误")
                    break
            except httpx.HTTPStatusError as e:
                    print(f"❌ HTTP 错误: {e}")
                    break
            except Exception as e:
                print(f"❌ 未知错误: {e}")
    return "达到最大步数仍未得到答案"     

# ========================
# 5. 测试用例
# ========================
async def main():
    print("🧪 测试 JSON Mode ReAct Agent")
    print("="*50)
    
    # 测试 1: 需要计算的问题
    print("\n📊 测试 1: 计算问题")
    result1 = await react_json_mode_agent("(15 + 27) * 3 等于多少？")
    print(f"测试1结果: {result1}")
    
    print("\n" + "="*50)
    
    # 测试 2: 需要搜索的问题
    print("\n🔍 测试 2: 搜索问题")
    result2 = await react_json_mode_agent("法国和德国哪个国家人口更多？")
    print(f"测试2结果: {result2}")
    
    print("\n" + "="*50)
    
    # 测试 3: 混合问题
    print("\n🔢 测试 3: 混合问题")
    result3 = await react_json_mode_agent("当前时间是什么？然后用计算器算一下 100 * 3.14")
    print(f"测试3结果: {result3}")


if __name__ == "__main__":
    asyncio.run(main())   