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
# 工具定义
# ========================
def search_tool(query: str) -> str:
    """搜索工具"""
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
# GoT 增强版核心数据结构
# ========================

class NodeType(Enum):
    INPUT = "input"
    THOUGHT = "thought"
    ACTION = "action"
    RESULT = "result"
    ANSWER = "answer"
    MERGE = "merge"  
    REFLECT = "reflect"

@dataclass
class GraphNode:
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
    from_node_id: str
    to_node_id: str
    label: Optional[str] = None
    weight: float = 1.0
    directed: bool = True
    connection_type: str = "default"  

class GraphOfThoughtsEnhanced:
    """增强版 Graph of Thoughts - 真正体现图结构优势"""
    
    def __init__(self, max_nodes: int = 100, max_iterations: int = 30):
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
        if len(self.nodes) >= self.max_nodes:
            raise ValueError("已达到最大节点数限制")
        
        self.node_count += 1
        node = GraphNode(
            node_id=f"node_{self.node_count}",
            node_type=node_type,
            content=content,
            **kwargs
        )
        self.nodes[node.node_id] = node
        return node
    
    def _add_edge(self, from_node: GraphNode, to_node: GraphNode, label: str = None, 
                  weight: float = 1.0, connection_type: str = "default"):
        """添加边 - 支持多种连接类型"""
        edge = Edge(
            from_node_id=from_node.node_id,
            to_node_id=to_node.node_id,
            label=label,
            weight=weight,
            connection_type=connection_type
        )
        self.edges.append(edge)
    
    def _get_neighbors(self, node_id: str) -> List[GraphNode]:
        """获取节点的邻居（后继节点）"""
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
    
    def _get_all_reachable_nodes(self, start_node_id: str) -> Set[str]:
        """获取从起始节点可达的所有节点（图遍历）"""
        reachable = set()
        queue = [start_node_id]
        
        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            reachable.add(current)
            
            for neighbor in self._get_neighbors(current):
                if neighbor.node_id not in reachable:
                    queue.append(neighbor.node_id)
        
        return reachable
    
    def _create_cross_connection(self, from_node: GraphNode, to_node: GraphNode, reason: str):
        """创建跨节点连接（GoT 核心特性）"""
        self._add_edge(from_node, to_node, label=reason, connection_type="cross")
        print(f"  🔗 创建跨连接: {from_node.node_id} -> {to_node.node_id} [{reason}]")
    
    def _merge_nodes(self, nodes: List[GraphNode], merged_content: str) -> GraphNode:
        """合并多个节点的信息到一个新节点（GoT 核心特性）"""
        merge_node = self._create_node(NodeType.MERGE, merged_content)
        merge_node.score = sum(n.score for n in nodes) / len(nodes)
        
        for node in nodes:
            self._add_edge(node, merge_node, label="merge", connection_type="merge")
        
        print(f"  🔀 合并节点: {[n.node_id for n in nodes]} -> {merge_node.node_id}")
        return merge_node
    
    async def _generate_thoughts(self, context: str, question: str, num_thoughts: int = 4) -> List[str]:
        """生成多个思考方向"""
        prompt = f"""
问题: {question}

当前上下文:
{context}

请从不同角度思考，生成 {num_thoughts} 个可能的下一步思考方向。
要求多样性，每个思考可以是：
1. 分析问题的不同方面
2. 提出不同的解决方案
3. 考虑不同的工具调用
4. 反思之前的推理

输出格式（JSON）:
{{
  "thoughts": [
    "思考方向1...",
    "思考方向2...",
    "思考方向3...",
    "思考方向4..."
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
    
    def _check_topic_relevance(self, content1: str, content2: str) -> bool:
        """判断两个内容是否讨论相关主题"""
        keywords1 = set([w for w in content1.split() if len(w) >= 2])
        keywords2 = set([w for w in content2.split() if len(w) >= 2])
        
        if not keywords1 or not keywords2:
            return False
        
        common = keywords1.intersection(keywords2)
        return len(common) >= 1 or len(common) / min(len(keywords1), len(keywords2)) >= 0.2
    
    def _find_relevant_nodes(self, target_node: GraphNode, exclude_ids: Set[str] = None) -> List[GraphNode]:
        """在图中找到与目标节点相关的其他节点"""
        if exclude_ids is None:
            exclude_ids = set()
        
        relevant_nodes = []
        exclude_ids.add(target_node.node_id)
        
        for node_id, node in self.nodes.items():
            if node_id in exclude_ids:
                continue
            
            if node.node_type in [NodeType.THOUGHT, NodeType.RESULT]:
                if self._check_topic_relevance(target_node.content, node.content):
                    relevant_nodes.append(node)
        
        return sorted(relevant_nodes, key=lambda x: -x.score)[:3]

    async def _reflect_and_adjust(self, current_nodes: List[GraphNode], question: str) -> Dict[str, Any]:
        """反思并决定是否跳转或回溯（GoT 核心特性）"""
        nodes_text = "\n".join([
            f"{i}. [{n.node_type.value}] {n.content[:100]} (分数:{n.score})"
            for i, n in enumerate(current_nodes)
        ])
        
        prompt = f"""
问题: {question}

当前推理节点:
{nodes_text}

请分析当前推理状态：
1. 是否需要回溯到之前的某个节点重新开始？
2. 是否需要跳转到图中的其他节点？
3. 是否需要合并某些节点的信息？
4. 是否可以直接得出答案？

