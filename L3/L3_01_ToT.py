import httpx
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio
from dataclasses import dataclass
from enum import Enum

API_KEY = ""
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"

# ========================
# 2. 工具定义
# ========================
def search_tool(query: str) -> str:
    """搜索工具"""
    mock_data = {
        "法国首都": "巴黎",
        "德国首都": "柏林",
        "日本首都": "东京",
        "Python": "Python是一种高级编程语言，由Guido van Rossum于1991年创建。",
        "Java": "Java是一种面向对象的编程语言，由Sun Microsystems于1995年发布。",
        "JavaScript": "JavaScript是一种用于Web开发的脚本语言，由Brendan Eich于1995年创建。",
        "地球半径": "地球的平均半径约为6371公里。",
        "月球半径": "月球的平均半径约为1737公里。",
        "圆周率": "π ≈ 3.141592653589793",
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


TOOLS = {
    "search": search_tool,
    "calculator": calculator_tool,
}

# ========================
# 3. ToT 核心数据结构
# ========================

class NodeType(Enum):
    """节点类型"""
    ROOT = "root"          # 根节点（问题）
    THOUGHT = "thought"    # 思考节点
    ACTION = "action"      # 行动节点
    RESULT = "result"      # 结果节点
    ANSWER = "answer"      # 答案节点

@dataclass
class TreeNode:
    """ToT 树的节点"""
    node_id: str
    node_type: NodeType
    content: str           # 节点的内容（thought/action/result）
    score: float = 0.0     # 评估分数
    parent: Optional['TreeNode'] = None
    children: List['TreeNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
    
    def add_child(self, child: 'TreeNode'):
        child.parent = self
        self.children.append(child)
    
    def get_path_to_root(self) -> List[str]:
        """获取从根节点到当前节点的路径"""
        path = []
        current = self
        while current:
            path.insert(0, current.content[:50])
            current = current.parent
        return path
    
    def get_depth(self) -> int:
        """获取节点深度"""
        depth = 0
        current = self
        while current.parent:
            depth += 1
            current = current.parent
        return depth

class ThoughtGeneration(BaseModel):
    """生成多个思考分支"""
    thoughts: List[str] = Field(..., description="多个可能的思考方向")

class ActionDecision(BaseModel):
    """行动决策"""
    thought: str = Field(..., description="选择的思考路径")
    action_name: str = Field(..., description="工具名称")
    action_args: Dict[str, Any] = Field(default_factory=dict, description="工具参数")

class BranchEvaluation(BaseModel):
    """分支评估"""
    branch_index: int = Field(..., description="分支索引")
    score: float = Field(..., ge=0, le=10, description="评分 (0-10)")
    reasoning: str = Field(..., description="评分理由")

class Evaluations(BaseModel):
    """所有分支的评估"""
    evaluations: List[BranchEvaluation] = Field(..., description="所有分支的评估结果")

class FinalAnswer(BaseModel):
    """最终答案"""
    best_path: List[str] = Field(..., description="最优路径")
    final_answer: str = Field(..., description="最终答案")
    confidence: str = Field("medium", description="置信度: high/medium/low")

# ========================
# 4. ToT 核心算法
# ========================
class TreeOfThoughts:
    """Tree of Thoughts 实现"""
    def __init__(self, branching_factor: int = 3, max_depth: int = 3):
        self.branching_factor = branching_factor  # 每个节点的分支数
        self.max_depth = max_depth  # 最大深度
        self.root: Optional[TreeNode] = None
        self.node_count = 0
        self.client = httpx.AsyncClient(timeout=30)
    
    def _create_node(self, node_type: NodeType, content: str) -> TreeNode:
        """创建一个新节点"""
        self.node_count += 1
        return TreeNode(
            node_id=f"node_{self.node_count}",
            node_type=node_type,
            content=content
        )
    
    async def _generate_thoughts(self, context: str, question: str) -> List[str]:
        """生成多个思考方向"""
        
        prompt = f"""
问题: {question}

当前上下文:
{context}

请从不同角度思考，生成 {self.branching_factor} 个可能的下一步思考方向。
每个思考应该是一个完整的推理步骤。

输出格式（JSON）:
json

{{

"thoughts": [

"第一个思考方向...",

"第二个思考方向...",

"第三个思考方向..."

]

}}
复制
"""
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,  # 高温度鼓励多样性
                    "max_tokens": 800,
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            data = response.json()
            result = ThoughtGeneration(**json.loads(data["choices"][0]["message"]["content"]))
            return result.thoughts
            
        except Exception as e:
            print(f"  ❌ 生成思考失败: {e}")
            return [f"继续分析: {context[:50]}..."]

    async def _evaluate_branches(self, branches: List[str], question: str) -> List[float]:
        """评估多个分支的质量"""
        
        branches_text = "\n".join([
            f"[{i}] {branch}" for i, branch in enumerate(branches)
        ])
        
        prompt = f"""
问题: {question}

以下是多个可能的思考方向，请评估每个方向的可行性：

{branches_text}

评估标准：
- 是否直接针对问题？
- 逻辑是否合理？
- 是否有可能得到答案？

输出格式（JSON）:
json

{{

"evaluations": [

{{"branch_index": 0, "score": 8.5, "reasoning": "..."}},

{{"branch_index": 1, "score": 6.0, "reasoning": "..."}}

]

}}
复制
"""
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 600,
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            data = response.json()
            result = Evaluations(**json.loads(data["choices"][0]["message"]["content"]))
            
            # 转换为分数列表
            scores = [0.0] * len(branches)
            for eval_item in result.evaluations:
                if 0 <= eval_item.branch_index < len(branches):
                    scores[eval_item.branch_index] = eval_item.score
            
            return scores
            
        except Exception as e:
            print(f"  ❌ 评估分支失败: {e}")
            return [5.0] * len(branches)

    async def _decide_action(self, thought: str, context: str) -> Optional[ActionDecision]:
        """根据思考决定行动"""
        
        prompt = f"""
当前思考: {thought}

可用工具:
- search(query: str): 搜索信息
- calculator(expression: str): 计算数学表达式

请根据这个思考，决定下一步行动。

输出格式（JSON）:
json

{{

"thought": "选择的思考路径",

"action_name": "工具名称",

"action_args": {{}}

}}
复制
如果不需要工具，action_name 设为 "none"。
"""
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 400,
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            data = response.json()
            return ActionDecision(**json.loads(data["choices"][0]["message"]["content"]))
            
        except Exception as e:
            print(f"  ❌ 决定行动失败: {e}")
            return None

    async def _execute_action(self, decision: ActionDecision) -> str:
        """执行工具"""
        
        if decision.action_name == "none":
            return "无需工具，直接推理"
        
        if decision.action_name not in TOOLS:
            return f"错误：未知工具 '{decision.action_name}'"
        
        try:
            tool_func = TOOLS[decision.action_name]
            result = tool_func(**decision.action_args)
            return result
        except Exception as e:
            return f"工具执行错误: {e}"

    async def solve(self, question: str) -> str:
        """使用 ToT 解决问题"""
        
        print(f"\n{'='*80}")
        print(f"🌳 Tree of Thoughts 开始推理")
        print(f"问题: {question}")
        print(f"分支因子: {self.branching_factor}, 最大深度: {self.max_depth}")
        print(f"{'='*80}")
        
        # 创建根节点
        self.root = self._create_node(NodeType.ROOT, question)
        
        # BFS 遍历树
        current_level = [self.root]
        depth = 0
        
        while current_level and depth < self.max_depth:
            depth += 1
            print(f"\n{'─'*60}")
            print(f"📊 深度 {depth}: 当前有 {len(current_level)} 个节点")
            print(f"{'─'*60}")
            
            next_level = []
            
            for node in current_level:
                # 获取从根到当前节点的路径作为上下文
                context = " -> ".join(node.get_path_to_root())
                print(f"\n  📍 节点 {node.node_id}: {node.content[:60]}...")
                
                # Step 1: 生成多个思考方向
                print(f"  🌱 生成 {self.branching_factor} 个思考方向...")
                thoughts = await self._generate_thoughts(context, question)
                
                # Step 2: 评估这些思考方向
                print(f"  📝 评估思考方向...")
                scores = await self._evaluate_branches(thoughts, question)
                
                # 打印评估结果
                for i, (thought, score) in enumerate(zip(thoughts, scores)):
                    print(f"    [{i}] 分数={score:.1f}: {thought[:50]}...")
                
                # Step 3: 选择 Top-K 分支
                top_indices = sorted(
                    range(len(scores)),
                    key=lambda i: scores[i],
                    reverse=True
                )[:self.branching_factor]
                
                for idx in top_indices:
                    thought = thoughts[idx]
                    score = scores[idx]
                    
                    # 创建思考节点
                    thought_node = self._create_node(NodeType.THOUGHT, thought)
                    thought_node.score = score
                    node.add_child(thought_node)
                    
                    # Step 4: 决定行动
                    print(f"    🔧 为分支 {idx} 决定行动...")
                    decision = await self._decide_action(thought, context)
                    
                    if decision and decision.action_name != "none":
                        # 执行工具
                        result = await self._execute_action(decision)
                        
                        # 创建结果节点
                        result_content = f"Action: {decision.action_name}({decision.action_args}) -> {result}"
                        result_node = self._create_node(NodeType.RESULT, result_content)
                        thought_node.add_child(result_node)
                        
                        # 如果是有效的工具调用，加入下一层
                        if "错误" not in result:
                            next_level.append(result_node)
                            print(f"      ✅ 结果: {result[:50]}...")
                        else:
                            print(f"      ❌ 错误: {result[:50]}...")
                    else:
                        # 不需要工具，可能是最终答案
                        answer_content = f"直接推理: {thought}"
                        answer_node = self._create_node(NodeType.ANSWER, answer_content)
                        thought_node.add_child(answer_node)
                        print(f"      💡 直接推理，无需工具")
            
            current_level = next_level
        
        # ========== 选择最优路径 ==========
        print(f"\n{'='*60}")
        print(f"🏆 选择最优路径")
        print(f"{'='*60}")
        
        best_path = self._find_best_path()
        
        if best_path:
            print(f"\n最优路径:")
            for i, node in enumerate(best_path):
                print(f"  {i}. [{node.node_type.value}] {node.content[:80]}")
            
            # 生成最终答案
            final_answer = await self._generate_final_answer(question, best_path)
            return final_answer
        else:
            return "无法找到合适的解决方案"

    def _find_best_path(self) -> List[TreeNode]:
        """找到最优路径（分数最高的路径）"""
        
        best_score = -1
        best_path = []
        
        def dfs(node: TreeNode, current_path: List[TreeNode]):
            nonlocal best_score, best_path
            
            current_path.append(node)
            
            # 如果是叶子节点，计算路径总分
            if not node.children:
                total_score = sum(n.score for n in current_path)
                if total_score > best_score:
                    best_score = total_score
                    best_path = current_path.copy()
            else:
                for child in node.children:
                    dfs(child, current_path)
            
            current_path.pop()
        
        if self.root:
            dfs(self.root, [])
        
        return best_path

    async def _generate_final_answer(self, question: str, path: List[TreeNode]) -> str:
        """根据最优路径生成最终答案"""
        
        path_text = "\n".join([
            f"Step {i}: [{node.node_type.value}] {node.content}"
            for i, node in enumerate(path)
        ])
        
        prompt = f"""
问题: {question}

以下是解决问题的推理路径:

{path_text}

请根据这个推理路径，生成一个完整、自然的最终答案。

输出格式（JSON）:
json

{{

"best_path": ["step1", "step2", ...],

"final_answer": "完整的最终答案",

"confidence": "high"

}}
复制
"""
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 600,
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            data = response.json()
            result = FinalAnswer(**json.loads(data["choices"][0]["message"]["content"]))
            
            print(f"\n{'='*60}")
            print(f"🎯 最终答案:")
            print(f"{result.final_answer}")
            print(f"置信度: {result.confidence}")
            print(f"{'='*60}")
            
            return result.final_answer
            
        except Exception as e:
            print(f"❌ 生成最终答案失败: {e}")
            return "无法生成最终答案"
    
    async def close(self):
        await self.client.aclose()

# ========================
# 5. 可视化辅助
# ========================

def print_tree(node: TreeNode, indent: str = "", is_last: bool = True):
    """打印树结构"""
    
    marker = "└── " if is_last else "├── "
    score_str = f" [分数:{node.score:.1f}]" if node.score != 0 else ""
    
    print(f"{indent}{marker}{node.node_type.value}: {node.content[:50]}...{score_str}")
    
    if node.children:
        new_indent = indent + ("    " if is_last else "│   ")
        for i, child in enumerate(node.children):
            print_tree(child, new_indent, i == len(node.children) - 1)


# ========================
# 6. 测试
# ========================

async def main():
    print("🧪 测试 Tree of Thoughts")
    
    tot = TreeOfThoughts(branching_factor=3, max_depth=3)
    
    try:
        # 测试 1: 需要多步推理的问题
        print("\n" + "="*80)
        print("📊 测试 1: 地理计算问题")
        result1 = await tot.solve("地球的半径是6371公里，月球的半径是1737公里。地球的直径是月球直径的几倍？")
        print(f"\n测试1结果: {result1}")
        
        # 测试 2: 需要搜索的问题
        print("\n" + "="*80)
        print("📊 测试 2: 编程语言问题")
        result2 = await tot.solve("Python、Java和JavaScript这三种编程语言，哪个最先被创建？")
        print(f"\n测试2结果: {result2}")
        
        # 测试 3: 复杂计算问题
        print("\n" + "="*80)
        print("📊 测试 3: 复杂计算问题")
        result3 = await tot.solve("一个圆的半径是5厘米，它的面积是多少？（使用 π=3.14）")
        print(f"\n测试3结果: {result3}")
        
    finally:
        await tot.close()


if __name__ == "__main__":
    asyncio.run(main())
