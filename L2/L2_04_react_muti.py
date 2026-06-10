from ast import arguments

import httpx
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio

API_KEY = ""
BASE_URL = "https://api.deepseek.com"

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
        "光速": "真空中的光速为299,792,458米/秒。",
        "中国人口": "中国2023年人口约14.1亿。",
        "印度人口": "印度2023年人口约14.2亿。",
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


TOOLS = {
    "search": search_tool,
    "calculator": calculator_tool,
    "get_current_time": get_current_time
}

# ========================
# 3. Pydantic 模型
# ========================
class Action(BaseModel):
    name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")

class Task(BaseModel):
    """任务单元"""
    task_id: str = Field(..., description="任务ID")
    description: str = Field(..., description="任务描述")
    status: str = Field("pending", description="任务状态: pending/in_progress/done/failed")
    result: Optional[str] = Field(None, description="任务结果")
    assigned_to: Optional[str] = Field(None, description="分配给哪个 Worker")

class Plan(BaseModel):
    """Planner 的输出"""
    plan_summary: str = Field(..., description="计划概述")
    tasks: List[Task] = Field(..., description="任务列表")

class WorkerResult(BaseModel):
    """Worker 的输出"""
    task_id: str = Field(..., description="执行的任务ID")
    action: Action = Field(..., description="执行的动作")
    observation: str = Field(..., description="工具返回的结果")
    success: bool = Field(True, description="是否成功")

class CriticFeedback(BaseModel):
    """Critic 的反馈"""
    task_id: str = Field(..., description="审查的任务ID")
    is_correct: bool = Field(..., description="结果是否正确")
    feedback: str = Field(..., description="反馈意见")
    suggested_correction: Optional[str] = Field(None, description="建议的修正方案")

# ========================
# 4. Agent 基类
# ========================
class Agent:
    """Agent 基类"""
    
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.client = httpx.AsyncClient(timeout=30)
    
    async def think(self, messages: List[Dict[str, str]], response_schema: type) -> Any:
        """让 Agent 思考并返回结构化输出"""
        
        full_messages = [
            {"role": "system", "content": self.system_prompt},
            *messages
        ]
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": full_messages,
                    "temperature": 0.1,
                    "max_tokens": 1000,
                    "response_format": {
                        "type": "json_object"
                    }
                }
            )
            
            response.raise_for_status()
            response_data = response.json()
            model_output = response_data["choices"][0]["message"]["content"]
            
            parsed = json.loads(model_output)
            return response_schema(**parsed)
            
        except Exception as e:
            print(f"  [{self.name}] ❌ 错误: {e}")
            return None
    
    async def close(self):
        await self.client.aclose()

# ========================
# 5. 具体 Agent 实现
# ========================
class PlannerAgent(Agent):
    """Planner: 制定计划"""
    
    def __init__(self):
        super().__init__(
            name="Planner",
            system_prompt="""
你是一个专业的项目规划者（Planner）。

你的职责：
1. 理解用户的需求
2. 将复杂问题分解为多个子任务
3. 确定任务的执行顺序

**输出格式**（必须严格遵循 JSON）：
json

{

"plan_summary": "计划的简要概述",

"tasks": [

{

"task_id": "task_1",

"description": "任务描述",

"status": "pending",

"result": null,

"assigned_to": null

}

]

}

**规则**：
- task_id 格式: task_1, task_2, task_3...
- 每个任务应该是原子性的（只做一件事）
- 任务之间要有明确的依赖关系
- 不要超过5个任务
"""
        )

class WorkerAgent(Agent):
    """Worker: 执行具体任务"""
    
    def __init__(self):
        super().__init__(
            name="Worker",
            system_prompt=f"""
你是一个执行者（Worker）。

你的职责：
1. 接收一个具体的任务
2. 选择合适的工具来执行
3. 返回执行结果

**可用工具**：
- search(query: str): 搜索信息
- calculator(expression: str): 计算数学表达式
- get_current_time(): 获取当前时间

**输出格式**（必须严格遵循 JSON）：
json

{{

"task_id": "任务ID",

"action": {{

"name": "工具名称",

"arguments": {{}}

}},

"observation": "工具返回的结果",

"success": true

}}

**规则**：
- 一次只执行一个工具
- 如果工具返回错误，设置 success=false
- 观察结果要如实记录
"""
        )