输出格式（JSON）:
{{
  "action": "continue/backtrack/jump/merge/answer",
  "target_node_id": "目标节点ID（如果需要跳转）",
  "reason": "理由",
  "merged_content": "合并后的内容（如果是merge）"
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
                    "temperature": 0.3,
                    "max_tokens": 400,
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            data = response.json()
            return json.loads(data["choices"][0]["message"]["content"])
            
        except Exception as e:
            print(f"  ❌ 反思失败: {e}")
            return {"action": "continue", "reason": "无法反思"}

    def _find_best_path(self, start_id: str = None, end_types: List[NodeType] = None) -> List[GraphNode]:
        """找到最优路径（图版本）"""
        if not start_id:
            start_id = self.input_node_id
        
        if not start_id or start_id not in self.nodes:
            return []
        
        if end_types is None:
            end_types = [NodeType.ANSWER]
        
        best_paths = []
        current_path = []
        
        def dfs(node_id: str):
            node = self.nodes.get(node_id)
            if not node:
                return
            
            if node.node_type in end_types:
                current_path.append(node)
                path_score = sum(n.score for n in current_path)
                path_length = len(current_path)
                adjusted_score = path_score / path_length
                best_paths.append((adjusted_score, current_path.copy()))
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
        """使用增强版 GoT 解决问题"""
        
        print(f"\n{'='*80}")
        print(f"🔗 Graph of Thoughts (增强版) 开始推理")
        print(f"问题: {question}")
        print(f"最大节点数: {self.max_nodes}, 最大迭代次数: {self.max_iterations}")
        print(f"{'='*80}")
        
        input_node = self._create_node(NodeType.INPUT, question)
        self.input_node_id = input_node.node_id
        print(f"📥 创建输入节点: {input_node.node_id}")
        
        iteration = 0
        active_nodes = [input_node]
        explored_paths = []
        
        while active_nodes and iteration < self.max_iterations and len(self.nodes) < self.max_nodes:
            iteration += 1
            print(f"\n{'─'*60}")
            print(f"🔄 迭代 {iteration}: 活跃节点数: {len(active_nodes)}")
            print(f"{'─'*60}")
            
            new_active_nodes = []
            
            for current_node in active_nodes:
                if current_node.visited:
                    continue
                current_node.visited = True
                
                context = "\n".join([f"[{n.node_type.value}] {n.content[:80]}" 
                                   for n in self._get_predecessors(current_node.node_id)])
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
                    
                    top_thoughts = sorted(thought_nodes, key=lambda x: -x.score)[:3]
                    
                    for thought_node in top_thoughts:
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
                                new_active_nodes.append(result_node)
                            
                                if result_node.score >= 6.0:
                                    relevant_nodes = self._find_relevant_nodes(result_node)
                                    for relevant_node in relevant_nodes:
                                        if relevant_node != thought_node and relevant_node.score >= 5.0:
                                            self._create_cross_connection(result_node, relevant_node, "内容相关")
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
                answer_nodes = [self.nodes[nid] for nid in self.answer_node_ids]
                reflect_result = await self._reflect_and_adjust(answer_nodes, question)
                
                action = reflect_result.get("action", "continue")
                
                if action == "answer":
                    print(f"    ✅ 直接输出答案")
                    break
                elif action == "merge":
                    merged_content = reflect_result.get("merged_content", "")
                    if merged_content:
                        merged_node = self._merge_nodes(answer_nodes, merged_content)
                        new_active_nodes.append(merged_node)
                        print(f"    🔀 合并答案节点")
                elif action == "backtrack":
                    print(f"    🔄 回溯到之前的节点")
                    active_nodes = new_active_nodes + [input_node]
                    continue
                else:
                    print(f"    🔄 继续探索")
            
            active_nodes = new_active_nodes
        
        print(f"\n{'='*60}")
        print(f"🏆 寻找最优路径")
        print(f"{'='*60}")
        
        self._print_graph_summary()
        
        best_path = self._find_best_path()
        
        if best_path:
            print(f"\n最优路径:")
            for i, node in enumerate(best_path):
                print(f"  {i}. [{node.node_type.value}] {node.content[:80]} (分数:{node.score:.2f})")
            
            final_answer = await self._generate_final_answer(question, best_path)
            return final_answer
        else:
            return "无法找到合适的解决方案"

    def _print_graph_summary(self):
        """打印图结构摘要"""
        print(f"\n📊 推理图摘要:")
        print(f"  节点数: {len(self.nodes)}")
        print(f"  边数: {len(self.edges)}")
        print(f"  答案节点数: {len(self.answer_node_ids)}")
        
        cross_edges = [e for e in self.edges if e.connection_type == "cross"]
        merge_edges = [e for e in self.edges if e.connection_type == "merge"]
        print(f"  跨连接数: {len(cross_edges)}")
        print(f"  合并连接数: {len(merge_edges)}")

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
# 测试
# ========================
async def main():
    print("🧪 测试 Graph of Thoughts (增强版)")
    
    got = GraphOfThoughtsEnhanced(max_nodes=50, max_iterations=15)
    
    try:
        print("\n" + "="*80)
        print("📊 测试 1: 复杂计算问题")
        result1 = await got.solve("地球的半径是6371公里，月球的半径是1737公里。地球的体积是月球体积的几倍？（球体体积公式：4/3πr³）")
        print(f"\n测试1结果: {result1}")
        
        print("\n" + "="*80)
        print("📊 测试 2: 多步骤推理")
        result2 = await got.solve("光从地球到月球需要多长时间？请先搜索距离和光速，然后计算。")
        print(f"\n测试2结果: {result2}")
        
    finally:
        await got.close()


if __name__ == "__main__":
    asyncio.run(main())