import httpx
import json
import random
import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")

def search_tool(query: str) -> str:
    mock_data = {
        "法国首都": "巴黎",
        "德国首都": "柏林",
        "Python": "Python是一种高级编程语言，由Guido van Rossum于1991年创建。",
        "地球半径": "地球的平均半径约为6371公里。",
        "月球半径": "月球的平均半径约为1737公里。",
        "圆周率": "π ≈ 3.141592653589793",
        "中国人口": "中国2023年人口约14.1亿。",
        "印度人口": "印度2023年人口约14.2亿。",
        "光速": "真空中的光速为299,792,458米/秒。",
        "地球到月球距离": "地球到月球的平均距离约为384,400公里。",
        "GDP": "GDP是国内生产总值的缩写，是衡量一个国家经济状况的重要指标。",
    }
    return mock_data.get(query, f"未找到关于'{query}'的信息")

def calculator_tool(expression: str) -> str:
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

class NodeType(Enum):
    ROOT = "root"
    THOUGHT = "thought"
    ACTION = "action"
    RESULT = "result"
    ANSWER = "answer"

@dataclass
class MCTSNode:
    node_id: str
    node_type: NodeType
    content: str
    parent: Optional['MCTSNode'] = None
    children: List['MCTSNode'] = field(default_factory=list)
    visits: int = 0
    wins: float = 0.0
    score: float = 0.0
    terminal: bool = False
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    
    @property
    def value(self) -> float:
        if self.visits == 0:
            return float('inf')
        return self.wins / self.visits
    
    def uct_score(self, exploration_weight: float = 1.414) -> float:
        if self.visits == 0:
            return float('inf')
        parent_visits = self.parent.visits if self.parent else 1
        exploitation = self.wins / self.visits
        exploration = exploration_weight * math.sqrt(math.log(parent_visits) / self.visits)
        return exploitation + exploration
    
    def add_child(self, child: 'MCTSNode'):
        child.parent = self
        self.children.append(child)
    
    def is_leaf(self) -> bool:
        return len(self.children) == 0
    
    def to_dict(self):
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "content": self.content,
            "visits": self.visits,
            "wins": self.wins,
            "score": self.score,
            "terminal": self.terminal
        }

