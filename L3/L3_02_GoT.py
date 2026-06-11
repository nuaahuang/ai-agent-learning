import httpx
import json
from typing import Dict, Any, List, Optional, Set
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
        "光速": "真空中的光速为299,792,458米/秒。",
        "地球到月球距离": "地球到月球的平均距离约为384,400公里。",
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
# 3. GoT 核心数据结构
# ========================

class NodeType(Enum):
    """节点类型"""
    INPUT = "input"            # 输入节点（问题）
    THOUGHT = "thought"        # 思考节点
    ACTION = "action"          # 行动节点
    RESULT = "result"          # 结果节点
    ANSWER = "answer"          # 答案节点
    REFLECT = "reflect"        # 反思节点

@dataclass
class GraphNode:
    """推理图的节点"""
    node_id: str
    node_type: NodeType
    content: str
    score: float = 0.0
    visited: bool = False
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self):
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "content": self.content,
            "score": self.score,
            "timestamp": self.timestamp
        }

@dataclass
class Edge:
    """节点之间的边"""
    from_node_id: str
    to_node_id: str
    label: Optional[str] = None
    weight: float = 1.0
    directed: bool = True

class GraphOfThoughts:
    """Graph of Thoughts 实现"""
    
    def __init__(self, max_nodes: int = 50, max_iterations: int = 20):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[Edge] = []
        self.max_nodes = max_nodes
        self.max_iterations = max_iterations
        self.node_count = 0
        self.client = httpx.AsyncClient(timeout=30)
        self.input_node_id: Optional[str] = None
        self.answer_node_ids: List[str] = []
    
    def _create_node(self, node_type: NodeType, content: str, **kwargs) -> GraphNode:
        """创建新节点"""
        self.node_count += 1
        node = GraphNode(
            node_id=f"node_{self.node_count}",
            node_type=node_type,
            content=content,
            **kwargs
        )
        self.nodes[node.node_id] = node
        return node
    
    def _add_edge(self, from_node: GraphNode, to_node: GraphNode, label: str = None, weight: float = 1.0):
        """添加边"""
        edge = Edge(
            from_node_id=from_node.node_id,
            to_node_id=to_node.node_id,
            label=label,
            weight=weight
        )
        self.edges.append(edge)
    
    def _get_neighbors(self, node_id: str) -> List[GraphNode]:
        """获取节点的邻居"""
        neighbors = []
        for edge in self.edges:
            if edge.from_node_id == node_id:
                if edge.to_node_id in self.nodes:
                    neighbors.append(self.nodes[edge.to_node_id])
        return neighbors
    
    def _get_predecessors(self, node_id: str) -> List[GraphNode]:
        """获取节点的前驱节点"""
        predecessors = []
        for edge in self.edges:
            if edge.to_node_id == node_id:
                if edge.from_node_id in self.nodes:
                    predecessors.append(self.nodes[edge.from_node_id])
        return predecessors
    
    def _get_node_context(self, node: GraphNode) -> str:
        """获取节点的上下文（前驱节点内容）"""
        predecessors = self._get_predecessors(node.node_id)
        if not predecessors:
            return "无前置上下文"
        
        context_parts = []
        for pred in predecessors:
            context_parts.append(f"[{pred.node_type.value}] {pred.content[:80]}")
        
        return "\n".join(context_parts)
    
    async def _generate_thoughts(self, context: str, question: str, num_thoughts: int = 3) -> List[str]:
        """生成多个思考方向"""
        prompt = f"""
问题: {question}

当前上下文:
{context}

请从不同角度思考，生成 {num_thoughts} 个可能的下一步思考方向。
每个思考应该是一个完整的推理步骤，要有多样性和创造性。

输出格式（JSON）:
{{
  "thoughts": [
    "思考方向1...",
    "思考方向2...",
    "思考方向3..."
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
            result = json.loads(data["choices"][0]["message"]["content"])
            return result.get("thoughts", [])
            
        except Exception as e:
            print(f"  ❌ 生成思考失败: {e}")
            return [f"继续分析问题..."]

    async def _evaluate_nodes(self, node_ids: List[str], question: str) -> List[float]:
        """评估多个节点的质量"""
        nodes_text = "\n".join([
            f"[{i}] [{self.nodes[nid].node_type.value}] {self.nodes[nid].content[:100]}"
            for i, nid in enumerate(node_ids)
        ])
        
        prompt = f"""
问题: {question}

以下是推理图中的多个节点，请评估每个节点的质量和有用性：

{nodes_text}

评估标准：
- 是否直接针对问题？
- 逻辑是否合理？
- 是否有助于解决问题？

