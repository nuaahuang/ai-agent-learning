from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Tuple, Set
import asyncio
import uuid
from datetime import datetime
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionResult:
    task_id: str
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'output': self.output,
            'error': self.error,
            'retry_count': self.retry_count,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.end_time - self.start_time if self.start_time and self.end_time else None
        }


@dataclass
class TaskNode:
    task_id: str
    name: str
    func: Callable[..., Any]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 0
    max_retries: int = 3
    timeout: Optional[int] = None
    is_async: bool = False
    
    def __post_init__(self):
        self.is_async = asyncio.iscoroutinefunction(self.func)


class DAG:
    def __init__(self, name: str):
        self.name = name
        self.nodes: Dict[str, TaskNode] = {}
        self.edges: Dict[str, List[str]] = {}
    
    def add_node(self, node: TaskNode) -> None:
        if node.task_id in self.nodes:
            raise ValueError(f"任务节点已存在: {node.task_id}")
        
        self.nodes[node.task_id] = node
        self.edges[node.task_id] = []
    
    def add_edge(self, from_task_id: str, to_task_id: str) -> None:
        if from_task_id not in self.nodes:
            raise ValueError(f"源任务不存在: {from_task_id}")
        if to_task_id not in self.nodes:
            raise ValueError(f"目标任务不存在: {to_task_id}")
        
        if to_task_id not in self.edges[from_task_id]:
            self.edges[from_task_id].append(to_task_id)
        
        if from_task_id not in self.nodes[to_task_id].dependencies:
            self.nodes[to_task_id].dependencies.append(from_task_id)
    
    def get_nodes(self) -> List[TaskNode]:
        return list(self.nodes.values())
    
    def get_node(self, task_id: str) -> Optional[TaskNode]:
        return self.nodes.get(task_id)
    
    def get_successors(self, task_id: str) -> List[str]:
        return self.edges.get(task_id, [])
    
    def topological_sort(self) -> List[str]:
        in_degree: Dict[str, int] = {node.task_id: len(node.dependencies) for node in self.nodes.values()}
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            queue.sort(key=lambda x: -self.nodes[x].priority)
            task_id = queue.pop(0)
            result.append(task_id)
            
            for successor in self.get_successors(task_id):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)
        
        if len(result) != len(self.nodes):
            raise ValueError("DAG中存在循环依赖")
        
        return result
    
    def validate(self) -> bool:
        try:
            self.topological_sort()
            return True
        except ValueError:
            return False


class DAGScheduler:
    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self.execution_results: Dict[str, ExecutionResult] = {}
        self.running_tasks: Set[str] = set()
        self.task_outputs: Dict[str, Any] = {}
    
    async def execute(self, dag: DAG) -> Dict[str, ExecutionResult]:
        if not dag.validate():
            raise ValueError("DAG验证失败：存在循环依赖")
        
        self.execution_results = {}
        self.task_outputs = {}
        
        execution_order = dag.topological_sort()
        print(f"📋 执行顺序: {execution_order}")
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def run_task(task_id: str):
            async with semaphore:
                return await self._execute_task(dag, task_id)
        
        pending_tasks = set(execution_order)
        
        while pending_tasks:
            ready_tasks = []
            for task_id in pending_tasks:
                node = dag.get_node(task_id)
                if node:
                    deps_completed = all(
                        self.execution_results.get(dep_id, ExecutionResult(dep_id, TaskStatus.PENDING)).status == TaskStatus.COMPLETED
                        for dep_id in node.dependencies
                    )
                    if deps_completed:
                        ready_tasks.append(task_id)
            
            if not ready_tasks:
                await asyncio.sleep(0.1)
                continue
            
            ready_tasks.sort(key=lambda x: -dag.nodes[x].priority)
            
            tasks = [run_task(task_id) for task_id in ready_tasks]
            await asyncio.gather(*tasks)
            
            pending_tasks -= set(ready_tasks)
        
        return self.execution_results
    
    async def _execute_task(self, dag: DAG, task_id: str) -> ExecutionResult:
        node = dag.get_node(task_id)
        if not node:
            result = ExecutionResult(task_id, TaskStatus.FAILED, error="任务节点不存在")
            self.execution_results[task_id] = result
            return result
        
        result = ExecutionResult(task_id, TaskStatus.RUNNING)
        result.start_time = datetime.now().timestamp()
        self.execution_results[task_id] = result
        
        retry_count = 0
        last_error = None
        
        while retry_count <= node.max_retries:
            try:
                print(f"🚀 开始执行任务: {node.name} (优先级: {node.priority})")
                
                if node.dependencies:
                    if len(node.dependencies) == 1:
                        args = (self.task_outputs.get(node.dependencies[0]),)
                        kwargs = {}
                    else:
                        args = ()
                        kwargs = {dep_id: self.task_outputs.get(dep_id) for dep_id in node.dependencies}
                else:
                    args = ()
                    kwargs = {}
                
                if node.is_async:
                    if node.timeout:
                        output = await asyncio.wait_for(
                            node.func(*args, **kwargs),
                            timeout=node.timeout
                        )
                    else:
                        output = await node.func(*args, **kwargs)
                else:
                    if node.timeout:
                        loop = asyncio.get_event_loop()
                        output = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda: node.func(*args, **kwargs)),
                            timeout=node.timeout
                        )
                    else:
                        output = node.func(*args, **kwargs)
                
                self.task_outputs[task_id] = output
                
                result.status = TaskStatus.COMPLETED
                result.output = output
                result.retry_count = retry_count
                result.end_time = datetime.now().timestamp()
                self.execution_results[task_id] = result
                
                print(f"✅ 任务完成: {node.name}")
                return result
            
            except asyncio.TimeoutError:
                last_error = f"任务超时 ({node.timeout}秒)"
                retry_count += 1
                print(f"⏱️ 任务超时: {node.name}, 重试次数: {retry_count}/{node.max_retries}")
            
            except Exception as e:
                last_error = str(e)
                retry_count += 1
                print(f"❌ 任务失败: {node.name}, 错误: {e}, 重试次数: {retry_count}/{node.max_retries}")
        
        result.status = TaskStatus.FAILED
        result.error = last_error
        result.retry_count = retry_count
        result.end_time = datetime.now().timestamp()
        self.execution_results[task_id] = result
        
        print(f"❌ 任务最终失败: {node.name}")
        return result


