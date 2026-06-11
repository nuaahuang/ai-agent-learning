import httpx
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio
from dataclasses import dataclass
from enum import Enum
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")

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


TOOLS = {
    "search": search_tool,
    "calculator": calculator_tool,
}

# ========================
# 3. ToT 核心数据结构
# ========================

class NodeType(Enum):
    ROOT = "root"          
    THOUGHT = "thought"    
    ACTION = "action"      
    RESULT = "result"      
    ANSWER = "answer"      

@dataclass
class TreeNode:
    node_id: str
    node_type: NodeType
    content: str           
    score: float = 0.0     
    parent: Optional['TreeNode'] = None
    children: List['TreeNode'] = None
    depth: int = 0         
    path_score: float = 0.0 
    created_at: float = 0.0 
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
        self.created_at = datetime.now().timestamp()
    
    def add_child(self, child: 'TreeNode'):
        child.parent = self
        child.depth = self.depth + 1
        self.children.append(child)
    
    def get_path_to_root(self) -> List[str]:
        path = []
        current = self
        while current:
            path.insert(0, current.content[:50])
            current = current.parent
        return path
    
    def get_depth(self) -> int:
        return self.depth

class ThoughtGeneration(BaseModel):
    thoughts: List[str] = Field(..., description="多个可能的思考方向")

class ActionDecision(BaseModel):
    thought: str = Field(..., description="选择的思考路径")
    action_name: str = Field(..., description="工具名称")
    action_args: Dict[str, Any] = Field(default_factory=dict, description="工具参数")

class BranchEvaluation(BaseModel):
    branch_index: int = Field(..., description="分支索引")
    score: float = Field(..., ge=0, le=10, description="评分 (0-10)")
    reasoning: str = Field(..., description="评分理由")

class Evaluations(BaseModel):
    evaluations: List[BranchEvaluation] = Field(..., description="所有分支的评估结果")

class FinalAnswer(BaseModel):
    best_path: List[str] = Field(..., description="最优路径")
    final_answer: str = Field(..., description="最终答案")
    confidence: str = Field("medium", description="置信度: high/medium/low")