class MonteCarloTreeSearch:
    def __init__(self, max_iterations: int = 50, max_depth: int = 10, exploration_weight: float = 1.414,
                 early_stopping_threshold: float = 0.95, early_stopping_patience: int = 5,
                 convergence_threshold: float = 0.001):
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.exploration_weight = exploration_weight
        self.early_stopping_threshold = early_stopping_threshold
        self.early_stopping_patience = early_stopping_patience
        self.convergence_threshold = convergence_threshold
        self.root: Optional[MCTSNode] = None
        self.node_count = 0
        self.client = httpx.AsyncClient(timeout=30)
        self.best_value_history: List[float] = []
        self.consecutive_no_improvement = 0
    
    def _create_node(self, node_type: NodeType, content: str, terminal: bool = False) -> MCTSNode:
        self.node_count += 1
        return MCTSNode(
            node_id=f"node_{self.node_count}",
            node_type=node_type,
            content=content,
            terminal=terminal
        )
    
    def _select(self, node: MCTSNode) -> MCTSNode:
        while not node.is_leaf() and not node.terminal:
            best_child = max(node.children, key=lambda c: c.uct_score(self.exploration_weight))
            node = best_child
        return node
    
    async def _expand(self, node: MCTSNode, question: str) -> MCTSNode:
        if node.terminal or len(node.children) > 0:
            return node
        
        if node.node_type == NodeType.ANSWER:
            node.terminal = True
            return node
        
        context = self._get_context(node)
        
        if node.node_type in [NodeType.ROOT, NodeType.RESULT]:
            thoughts = await self._generate_thoughts(context, question, num_thoughts=3)
            for thought in thoughts:
                thought_node = self._create_node(NodeType.THOUGHT, thought)
                node.add_child(thought_node)
        
        elif node.node_type == NodeType.THOUGHT:
            action_decision = await self._decide_action(node.content, context)
            action_name = action_decision.get("action_name", "none")
            action_args = action_decision.get("action_args", {})
            
            if action_name != "none":
                action_content = f"Action: {action_name}({action_args})"
                action_node = self._create_node(NodeType.ACTION, action_content)
                node.add_child(action_node)
            else:
                answer_node = self._create_node(NodeType.ANSWER, f"Answer: {node.content}", terminal=True)
                node.add_child(answer_node)
        
        elif node.node_type == NodeType.ACTION:
            action_name, action_args = self._parse_action(node.content)
            result = self._execute_action(action_name, action_args)
            
            if "错误" in result or "未找到" in result:
                result_node = self._create_node(NodeType.RESULT, result)
            else:
                result_node = self._create_node(NodeType.RESULT, result)
            node.add_child(result_node)
        
        if node.children:
            return random.choice(node.children)
        return node
    
    async def _simulate(self, node: MCTSNode, question: str, depth: int = 0) -> float:
        if depth >= self.max_depth or node.terminal:
            return await self._evaluate_node(node, question)
        
        context = self._get_context(node)
        
        if node.node_type == NodeType.RESULT:
            thoughts = await self._generate_thoughts(context, question, num_thoughts=2)
            thought = random.choice(thoughts)
            return await self._evaluate_thought(thought, question)
        
        elif node.node_type == NodeType.THOUGHT:
            return await self._evaluate_thought(node.content, question)
        
        elif node.node_type == NodeType.ACTION:
            return 0.5
        
        return 0.0
    
    def _backpropagate(self, node: MCTSNode, reward: float):
        while node is not None:
            node.visits += 1
            node.wins += reward
            node = node.parent
    
    def _get_context(self, node: MCTSNode) -> str:
        context_parts = []
        current = node.parent
        while current:
            context_parts.append(f"[{current.node_type.value}] {current.content[:50]}")
            current = current.parent
        return "\n".join(reversed(context_parts))
    
    async def _generate_thoughts(self, context: str, question: str, num_thoughts: int = 3) -> List[str]:
        prompt = f"""
问题: {question}

上下文:
{context}

请生成 {num_thoughts} 个下一步思考方向：

输出格式（JSON）:
{{
  "thoughts": ["思考1", "思考2", "思考3"]
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
                    "temperature": 0.9,
                    "max_tokens": 400,
                    "response_format": {"type": "json_object"}
                }
            )
            response.raise_for_status()
            data = response.json()
            result = json.loads(data["choices"][0]["message"]["content"])
            return result.get("thoughts", ["继续分析..."])
        except Exception as e:
            return ["继续分析..."]
    
    async def _decide_action(self, thought: str, context: str) -> Dict[str, Any]:
        prompt = f"""
思考: {thought}
上下文: {context}

可用工具:
- search(query: str): 搜索信息
- calculator(expression: str): 计算