class DAGBuilder:
    def __init__(self, name: str):
        self.dag = DAG(name)
        self.pending_edges: List[Tuple[str, str]] = []
    
    def add_task(self, task_id: str, name: str, func: Callable[..., Any], 
                 dependencies: List[str] = None, priority: int = 0, 
                 max_retries: int = 3, timeout: Optional[int] = None) -> 'DAGBuilder':
        node = TaskNode(
            task_id=task_id,
            name=name,
            func=func,
            dependencies=[],
            priority=priority,
            max_retries=max_retries,
            timeout=timeout
        )
        self.dag.add_node(node)
        
        if dependencies:
            for dep_id in dependencies:
                if dep_id in self.dag.nodes:
                    self.dag.add_edge(dep_id, task_id)
                else:
                    self.pending_edges.append((dep_id, task_id))
        
        return self
    
    def build(self) -> DAG:
        for from_task_id, to_task_id in self.pending_edges:
            if from_task_id not in self.dag.nodes:
                raise ValueError(f"依赖任务不存在: {from_task_id}")
            self.dag.add_edge(from_task_id, to_task_id)
        
        if not self.dag.validate():
            raise ValueError("DAG构建失败：存在循环依赖")
        return self.dag


async def main():
    print("="*80)
    print("🏭 L5-03: DAG调度器 (DAG Scheduler)")
    print("="*80)
    
    async def fetch_data(source: str = "database"):
        await asyncio.sleep(0.5)
        return {"data": f"从{source}获取的数据"}
    
    async def process_data(data):
        await asyncio.sleep(0.8)
        return {"processed": data.get("data", "") + " - 已处理"}
    
    async def validate_data(processed):
        await asyncio.sleep(0.3)
        return {"valid": True, "checksum": "abc123"}
    
    async def save_results(validated):
        await asyncio.sleep(0.6)
        return {"saved": True, "record_count": 100}
    
    async def notify_agent(processed):
        await asyncio.sleep(0.2)
        return {"notified": True, "agent_id": "agent_001"}
    
    dag = DAGBuilder("数据处理流程") \
        .add_task("fetch", "数据获取", fetch_data, priority=10) \
        .add_task("process", "数据处理", process_data, dependencies=["fetch"], priority=8) \
        .add_task("validate", "数据验证", validate_data, dependencies=["process"], priority=5) \
        .add_task("save", "结果保存", save_results, dependencies=["validate"], priority=3) \
        .add_task("notify", "通知Agent", notify_agent, dependencies=["process"], priority=2) \
        .build()
    
    print(f"\n📊 DAG结构:")
    for node in dag.get_nodes():
        print(f"  - {node.task_id}: {node.name} (依赖: {node.dependencies}, 优先级: {node.priority})")
    
    print("\n" + "-"*60)
    print("执行DAG调度")
    print("-"*60)
    
    scheduler = DAGScheduler(max_concurrent=2)
    results = await scheduler.execute(dag)
    
    print("\n" + "-"*60)
    print("执行结果汇总")
    print("-"*60)
    
    for task_id, result in results.items():
        node = dag.get_node(task_id)
        duration = result.end_time - result.start_time if result.start_time and result.end_time else 0
        status_icon = "✅" if result.status == TaskStatus.COMPLETED else "❌"
        print(f"\n{status_icon} {node.name if node else task_id}:")
        print(f"   状态: {result.status.value}")
        print(f"   耗时: {duration:.2f}秒")
        print(f"   重试: {result.retry_count}次")
        if result.error:
            print(f"   错误: {result.error}")
    
    success_count = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
    total_count = len(results)
    
    print(f"\n📈 执行统计: {success_count}/{total_count} 任务成功完成")
    
    print("\n" + "="*80)
    print("✅ DAG调度演示完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())