# L2-04: Multi-Agent（多智能体协作基础）

对应代码：[L2_04_react_muti.py](file:///Users/deganghuang/workingspace/develop/agent_learning_code_space/L2/L2_04_react_muti.py)

---

## 1. 从单 Agent 到多 Agent

L2-01~03 都是**一个模型扮演所有角色**。当任务变复杂时，让一个 Agent 包揽所有职责会力不从心。

Multi-Agent 的思路：**角色分工，各司其职**。
就像一个团队：有人做规划、有人干活、有人审查、有人汇总。

```
单 Agent：一个人从头做到尾
多 Agent：项目经理 + 工程师 + 质检 + 汇报人 协作
```

---

## 2. 四个角色（经典分工）

本节实现了 Planner-Worker-Critic-Coordinator 模式：

| Agent | 角色 | 职责 |
|-------|------|------|
| **Planner** | 规划者 | 把复杂问题拆解为多个原子子任务 |
| **Worker** | 执行者 | 接收单个任务，选择工具执行 |
| **Critic** | 审查者 | 检查 Worker 结果是否正确，给修正建议 |
| **Coordinator** | 协调者 | 汇总所有任务结果，整合成最终答案 |

> 这其实是把 L2-03 的"执行者 + 审查者"扩展成了完整团队，并加上了"规划"和"汇总"。

---

## 3. Agent 基类设计

所有 Agent 共享一个基类，核心是 `think()` 方法：

```python
class Agent:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt        # 每个角色不同的人设
        self.client = httpx.AsyncClient(timeout=30)

    async def think(self, messages, response_schema):
        """让 Agent 思考并返回结构化输出（JSON Mode + Pydantic）"""
        full_messages = [{"role": "system", "content": self.system_prompt}, *messages]
        response = await self.client.post(..., json={
            "messages": full_messages,
            "response_format": {"type": "json_object"}    # 强制 JSON
        })
        return response_schema(**json.loads(model_output)) # Pydantic 解析
```

> 设计要点：**统一接口 + 角色差异化 prompt + 结构化输出**。每个 Agent 只是 `system_prompt` 和 `response_schema` 不同。

---

## 4. 各角色的结构化输出

每个 Agent 有自己的输出 Schema：

```python
class Plan(BaseModel):              # Planner 输出
    plan_summary: str
    tasks: List[Task]

class WorkerResult(BaseModel):      # Worker 输出
    task_id: str
    action: Action
    observation: str
    success: bool

class CriticFeedback(BaseModel):    # Critic 输出
    task_id: str
    is_correct: bool
    feedback: str
    suggested_correction: Optional[str]
```

---

## 5. 完整协作流程（4 个 Phase）

```
Phase 1: Planner 制定计划
   用户问题 → 拆解成 task_1, task_2, ...

Phase 2: Worker 执行任务（逐个）
   每个 task → Worker 选工具 → 实际执行 → 得到结果

Phase 3: Critic 审查（每个任务后）
   检查结果是否正确 → 不通过则 Worker 根据建议重试

Phase 4: Coordinator 汇总
   收集所有 task 结果 → 整合成完整自然语言答案 + 置信度
```

代码主干：

```python
class MultiAgentSystem:
    async def solve(self, user_query):
        plan = await self.planner.think(...)          # Phase 1
        for task in plan.tasks:                       # Phase 2
            worker_result = await self.worker.think(...)
            actual_result = TOOLS[...](...)           # 真实执行工具
            critic_feedback = await self.critic.think(...)  # Phase 3
            if not critic_feedback.is_correct:
                retry_result = await self.worker.think(...) # 重试
        coordinator_result = await self.coordinator.think(...)  # Phase 4
        return coordinator_result.final_answer
```

---

## 6. 关键设计点

| 点 | 说明 |
|----|------|
| **任务原子化** | Planner 要求每个任务只做一件事，便于执行和审查 |
| **真实执行 vs 模型描述** | Worker 给出 action，但工具由**主控代码真实执行**，不信任模型的 observation |
| **Critic 闭环** | 审查不通过会触发 Worker 重试，形成质量保障 |
| **资源清理** | 每个 Agent 持有 httpx client，结束要 `close()` |

---

## 7. 与后续章节的关系

L2-04 是多 Agent 的**入门版**（线性流程：规划→执行→审查→汇总）。
真正的多 Agent 通信模式在 **L4** 深入展开：

| 模式 | 章节 |
|------|------|
| 黑板模式（共享知识） | L4-01 |
| 信箱模式（点对点） | L4-02 |
| 广播模式（一对多） | L4-03 |
| 交接机制（任务传递） | L4-04 |
| 共识机制（投票） | L4-05 |
| 辩论机制（观点对抗） | L4-06 |

---

## 8. 小结

- Multi-Agent = 角色分工协作，应对复杂任务
- 经典四角色：Planner（规划）/ Worker（执行）/ Critic（审查）/ Coordinator（汇总）
- 统一 Agent 基类 + 差异化 prompt + 结构化输出，是工程化的关键
- 工具由主控代码真实执行，不盲信模型描述
- 本节是 L4 多 Agent 通信模式的基础铺垫