请决定下一步行动。输出 JSON:
{{
  "action_name": "工具名称或 none",
  "action_args": {{参数}}
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
                    "max_tokens": 300,
                    "response_format": {"type": "json_object"}
                }
            )
            response.raise_for_status()
            data = response.json()
            return json.loads(data["choices"][0]["message"]["content"])
        except Exception as e:
            return {"action_name": "none", "action_args": {}}
    
    def _parse_action(self, action_content: str) -> Tuple[str, Dict[str, Any]]:
        try:
            import re
            match = re.match(r"Action: (\w+)\((.*)\)", action_content)
            if match:
                action_name = match.group(1)
                args_str = match.group(2)
                try:
                    args_str = args_str.replace("'", "\"")
                    args = json.loads(args_str)
                except:
                    try:
                        import ast
                        args = ast.literal_eval(args_str)
                    except:
                        args = {}
                return action_name, args
        except:
            pass
        return "none", {}
    
    def _execute_action(self, action_name: str, action_args: Dict[str, Any]) -> str:
        if action_name == "none":
            return "无需工具"
        if action_name not in TOOLS:
            return f"未知工具: {action_name}"
        try:
            return TOOLS[action_name](**action_args)
        except Exception as e:
            return f"执行错误: {e}"
    
    async def _evaluate_node(self, node: MCTSNode, question: str) -> float:
        prompt = f"""
问题: {question}
节点内容: {node.content}

请评估这个节点对解决问题的贡献，分数0-10：

输出格式（JSON）:
{{
  "score": 8.5
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
                    "max_tokens": 100,
                    "response_format": {"type": "json_object"}
                }
            )
            response.raise_for_status()
            data = response.json()
            result = json.loads(data["choices"][0]["message"]["content"])
            return result.get("score", 5.0) / 10.0
        except Exception as e:
            return 0.5
    
    async def _evaluate_thought(self, thought: str, question: str) -> float:
        return await self._evaluate_node(MCTSNode(node_id="temp", node_type=NodeType.THOUGHT, content=thought), question)
    
    def _print_tree(self, node: MCTSNode, indent: int = 0):
        prefix = "  " * indent
        status = "*" if node.terminal else ""
        print(f"{prefix}{node.node_id} [{node.node_type.value}]: {node.content[:40]}... (v={node.visits}, w={node.wins:.2f}, val={node.value:.2f}){status}")
        for child in sorted(node.children, key=lambda c: -c.visits):
            self._print_tree(child, indent + 1)
    
    def _get_best_path(self) -> List[MCTSNode]:
        if not self.root:
            return []
        
        path = []
        current = self.root
        
        while current and not current.terminal:
            path.append(current)
            if current.children:
                current = max(current.children, key=lambda c: c.value)
            else:
                break
        
        if current:
            path.append(current)
        
        return path
    
    async def solve(self, question: str) -> Tuple[str, List[MCTSNode]]:
        self.root = self._create_node(NodeType.ROOT, question)
        self.node_count = 0
        self.best_value_history = []
        self.consecutive_no_improvement = 0
        
        print(f"\n{'='*80}")
        print(f"🎲 Monte Carlo Tree Search 开始推理")
        print(f"问题: {question}")
        print(f"最大迭代次数: {self.max_iterations}, 最大深度: {self.max_depth}")
        print(f"早停阈值: {self.early_stopping_threshold}, 收敛阈值: {self.convergence_threshold}")
        print(f"{'='*80}")
        
        for iteration in range(self.max_iterations):
            if iteration % 10 == 0 or iteration < 5:
                print(f"\n迭代 {iteration}/{self.max_iterations}...")
            
            selected = self._select(self.root)
            
            expanded = await self._expand(selected, question)
            
            reward = await self._simulate(expanded, question)
            
            self._backpropagate(expanded, reward)
            
            if self.root.children:
                best_child = max(self.root.children, key=lambda c: c.value)
                current_best_value = best_child.value
                
                self.best_value_history.append(current_best_value)
                
                if len(self.best_value_history) > 1:
                    prev_best = self.best_value_history[-2]
                    
                    if abs(current_best_value - prev_best) < self.convergence_threshold:
                        self.consecutive_no_improvement += 1
                    else:
                        self.consecutive_no_improvement = 0
                    
                    if current_best_value >= self.early_stopping_threshold:
                        if self.consecutive_no_improvement >= 2:
                            print(f"\n🛑 早停触发！当前最优值 {current_best_value:.3f} >= 阈值 {self.early_stopping_threshold}")
                            print(f"   连续 {self.consecutive_no_improvement} 次迭代无明显提升")
                            break
                    
                    if self.consecutive_no_improvement >= self.early_stopping_patience:
                        print(f"\n🛑 收敛停止！连续 {self.consecutive_no_improvement} 次迭代无明显提升")
                        break
        
        print("\n📊 搜索完成！")
        print(f"   实际迭代次数: {iteration + 1}")
        print(f"   最终最优值: {self.best_value_history[-1] if self.best_value_history else 0:.3f}")
        print("\n🌳 最终搜索树结构:")
        self._print_tree(self.root)
        
        best_path = self._get_best_path()
        
        print("\n🏆 最优路径:")
        for i, node in enumerate(best_path):
            print(f"  {i}. [{node.node_type.value}] {node.content[:60]}... (访问次数: {node.visits}, 价值: {node.value:.3f})")
        
        final_answer = ""
        for node in reversed(best_path):
            if node.node_type == NodeType.ANSWER:
                final_answer = node.content.replace("Answer: ", "")
                break
        
        if not final_answer:
            final_answer = "未找到明确答案"
        
        return final_answer, best_path

async def main():
    mcts = MonteCarloTreeSearch(max_iterations=30, max_depth=8)
    
    questions = [
        "地球的半径是6371公里，月球的半径是1737公里。地球的体积是月球体积的几倍？",
        "光从地球到月球需要多长时间？"
    ]
    
    for i, question in enumerate(questions, 1):
        print(f"\n{'='*80}")
        print(f"📊 测试 {i}: {question}")
        print(f"{'='*80}")
        
        answer, path = await mcts.solve(question)
        
        print(f"\n{'='*80}")
        print(f"🎯 最终答案: {answer}")
        print(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(main())