# ========================
# 4. 优化版 ToT 核心算法
# ========================
class TreeOfThoughtsOptimized:
    """Tree of Thoughts 优化版
    
    优化特性：
    1. 智能剪枝策略 - 动态过滤低质量分支
    2. 早停机制 - 提前终止无效搜索
    3. 路径评分衰减 - 考虑深度和时间因素
    """
    
    def __init__(self, 
                 min_branching_factor: int = 1, 
                 max_branching_factor: int = 5, 
                 max_depth: int = 3,
                 early_stop_threshold: float = 9.0,
                 decay_factor: float = 0.9,
                 pruning_threshold: float = 2.0):
        self.min_branching_factor = min_branching_factor
        self.max_branching_factor = max_branching_factor
        self.max_depth = max_depth
        self.early_stop_threshold = early_stop_threshold  
        self.decay_factor = decay_factor  
        self.pruning_threshold = pruning_threshold  
        self.root: Optional[TreeNode] = None
        self.node_count = 0
        self.client = httpx.AsyncClient(timeout=30)
        self.best_path_score = -1
        self.early_stopped = False
        
        self.thresholds = {
            "high": 8.0,
            "medium": 5.0,
            "low": 3.0
        }
    
    def _create_node(self, node_type: NodeType, content: str) -> TreeNode:
        """创建一个新节点"""
        self.node_count += 1
        return TreeNode(
            node_id=f"node_{self.node_count}",
            node_type=node_type,
            content=content,
            depth=0
        )
    
    def _calculate_dynamic_branching_factor(self, scores: List[float]) -> int:
        """
        自动计算分支因子：
        - 如果有高分分支（>=8分），减少分支数（聚焦最优路径）
        - 如果分数普遍较低，增加分支数（探索更多可能性）
        - 根据平均分数动态调整
        """
        if not scores:
            return self.min_branching_factor
        
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        
        if max_score >= self.thresholds["high"]:
            high_count = sum(1 for s in scores if s >= self.thresholds["high"])
            return min(max(self.min_branching_factor, high_count), self.max_branching_factor)
        elif avg_score >= self.thresholds["medium"]:
            return (self.min_branching_factor + self.max_branching_factor) // 2
        elif avg_score < self.thresholds["low"]:
            return self.max_branching_factor
        else:
            return (self.min_branching_factor + self.max_branching_factor) // 2
    
    def _filter_promising_branches(self, thoughts: List[str], scores: List[float]) -> Tuple[List[str], List[float]]:
        """
        优化剪枝策略：
        1. 移除分数过低的分支（<pruning_threshold）
        2. 保持至少最小分支数
        3. 兄弟节点竞争剪枝（只保留前N个）
        """
        filtered = [(t, s) for t, s in zip(thoughts, scores) if s >= self.pruning_threshold]
        
        if len(filtered) < self.min_branching_factor:
            sorted_by_score = sorted(zip(thoughts, scores), key=lambda x: -x[1])
            filtered = sorted_by_score[:self.min_branching_factor]
        
        sorted_filtered = sorted(filtered, key=lambda x: -x[1])
        max_to_keep = min(len(sorted_filtered), self.max_branching_factor * 2)
        
        return [t for t, s in sorted_filtered[:max_to_keep]], [s for t, s in sorted_filtered[:max_to_keep]]
    
    def _calculate_path_score(self, node: TreeNode, current_score: float) -> float:
        """
        路径评分衰减计算：
        1. 深度衰减：路径越长，衰减越多
        2. 质量衰减：当前节点分数的加权
        3. 历史累积：综合考虑路径上所有节点
        """
        depth_penalty = self.decay_factor ** node.depth
        adjusted_score = current_score * depth_penalty
        
        if node.parent:
            adjusted_score += node.parent.path_score * 0.3
        
        return adjusted_score
    
    def _check_early_stop(self, current_best_score: float, depth: int) -> bool:
        """
        早停机制检查：
        1. 如果找到高分路径（>= early_stop_threshold），提前停止
        2. 如果所有分支质量过低，提前停止
        3. 如果路径分数收敛且深度较大，提前停止
        """
        if current_best_score >= self.early_stop_threshold:
            print(f"    ⚡ 早停触发：找到高分路径 ({current_best_score:.1f} >= {self.early_stop_threshold})")
            return True
        
        if depth >= self.max_depth - 1 and current_best_score < self.thresholds["low"]:
            print(f"    ⚡ 早停触发：低质量路径且已达最大深度")
            return True
        
        return False
    
    def _prune_by_sibling_competition(self, node: TreeNode) -> List[TreeNode]:
        """
        兄弟节点竞争剪枝：
        - 只保留分数最高的兄弟节点
        - 移除明显劣势的分支
        """
        if not node.parent or not node.parent.children:
            return []
        
        siblings = node.parent.children
        if len(siblings) <= 1:
            return []
        
        max_sibling_score = max(s.score for s in siblings)
        pruned = []
        
        for sibling in siblings:
            if sibling.score < max_sibling_score * 0.4:
                pruned.append(sibling)
        
        if pruned:
            print(f"    🔪 兄弟竞争剪枝：移除 {len(pruned)} 个劣势分支")
            node.parent.children = [s for s in siblings if s not in pruned]
        
        return pruned
    
    async def _generate_thoughts(self, context: str, question: str, desired_count: int = 3) -> List[str]:
        """生成多个思考方向"""
        
        prompt = f"""
问题: {question}

当前上下文:
{context}

请从不同角度思考，生成 {desired_count} 个可能的下一步思考方向。
每个思考应该是一个完整的推理步骤，要有多样性。

输出格式（JSON）:
{{
  "thoughts": [
    "第一个思考方向...",
    "第二个思考方向...",
    "第三个思考方向..."
  ]
}}
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
                    "temperature": 0.8,
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
{{
  "evaluations": [
    {{"branch_index": 0, "score": 8.5, "reasoning": "..."}},
    {{"branch_index": 1, "score": 6.0, "reasoning": "..."}}
  ]
}}
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
{{
  "thought": "选择的思考路径",
  "action_name": "工具名称",
  "action_args": {{}}
}}
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
        """使用优化版 ToT 解决问题"""
        
        print(f"\n{'='*80}")
        print(f"🌳 Tree of Thoughts (优化版)")
        print(f"问题: {question}")
        print(f"分支范围: {self.min_branching_factor}-{self.max_branching_factor}, 最大深度: {self.max_depth}")
        print(f"早停阈值: {self.early_stop_threshold}, 衰减因子: {self.decay_factor}")
        print(f"{'='*80}")
        
        self.root = self._create_node(NodeType.ROOT, question)
        self.best_path_score = -1
        self.early_stopped = False
        
        current_level = [self.root]
        depth = 0
        
        while current_level and depth < self.max_depth and not self.early_stopped:
            depth += 1
            print(f"\n{'─'*60}")
            print(f"📊 深度 {depth}: 当前有 {len(current_level)} 个节点")
            print(f"{'─'*60}")
            
            next_level = []
            
            for node in current_level:
                if self.early_stopped:
                    break
                    
                context = " -> ".join(node.get_path_to_root())
                print(f"\n  📍 节点 {node.node_id}: {node.content[:60]}...")
                
                initial_count = min(self.max_branching_factor * 2, 6)
                print(f"  🌱 生成 {initial_count} 个初始思考方向...")
                thoughts = await self._generate_thoughts(context, question, initial_count)
                
                print(f"  📝 评估思考方向...")
                scores = await self._evaluate_branches(thoughts, question)
                
                thoughts, scores = self._filter_promising_branches(thoughts, scores)
                
                dynamic_factor = self._calculate_dynamic_branching_factor(scores)
                print(f"  🎯 自动调整分支因子: {dynamic_factor} (分数范围: {min(scores):.1f}-{max(scores):.1f})")
                
                for i, (thought, score) in enumerate(zip(thoughts, scores)):
                    print(f"    [{i}] 分数={score:.1f}: {thought[:50]}...")
                
                top_indices = sorted(
                    range(len(scores)),
                    key=lambda i: scores[i],
                    reverse=True
                )[:dynamic_factor]
                
                for idx in top_indices:
                    if self.early_stopped:
                        break
                        
                    thought = thoughts[idx]
                    score = scores[idx]
                    
                    thought_node = self._create_node(NodeType.THOUGHT, thought)
                    thought_node.score = score
                    thought_node.path_score = self._calculate_path_score(thought_node, score)
                    node.add_child(thought_node)
                    
                    if thought_node.path_score > self.best_path_score:
                        self.best_path_score = thought_node.path_score
                    
                    if self._check_early_stop(self.best_path_score, depth):
                        self.early_stopped = True
                        break
                    
                    self._prune_by_sibling_competition(thought_node)
                    
                    print(f"    🔧 为分支 {idx} 决定行动...")
                    decision = await self._decide_action(thought, context)
                    
                    if decision and decision.action_name != "none":
                        result = await self._execute_action(decision)
                        
                        result_content = f"Action: {decision.action_name}({decision.action_args}) -> {result}"
                        result_node = self._create_node(NodeType.RESULT, result_content)
                        result_node.score = score * 0.8
                        result_node.path_score = self._calculate_path_score(result_node, score * 0.8)
                        thought_node.add_child(result_node)
                        
                        if "错误" not in result:
                            next_level.append(result_node)
                            print(f"      ✅ 结果: {result[:50]}...")
                            
                            if result_node.path_score > self.best_path_score:
                                self.best_path_score = result_node.path_score
                                
                            if self._check_early_stop(self.best_path_score, depth):
                                self.early_stopped = True
                        else:
                            print(f"      ❌ 错误: {result[:50]}...")
                    else:
                        answer_content = f"直接推理: {thought}"
                        answer_node = self._create_node(NodeType.ANSWER, answer_content)
                        answer_node.score = score
                        answer_node.path_score = self._calculate_path_score(answer_node, score)
                        thought_node.add_child(answer_node)
                        
                        if answer_node.path_score > self.best_path_score:
                            self.best_path_score = answer_node.path_score
                            
                        if self._check_early_stop(self.best_path_score, depth):
                            self.early_stopped = True
                            
                        print(f"      💡 直接推理，无需工具")
            
            current_level = next_level
        
        print(f"\n{'='*60}")
        print(f"🏆 选择最优路径 {'(早停)' if self.early_stopped else ''}")
        print(f"{'='*60}")
        
        best_path = self._find_best_path()
        
        if best_path:
            print(f"\n最优路径 (路径分数: {self.best_path_score:.2f}):")
            for i, node in enumerate(best_path):
                depth_marker = "  " * i
                print(f"{depth_marker}{i}. [{node.node_type.value}] {node.content[:80]} (分数:{node.score:.2f})")
            
            final_answer = await self._generate_final_answer(question, best_path)
            return final_answer
        else:
            return "无法找到合适的解决方案"

    def _find_best_path(self) -> List[TreeNode]:
        """找到最优路径（考虑路径评分衰减）"""
        
        best_score = -1
        best_path = []
        
        def dfs(node: TreeNode, current_path: List[TreeNode]):
            nonlocal best_score, best_path
            
            current_path.append(node)
            
            if not node.children:
                total_score = sum(n.path_score for n in current_path)
                if total_score > best_score:
                    best_score = total_score
                    best_path = current_path.copy()
            else:
                for child in sorted(node.children, key=lambda c: -c.path_score):
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
{{
  "best_path": ["step1", "step2", ...],
  "final_answer": "完整的最终答案",
  "confidence": "high"
}}
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
# 5. 测试
# ========================

async def main():
    print("🧪 测试 Tree of Thoughts (优化版)")
    
    tot = TreeOfThoughtsOptimized(
        min_branching_factor=1,
        max_branching_factor=5,
        max_depth=3,
        early_stop_threshold=9.0,
        decay_factor=0.9,
        pruning_threshold=2.0
    )
    
    try:
        print("\n" + "="*80)
        print("📊 测试 1: 地理计算问题")
        result1 = await tot.solve("地球的半径是6371公里，月球的半径是1737公里。地球的直径是月球直径的几倍？")
        print(f"\n测试1结果: {result1}")
        
        print("\n" + "="*80)
        print("📊 测试 2: 人口比较问题")
        result2 = await tot.solve("中国和印度哪个国家人口更多？多多少？")
        print(f"\n测试2结果: {result2}")
        
        print("\n" + "="*80)
        print("📊 测试 3: 复杂计算问题")
        result3 = await tot.solve("一个圆的半径是5厘米，它的面积是多少？（使用 π=3.14）")
        print(f"\n测试3结果: {result3}")
        
    finally:
        await tot.close()


if __name__ == "__main__":
    asyncio.run(main())