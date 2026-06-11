import httpx
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")

# ========================
# 2. 工具定义
# ========================
def search_tool(query: str) -> str:
    """搜索工具"""
    mock_data = {
        "法国人口": "法国2023年人口约6800万。",
        "德国人口": "德国2023年人口约8400万。",
        "Python创始人": "Python由Guido van Rossum在1991年创建。",
        "AI发展": "人工智能在2020年代快速发展，特别是大语言模型。",
        "地球到月球距离": "地球到月球的平均距离约为384,400公里。",
        "光速": "真空中的光速为299,792,458米/秒。"
    }
    return mock_data.get(query, f"未找到关于'{query}'的信息")


def calculator_tool(expression: str) -> str:
    """计算器工具"""
    try:
        allowed_chars = set("0123456789+-*/(). ")
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含不安全字符"
        
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{result}"
    except Exception as e:
        return f"计算错误: {e}"


def get_current_time() -> str:
    """获取当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 工具映射
TOOLS = {
    "search": search_tool,
    "calculator": calculator_tool,
    "get_current_time": get_current_time
}


# ========================
# 3. Pydantic 模型
# ========================

class Action(BaseModel):
    name: str = Field(description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")

class ReactStep(BaseModel):
    """ReAct 单步输出"""
    thought: str = Field(..., description="推理过程")
    action: Optional[Action] = Field(None, description="要执行的动作")
    final_answer: Optional[str] = Field(None, description="最终答案")

class ReflectionResult(BaseModel):
    """Reflection 的输出"""
    is_correct: bool = Field(..., description="结果是否正确")
    reason: str = Field(..., description="判断理由")
    corrected_action: Optional[Action] = Field(None, description="如果需要修正，新的动作")
    corrected_final_answer: Optional[str] = Field(None, description="如果需要修正，新的最终答案")

# ========================
# 4. 核心：带 Reflection 的 ReAct
# ========================

async def react_with_reflection(
    user_query: str,
    max_steps: int = 5,
    max_reflections: int = 3  # 每个步骤最多反思次数
) -> str:
    """
    带 Reflection 机制的 ReAct Agent
    
    特点：
    1. 每次 Action 后都会反思结果
    2. 发现错误会自动修正
    3. 避免重复犯同样的错误
    """

    # 系统提示词
    system_prompt = f"""
你是一个遵循 ReAct 框架的智能助手。

**核心规则**：
1. 每一步都必须输出 JSON 格式
2. 输出格式必须严格符合 Schema
3. 如果遇到错误，反思并修正

**输出格式**：
json

{{

"thought": "你的推理过程",

"action": {{

"name": "工具名称",

"arguments": {{}}

}},

"final_answer": null

}}

**可用工具**：
- search: 搜索信息，参数: {{"query": "搜索内容"}}
- calculator: 计算数学表达式，参数: {{"expression": "1+1"}}
- get_current_time: 获取当前时间，参数: {{}}

**重要**：
- 仔细思考用户的真实意图
- 不要急于给出答案
- 如果发现结果不合理，反思并修正
"""
    
    # Reflection 提示词
    reflection_prompt = """
你是一个严格的审查者。你需要检查上一步的执行结果。

**检查要点**：
1. 结果是否合理？
2. 是否完全回答了用户的问题？
3. 有没有遗漏什么？
4. 计算是否正确？

**输出格式**：
json

{{

"is_correct": true/false,

"reason": "判断理由",

"corrected_action": null,

"corrected_final_answer": null

}}

如果结果不正确，请在 corrected_action 或 corrected_final_answer 中给出修正方案。