输出格式（JSON）:
{{
  "evaluations": [
    {{"node_index": 0, "score": 8.5, "reasoning": "..."}},
    {{"node_index": 1, "score": 6.0, "reasoning": "..."}}
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
            result = json.loads(data["choices"][0]["message"]["content"])
            
            scores = [5.0] * len(node_ids)
            for eval_item in result.get("evaluations", []):
                idx = eval_item.get("node_index", 0)
                if 0 <= idx < len(node_ids):
                    scores[idx] = eval_item.get("score", 5.0)
            
            return scores
            
        except Exception as e:
            print(f"  ❌ 评估节点失败: {e}")
            return [5.0] * len(node_ids)

    async def _decide_action(self, thought: str, context: str) -> Dict[str, Any]:
        """决定下一步行动"""
        prompt = f"""
当前思考: {thought}

上下文:
{context}

可用工具:
- search(query: str): 搜索信息
- calculator(expression: str): 计算数学表达式
- get_current_time(): 获取当前时间

请根据这个思考，决定下一步行动。

输出格式（JSON）:
{{
  "thought": "选择的思考路径",
  "action_name": "工具名称或 'none'",
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
            return json.loads(data["choices"][0]["message"]["content"])
            
        except Exception as e:
            print(f"  ❌ 决定行动失败: {e}")
            return {"action_name": "none", "action_args": {}}

    def _execute_action(self, action_name: str, action_args: Dict[str, Any]) -> str:
        """执行工具"""
        if action_name == "none":
            return "无需工具，直接推理"
        
        if action_name not in TOOLS:
            return f"错误：未知工具 '{action_name}'"
        
        try:
            tool_func = TOOLS[action_name]
            result = tool_func(**action_args)
            return result
        except Exception as e:
            return f"工具执行错误: {e}"

    async def _reflect_on_path(self, path: List[GraphNode], question: str) -> str:
        """反思推理路径"""
        path_text = "\n".join([
            f"{i+1}. [{node.node_type.value}] {node.content}"
            for i, node in enumerate(path)
        ])
        
        prompt = f"""
问题: {question}

当前推理路径:
{path_text}

请反思这个推理路径：
1. 是否正确？
2. 是否遗漏了重要步骤？
3. 是否需要回溯或调整？

输出格式（JSON）:
{{
  "is_correct": true/false,
  "feedback": "反思意见",
  "suggestion": "建议的改进方向或 'continue'"
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
                    "max_tokens": 400,
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            data = response.json()
            result = json.loads(data["choices"][0]["message"]["content"])
            return result
            
        except Exception as e:
            print(f"  ❌ 反思失败: {e}")
            return {"is_correct": True, "feedback": "无法反思", "suggestion": "continue"}

    def _find_best_path(self, start_id: str = None) -> List[GraphNode]:
        """找到最优路径（基于评分）"""
        if not start_id:
            start_id = self.input_node_id
        
        if not start_id or start_id not in self.nodes:
            return []
        
        best_paths = []
        current_path = []
        
        def dfs(node_id: str):
            node = self.nodes.get(node_id)
            if not node:
                return
            
            if node.node_type == NodeType.ANSWER:
                current_path.append(node)
                path_score = sum(n.score for n in current_path)
                best_paths.append((path_score, current_path.copy()))
                current_path.pop()
                return
            
            if node.node_id in [n.node_id for n in current_path]:
                return
            
            current_path.append(node)
            neighbors = self._get_neighbors(node_id)
            
            for neighbor in sorted(neighbors, key=lambda x: -x.score):
                dfs(neighbor.node_id)
            
            current_path.pop()
        
        dfs(start_id)
        
        if not best_paths:
            return []
        
        best_paths.sort(key=lambda x: -x[0])
        return best_paths[0][1]

    async def solve(self, question: str) -> str:
        """使用 Graph of Thoughts 解决问题"""
        
        print(f"\n{'='*80}")
        print(f"🔗 Graph of Thoughts 开始推理")
        print(f"问题: {question}")
        print(f"最大节点数: {self.max_nodes}, 最大迭代次数: {self.max_iterations}")
        print(f"{'='*80}")
        
        input_node = self._create_node(NodeType.INPUT, question)
        self.input_node_id = input_node.node_id
        print(f"📥 创建输入节点: {input_node.node_id}")
        
        visited: Set[str] = set()
        queue = [input_node]
        iteration = 0
        
        while queue and iteration < self.max_iterations and len(self.nodes) < self.max_nodes:
            iteration += 1
            print(f"\n{'─'*60}")
            print(f"🔄 迭代 {iteration}: 队列中有 {len(queue)} 个节点")
            print(f"{'─'*60}")
            
            current_node = queue.pop(0)
            
            if current_node.node_id in visited:
                continue
            visited.add(current_node.node_id)
            
            if current_node.node_type == NodeType.ANSWER:
                continue
            
            context = self._get_node_context(current_node)
            print(f"\n📍 当前节点: [{current_node.node_type.value}] {current_node.content[:60]}...")
            
            thoughts = await self._generate_thoughts(context, question, num_thoughts=4)
            
            thought_nodes = []
            for thought in thoughts:
                thought_node = self._create_node(NodeType.THOUGHT, thought)
                self._add_edge(current_node, thought_node, label="thought")
                thought_nodes.append(thought_node)
                print(f"  🌱 创建思考节点: {thought_node.node_id}")
            
            if thought_nodes:
                thought_ids = [n.node_id for n in thought_nodes]
                scores = await self._evaluate_nodes(thought_ids, question)
                
                for node, score in zip(thought_nodes, scores):
                    node.score = score
                    print(f"  📝 评估分数: {node.node_id} = {score:.1f}")
                
                for thought_node in sorted(thought_nodes, key=lambda x: -x.score)[:3]:
                    action_decision = await self._decide_action(thought_node.content, context)
                    action_name = action_decision.get("action_name", "none")
                    action_args = action_decision.get("action_args", {})
                    
                    if action_name != "none":
                        action_node = self._create_node(
                            NodeType.ACTION,
                            f"Action: {action_name}({action_args})"
                        )
                        self._add_edge(thought_node, action_node, label="action")
                        
                        result = self._execute_action(action_name, action_args)
                        result_node = self._create_node(NodeType.RESULT, result)
                        result_node.score = thought_node.score * 0.8
                        self._add_edge(action_node, result_node, label="result")
                        
                        print(f"    🛠️ Action: {action_name}({action_args})")
                        print(f"    📊 Result: {result[:50]}...")
                        
                        if "错误" not in result:
                            queue.append(result_node)
                    else:
                        answer_node = self._create_node(
                            NodeType.ANSWER,
                            f"Final Answer: {thought_node.content}"
                        )
                        answer_node.score = thought_node.score
                        self._add_edge(thought_node, answer_node, label="answer")
                        self.answer_node_ids.append(answer_node.node_id)
                        print(f"    💡 生成答案节点: {answer_node.node_id}")
            
            if self.answer_node_ids:
                reflect_result = await self._reflect_on_path(
                    [self.nodes[nid] for nid in self.answer_node_ids],
                    question
                )
                if reflect_result.get("is_correct", True):
                    print(f"    ✅ 反思通过")
                    break
                else:
                    print(f"    🔄 反思建议: {reflect_result.get('suggestion', '')}")
                    queue.extend(thought_nodes)
        
        print(f"\n{'='*60}")
        print(f"🏆 寻找最优路径")
        print(f"{'='*60}")
        
        best_path = self._find_best_path()
        
        if best_path:
            print(f"\n最优路径:")
            for i, node in enumerate(best_path):
                print(f"  {i}. [{node.node_type.value}] {node.content[:80]} (分数:{node.score:.2f})")
            
            final_answer = await self._generate_final_answer(question, best_path)
            return final_answer
        else:
            return "无法找到合适的解决方案"

    async def _generate_final_answer(self, question: str, path: List[GraphNode]) -> str:
        """根据最优路径生成最终答案"""
        
        path_text = "\n".join([
            f"Step {i}: [{node.node_type.value}] {node.content}"
            for i, node in enumerate(path)
        ])
        
        prompt = f"""
问题: {question}

以下是推理路径:
{path_text}

请根据这个推理路径，生成一个完整、自然的最终答案。

输出格式（JSON）:
{{
  "final_answer": "完整的最终答案",
  "confidence": "high/medium/low"
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
            result = json.loads(data["choices"][0]["message"]["content"])
            
            print(f"\n{'='*60}")
            print(f"🎯 最终答案:")
            print(f"{result.get('final_answer', '无法生成答案')}")
            print(f"置信度: {result.get('confidence', 'medium')}")
            print(f"{'='*60}")
            
            return result.get("final_answer", "无法生成答案")
            
        except Exception as e:
            print(f"❌ 生成最终答案失败: {e}")
            return "无法生成最终答案"
    
    async def close(self):
        await self.client.aclose()

# ========================
# 可视化工具
# ========================
def print_graph(got: GraphOfThoughts):
    """打印图结构"""
    print("\n📊 推理图结构:")
    print("-" * 50)
    
    for node_id, node in got.nodes.items():
        neighbors = got._get_neighbors(node_id)
        if neighbors:
            print(f"[{node.node_type.value}] {node.content[:50]}...")
            for neighbor in neighbors:
                print(f"  └─> [{neighbor.node_type.value}] {neighbor.content[:40]}...")
        else:
            print(f"[{node.node_type.value}] {node.content[:50]}... (叶子节点)")

# ========================
# 测试
# ========================
async def main():
    print("🧪 测试 Graph of Thoughts")
    
    got = GraphOfThoughts(max_nodes=30, max_iterations=10)
    
    try:
        print("\n" + "="*80)
        print("📊 测试 1: 地理计算问题")
        result1 = await got.solve("地球的半径是6371公里，月球的半径是1737公里。地球的直径是月球直径的几倍？")
        print(f"\n测试1结果: {result1}")
        
        print("\n" + "="*80)
        print("📊 测试 2: 人口比较问题")
        result2 = await got.solve("中国和印度哪个国家人口更多？多多少？")
        print(f"\n测试2结果: {result2}")
        
        print("\n" + "="*80)
        print("📊 测试 3: 混合问题")
        result3 = await got.solve("光从地球到月球需要多长时间？（使用搜索工具获取距离和光速）")
        print(f"\n测试3结果: {result3}")
        
    finally:
        await got.close()


if __name__ == "__main__":
    asyncio.run(main())