class CriticAgent(Agent):
    """Critic: 审查结果"""
    
    def __init__(self):
        super().__init__(
            name="Critic",
            system_prompt="""
你是一个严格的审查者（Critic）。

你的职责：
1. 检查 Worker 的执行结果是否正确
2. 检查结果是否完全回答了任务的要求
3. 如果发现错误，给出修正建议

**输出格式**（必须严格遵循 JSON）：
json

{

"task_id": "审查的任务ID",

"is_correct": true,

"feedback": "审查意见",

"suggested_correction": null

}

**规则**：
- 要严格但不苛刻
- 如果结果有瑕疵，给出具体的修正建议
- 如果结果完全正确，直接通过
"""
        )

class CoordinatorAgent(Agent):
    """Coordinator: 汇总最终结果"""
    
    def __init__(self):
        super().__init__(
            name="Coordinator",
            system_prompt="""
你是一个协调者（Coordinator）。

你的职责：
1. 收集所有 Worker 的执行结果
2. 汇总成一个完整的答案
3. 确保答案连贯、完整

**输出格式**（必须严格遵循 JSON）：
json

{

"final_answer": "最终的完整答案",

"confidence": "high/medium/low",

"notes": "任何需要注意的事项"

}

**规则**：
- 答案要自然、易懂
- 如果有多个任务结果，要有机整合
- 如果某些任务失败，要如实说明
"""
        )