**当前上下文**：
- 用户问题: {user_query}
- 上一步的 Thought: {last_thought}
- 执行的 Action: {last_action}
- 得到的 Observation: {observation}
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]

    print(f"\n🤔 用户提问: {user_query}")
    print("-" * 70)

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
                    react_step = ReactStep(**parsed_json)
                    
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
                    print(f"\n✅ 模型直接给出了最终答案:\n{react_step.final_answer}")
                    # ========== Phase 2: Reflection ==========
                    print(f"\n🔍 Phase 2: 反思验证")

                    # 构造 Reflection 消息
                    reflection_messages = [
                        {"role": "system", "content": reflection_prompt.format(
                            user_query=user_query,
                            last_thought=react_step.thought,
                            last_action="无（直接给出答案）",
                            observation=react_step.final_answer
                        )},
                        {"role": "user", "content": "请审查这个答案是否正确？"}
                    ]

                    reflection_response = await client.post(
                            f"{BASE_URL}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {API_KEY}",
                                "Content-Type": "application/json",
                            },
                            data=json.dumps({
                                "model": "deepseek-chat",
                                "messages": reflection_messages,
                                "temperature": 0.1,
                                "max_tokens": 500,
                                "response_format": {
                                    "type": "json_object"
                                },
                                "response_format": {
                                    "type": "json_object"
                                }
                            }),
                            
                        )

                    reflection_response.raise_for_status()
                    reflection_data = reflection_response.json()
                    reflection_output = reflection_data["choices"][0]["message"]["content"]

                    try:
                        reflection_result = ReflectionResult(**json.loads(reflection_output))
                    except Exception as e:
                        print(f"⚠️ Reflection 解析失败: {e}")
                        print(f"   默认接受答案")
                        return react_step.final_answer
                    
                    print(f"  🔎 Reflection 判断: {'✅ 正确' if reflection_result.is_correct else '❌ 错误'}")
                    print(f"  💬 理由: {reflection_result.reason}")

                    if reflection_result.is_correct:
                        print(f"\n🎉 答案通过验证！")
                        return react_step.final_answer
                    else:
                        print(f"\n🔄 答案未通过验证，开始修正...")
                        # 如果是修正后的最终答案
                        if reflection_result.corrected_final_answer:
                            print(f"  ✨ 修正后的答案: {reflection_result.corrected_final_answer}")
                            
                            # 再次反思修正后的答案
                            print(f"\n🔍 Phase 3: 二次验证")
                        
                            second_reflection = await client.post(
                                f"{BASE_URL}/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {API_KEY}",
                                    "Content-Type": "application/json",
                                },
                                data=json.dumps({
                                    "model": "deepseek-chat",
                                    "messages": [{"role": "system", "content": reflection_prompt.format(
                                            user_query=user_query,
                                            last_thought=f"修正后的答案",
                                            last_action="无",
                                            observation=reflection_result.corrected_final_answer
                                        )},
                                        {"role": "user", "content": "请审查这个修正后的答案是否正确？"}],
                                    "temperature": 0.1,
                                    "max_tokens": 500,
                                    "response_format": {
                                        "type": "json_object"
                                    }
                                })
                            )

                            second_reflection_data = second_reflection.json()
                            second_reflection_output = second_reflection_data["choices"][0]["message"]["content"]
                            try:
                                second_result = ReflectionResult(**json.loads(second_reflection_output))
                                if second_result.is_correct:
                                    print(f"  ✅ 二次验证通过！")
                                    return reflection_result.corrected_final_answer
                                else:
                                    print(f"  ❌ 二次验证仍不通过: {second_result.reason}")
                                    # 继续循环
                            except:
                                pass
                        # 如果有修正的 Action，添加到消息历史
                        if reflection_result.corrected_action:
                            messages.append({
                                "role": "assistant",
                                "content": f"反思: {reflection_result.reason}"
                            })
                            continue

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

                        # ========== Phase 2: Reflection on Action Result ==========
                        reflection_messages = [
                            {"role": "system", "content": reflection_prompt.format(
                                user_query=user_query,
                                last_thought=react_step.thought,
                                last_action=f"{action.name}({action.arguments})",
                                observation=result
                            )},
                            {"role": "user", "content": "请审查这个 Action 的结果是否合理？是否需要修正？"}
                        ]

                        reflection_response = await client.post(
                            f"{BASE_URL}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {API_KEY}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "model": "deepseek-chat",
                                "messages": reflection_messages,
                                "temperature": 0.1,
                                "max_tokens": 600,
                                "response_format": {
                                    "type": "json_object"
                                }
                            }
                        )
                        
                        reflection_response.raise_for_status()
                        reflection_data = reflection_response.json()
                        reflection_output = reflection_data["choices"][0]["message"]["content"]

                        try:
                            reflection_result = ReflectionResult(**json.loads(reflection_output))
                        except Exception as e:
                            print(f"⚠️ Reflection 解析失败: {e}")
                            # 默认接受结果
                            messages.append({
                                "role": "assistant",
                                "content": f"Thought: {react_step.thought}\nAction: {action.name}({json.dumps(action.arguments, ensure_ascii=False)})\nObservation: {result}"
                            })
                            continue
                        
                        print(f"  🔎 Reflection 判断: {'✅ 合理' if reflection_result.is_correct else '❌ 不合理'}")
                        print(f"  💬 理由: {reflection_result.reason}")

                        if reflection_result.is_correct:
                            # 结果合理，继续
                            messages.append({
                                "role": "assistant",
                                "content": f"Thought: {react_step.thought}\nAction: {action.name}({json.dumps(action.arguments, ensure_ascii=False)})\nObservation: {result}"
                            })
                        else:
                            # 结果不合理，反思并修正
                            print(f"  🔄 结果不合理，反思中...")
                            
                            if reflection_result.corrected_action:
                                print(f"  ✨ 修正 Action: {reflection_result.corrected_action.name}({reflection_result.corrected_action.arguments})")
                                
                                # 执行修正后的 Action
                                corrected_tool = TOOLS[reflection_result.corrected_action.name]
                                if reflection_result.corrected_action.name == "search":
                                    corrected_result = corrected_tool(reflection_result.corrected_action.arguments.get("query", ""))
                                elif reflection_result.corrected_action.name == "calculator":
                                    corrected_result = corrected_tool(reflection_result.corrected_action.arguments.get("expression", ""))
                                else:
                                    corrected_result = corrected_tool()
                                
                                print(f"  📊 修正后的 Observation: {corrected_result}")
                                
                                messages.append({
                                    "role": "assistant",
                                    "content": f"Thought: {react_step.thought}（反思后修正）\nAction: {reflection_result.corrected_action.name}({json.dumps(reflection_result.corrected_action.arguments, ensure_ascii=False)})\nObservation: {corrected_result}"
                                })
                            else:
                                # 只是记录反思，继续
                                messages.append({
                                    "role": "assistant",
                                    "content": f"Thought: {react_step.thought}\nAction: {action.name}({json.dumps(action.arguments, ensure_ascii=False)})\nObservation: {result}\n反思: {reflection_result.reason}"
                                })
                    
                    except Exception as e:
                        error_msg = f"工具执行错误: {e}"
                        print(f"  ❌ {error_msg}")
                        messages.append({
                            "role": "user",
                            "content": f"Observation: {error_msg}"
                        })
                else:
                    print("  ⚠️ 没有 Action 也没有 Final Answer")
                    break
                    
            except httpx.HTTPStatusError as e:
                print(f"❌ HTTP 错误: {e}")
                break
            except Exception as e:
                print(f"❌ 未知错误: {e}")
                break
    
    return "达到最大步数仍未得到答案"   


# ========================
# 5. 测试用例
# ========================
async def main():
    print("🧪 测试带 Reflection 的 ReAct Agent")
    print("="*70)
    
    # 测试 1: 需要计算的问题（容易出错）
    print("\n📊 测试 1: 计算问题（考验运算优先级）")
    result1 = await react_with_reflection("(15 + 27) * 3 等于多少？")
    print(f"\n测试1结果: {result1}")
    
    print("\n" + "="*70)
    
    # 测试 2: 需要搜索和计算的问题
    print("\n🔍 测试 2: 多步推理问题")
    result2 = await react_with_reflection("地球到月球的距离是多少？如果光速是30万公里每秒，光从地球到月球需要多长时间？")
    print(f"\n测试2结果: {result2}")
    
    print("\n" + "="*70)
    
    # 测试 3: 故意模糊的问题（考验反思能力）
    print("\n🤔 测试 3: 模糊问题")
    result3 = await react_with_reflection("帮我查一下法国的相关信息")
    print(f"\n测试3结果: {result3}")


if __name__ == "__main__":
    asyncio.run(main())