# ========================
# 6. Multi-Agent 主控制器
# ========================
class MultiAgentSystem:
    """Multi-Agent 系统的主控制器"""
    
    def __init__(self):
        self.planner = PlannerAgent()
        self.worker = WorkerAgent()
        self.critic = CriticAgent()
        self.coordinator = CoordinatorAgent()
        
        self.task_results: Dict[str, str] = {}
    
    async def solve(self, user_query: str) -> str:
        """处理用户问题的主流程"""
        
        print(f"\n{'='*80}")
        print(f"🤔 用户提问: {user_query}")
        print(f"{'='*80}")
        
        # ========== Phase 1: Planner 制定计划 ==========
        print(f"\n📋 Phase 1: Planner 制定计划")
        print("-" * 40)
        
        plan = await self.planner.think(
            messages=[{"role": "user", "content": f"请为以下问题制定执行计划：{user_query}"}],
            response_schema=Plan
        )
        
        if not plan:
            return "❌ Planner 无法制定计划"
        
        print(f"  计划概述: {plan.plan_summary}")
        print(f"  任务列表:")
        for task in plan.tasks:
            print(f"    - {task.task_id}: {task.description}")
        
        # ========== Phase 2: Worker 执行任务 ==========
        print(f"\n🔧 Phase 2: Worker 执行任务")
        print("-" * 40)
        
        for task in plan.tasks:
            print(f"\n  ▶️ 执行 {task.task_id}: {task.description}")
            
            # Worker 执行
            worker_result = await self.worker.think(
                messages=[
                    {"role": "user", "content": f"请执行以下任务：{task.description}\n请选择合适的工具。"}
                ],
                response_schema=WorkerResult
            )
            
            if not worker_result:
                print(f"    ❌ Worker 执行失败")
                self.task_results[task.task_id] = "执行失败"
                continue
            
            print(f"    🛠️ Action: {worker_result.action.name}({worker_result.action.arguments})")
            print(f"    📊 Observation: {worker_result.observation}")
            
            # 实际执行工具
            if worker_result.action.name in TOOLS:
                tool_func = TOOLS[worker_result.action.name]
                actual_result = tool_func(**worker_result.action.arguments)
                print(f"    ✅ 实际执行结果: {actual_result}")
                
                # 更新 task result
                self.task_results[task.task_id] = actual_result
                
                # ========== Phase 3: Critic 审查 ==========
                print(f"\n  🔍 Phase 3: Critic 审查")
                
                critic_feedback = await self.critic.think(
                    messages=[
                        {"role": "user", "content": f"""
请审查以下任务执行结果：

任务: {task.description}
执行动作: {worker_result.action.name}({worker_result.action.arguments})
执行结果: {actual_result}

这个结果是否正确？是否符合任务要求？
"""}
                    ],
                    response_schema=CriticFeedback
                )
                
                if critic_feedback:
                    print(f"    🔎 审查结果: {'✅ 通过' if critic_feedback.is_correct else '❌ 需修正'}")
                    print(f"    💬 反馈: {critic_feedback.feedback}")
                    
                    if not critic_feedback.is_correct and critic_feedback.suggested_correction:
                        print(f"    ✨ 修正建议: {critic_feedback.suggested_correction}")
                        
                        # 如果 Critic 给出了修正，重新执行
                        if critic_feedback.suggested_correction:
                            print(f"\n    🔄 根据 Critic 反馈重新执行...")
                            
                            retry_result = await self.worker.think(
                                messages=[
                                    {"role": "user", "content": f"""
原始任务: {task.description}
Critic 反馈: {critic_feedback.feedback}
修正建议: {critic_feedback.suggested_correction}

请根据 Critic 的建议重新执行。
"""}
                                ],
                                response_schema=WorkerResult
                            )
                            
                            if retry_result and retry_result.action.name in TOOLS:
                                retry_tool = TOOLS[retry_result.action.name]
                                retry_actual = retry_tool(**retry_result.action.arguments)
                                print(f"    ✅ 重新执行结果: {retry_actual}")
                                self.task_results[task.task_id] = retry_actual
            else:
                print(f"    ❌ 未知工具: {worker_result.action.name}")
                self.task_results[task.task_id] = "未知工具"
        
        # ========== Phase 4: Coordinator 汇总 ==========
        print(f"\n📝 Phase 4: Coordinator 汇总结果")
        print("-" * 40)
        
        # 构建结果摘要
        results_summary = "\n".join([
            f"- {task_id}: {result}"
            for task_id, result in self.task_results.items()
        ])
        
        class CoordinatorOutput(BaseModel):
            final_answer: str
            confidence: str
            notes: Optional[str]
        
        coordinator_result = await self.coordinator.think(
            messages=[
                {"role": "user", "content": f"""
原始问题: {user_query}

各任务执行结果:
{results_summary}

请将这些结果整合成一个完整的、自然的答案。
"""}
            ],
            response_schema=CoordinatorOutput
        )
        
        if coordinator_result:
            print(f"\n{'='*80}")
            print(f"🎉 最终答案:")
            print(f"{coordinator_result.final_answer}")
            print(f"\n置信度: {coordinator_result.confidence}")
            if coordinator_result.notes:
                print(f"备注: {coordinator_result.notes}")
            print(f"{'='*80}")
            
            return coordinator_result.final_answer
        else:
            return "❌ Coordinator 无法生成最终答案"
    
    async def close(self):
        """清理资源"""
        await self.planner.close()
        await self.worker.close()
        await self.critic.close()
        await self.coordinator.close()

# ========================
# 7. 测试
# ========================
async def main():
    print("🧪 测试 Multi-Agent 协作系统")
    
    # 创建 Multi-Agent 系统
    system = MultiAgentSystem()
    
    try:
        # 测试 1: 需要多步推理的问题
        print("\n" + "="*80)
        print("📊 测试 1: 多步推理问题")
        result1 = await system.solve("中国和印度哪个国家人口更多？多多少？")
        print(f"\n测试1结果: {result1}")
        
        # 测试 2: 需要计算的问题
        print("\n" + "="*80)
        print("📊 测试 2: 计算问题")
        result2 = await system.solve("地球到月球的距离是384,400公里，如果光速是30万公里每秒，光从地球到月球需要多少秒？")
        print(f"\n测试2结果: {result2}")
        
        # 测试 3: 混合问题
        print("\n" + "="*80)
        print("📊 测试 3: 混合问题")
        result3 = await system.solve("Python是什么时候创建的？到现在多少年了？")
        print(f"\n测试3结果: {result3}")
        
    finally:
        await system.close()


if __name__ == "__main__":
    asyncio.run(main())