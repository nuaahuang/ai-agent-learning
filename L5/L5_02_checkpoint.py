from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
import json
import hashlib
import os
import uuid
from datetime import datetime
import asyncio


@dataclass
class Checkpoint:
    checkpoint_id: str
    agent_id: str
    timestamp: float
    state_name: str
    context: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    checksum: Optional[str] = None
    version: int = 1
    
    def __post_init__(self):
        if self.checksum is None:
            self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        data = json.dumps({
            'agent_id': self.agent_id,
            'timestamp': self.timestamp,
            'state_name': self.state_name,
            'context': self.context,
            'metadata': self.metadata,
            'version': self.version
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
    
    def verify_checksum(self) -> bool:
        expected = self._calculate_checksum()
        return self.checksum == expected
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'checkpoint_id': self.checkpoint_id,
            'agent_id': self.agent_id,
            'timestamp': self.timestamp,
            'state_name': self.state_name,
            'context': self.context,
            'metadata': self.metadata,
            'checksum': self.checksum,
            'version': self.version
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Checkpoint':
        return cls(
            checkpoint_id=data['checkpoint_id'],
            agent_id=data['agent_id'],
            timestamp=data['timestamp'],
            state_name=data['state_name'],
            context=data['context'],
            metadata=data.get('metadata', {}),
            checksum=data.get('checksum'),
            version=data.get('version', 1)
        )
    
    def __repr__(self) -> str:
        return f"Checkpoint(id={self.checkpoint_id[:8]}, agent={self.agent_id}, state={self.state_name}, time={datetime.fromtimestamp(self.timestamp)})"


class CheckpointStorage(ABC):
    @abstractmethod
    async def save(self, checkpoint: Checkpoint) -> bool:
        pass
    
    @abstractmethod
    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        pass
    
    @abstractmethod
    async def load_latest(self, agent_id: str) -> Optional[Checkpoint]:
        pass
    
    @abstractmethod
    async def list_checkpoints(self, agent_id: str) -> List[Checkpoint]:
        pass
    
    @abstractmethod
    async def delete(self, checkpoint_id: str) -> bool:
        pass
    
    @abstractmethod
    async def cleanup(self, agent_id: str, keep_count: int = 5) -> int:
        pass


class FileSystemStorage(CheckpointStorage):
    def __init__(self, base_path: str = "./checkpoints"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
    
    async def save(self, checkpoint: Checkpoint) -> bool:
        try:
            agent_dir = os.path.join(self.base_path, checkpoint.agent_id)
            os.makedirs(agent_dir, exist_ok=True)
            
            file_path = os.path.join(agent_dir, f"{checkpoint.checkpoint_id}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"保存Checkpoint失败: {e}")
            return False
    
    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        try:
            for agent_dir in os.listdir(self.base_path):
                agent_path = os.path.join(self.base_path, agent_dir)
                if os.path.isdir(agent_path):
                    file_path = os.path.join(agent_path, f"{checkpoint_id}.json")
                    if os.path.exists(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            checkpoint = Checkpoint.from_dict(data)
                            if checkpoint.verify_checksum():
                                return checkpoint
                            else:
                                print(f"Checkpoint校验失败: {checkpoint_id}")
            return None
        except Exception as e:
            print(f"加载Checkpoint失败: {e}")
            return None
    
    async def load_latest(self, agent_id: str) -> Optional[Checkpoint]:
        try:
            agent_dir = os.path.join(self.base_path, agent_id)
            if not os.path.exists(agent_dir):
                return None
            
            files = [f for f in os.listdir(agent_dir) if f.endswith('.json')]
            if not files:
                return None
            
            latest_file = max(files, key=lambda x: os.path.getmtime(os.path.join(agent_dir, x)))
            file_path = os.path.join(agent_dir, latest_file)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                checkpoint = Checkpoint.from_dict(data)
                if checkpoint.verify_checksum():
                    return checkpoint
            return None
        except Exception as e:
            print(f"加载最新Checkpoint失败: {e}")
            return None
    
    async def list_checkpoints(self, agent_id: str) -> List[Checkpoint]:
        try:
            agent_dir = os.path.join(self.base_path, agent_id)
            if not os.path.exists(agent_dir):
                return []
            
            checkpoints = []
            for filename in os.listdir(agent_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(agent_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        checkpoint = Checkpoint.from_dict(data)
                        if checkpoint.verify_checksum():
                            checkpoints.append(checkpoint)
            
            checkpoints.sort(key=lambda x: x.timestamp)
            return checkpoints
        except Exception as e:
            print(f"列出Checkpoint失败: {e}")
            return []
    
    async def delete(self, checkpoint_id: str) -> bool:
        try:
            for agent_dir in os.listdir(self.base_path):
                agent_path = os.path.join(self.base_path, agent_dir)
                if os.path.isdir(agent_path):
                    file_path = os.path.join(agent_path, f"{checkpoint_id}.json")
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        return True
            return False
        except Exception as e:
            print(f"删除Checkpoint失败: {e}")
            return False
    
    async def cleanup(self, agent_id: str, keep_count: int = 5) -> int:
        try:
            checkpoints = await self.list_checkpoints(agent_id)
            if len(checkpoints) <= keep_count:
                return 0
            
            to_delete = checkpoints[:-keep_count]
            deleted_count = 0
            
            for cp in to_delete:
                if await self.delete(cp.checkpoint_id):
                    deleted_count += 1
            
            return deleted_count
        except Exception as e:
            print(f"清理Checkpoint失败: {e}")
            return 0


class InMemoryStorage(CheckpointStorage):
    def __init__(self):
        self.checkpoints: Dict[str, Checkpoint] = {}
        self.agent_checkpoints: Dict[str, List[str]] = {}
    
    async def save(self, checkpoint: Checkpoint) -> bool:
        try:
            self.checkpoints[checkpoint.checkpoint_id] = checkpoint
            
            if checkpoint.agent_id not in self.agent_checkpoints:
                self.agent_checkpoints[checkpoint.agent_id] = []
            self.agent_checkpoints[checkpoint.agent_id].append(checkpoint.checkpoint_id)
            
            return True
        except Exception as e:
            print(f"保存Checkpoint失败: {e}")
            return False
    
    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        checkpoint = self.checkpoints.get(checkpoint_id)
        if checkpoint and checkpoint.verify_checksum():
            return checkpoint
        return None
    
    async def load_latest(self, agent_id: str) -> Optional[Checkpoint]:
        checkpoint_ids = self.agent_checkpoints.get(agent_id, [])
        if not checkpoint_ids:
            return None
        
        latest_id = max(checkpoint_ids, key=lambda x: self.checkpoints[x].timestamp)
        return self.checkpoints.get(latest_id)
    
    async def list_checkpoints(self, agent_id: str) -> List[Checkpoint]:
        checkpoint_ids = self.agent_checkpoints.get(agent_id, [])
        checkpoints = []
        for cp_id in checkpoint_ids:
            cp = self.checkpoints.get(cp_id)
            if cp and cp.verify_checksum():
                checkpoints.append(cp)
        checkpoints.sort(key=lambda x: x.timestamp)
        return checkpoints
    
    async def delete(self, checkpoint_id: str) -> bool:
        if checkpoint_id in self.checkpoints:
            cp = self.checkpoints[checkpoint_id]
            if cp.agent_id in self.agent_checkpoints:
                self.agent_checkpoints[cp.agent_id].remove(checkpoint_id)
            del self.checkpoints[checkpoint_id]
            return True
        return False
    
    async def cleanup(self, agent_id: str, keep_count: int = 5) -> int:
        checkpoints = await self.list_checkpoints(agent_id)
        if len(checkpoints) <= keep_count:
            return 0
        
        to_delete = checkpoints[:-keep_count]
        deleted_count = 0
        
        for cp in to_delete:
            if await self.delete(cp.checkpoint_id):
                deleted_count += 1
        
        return deleted_count


class CheckpointManager:
    def __init__(self, storage: CheckpointStorage = None):
        self.storage = storage or FileSystemStorage()
        self.save_triggers: List[Callable[['CheckpointManager', 'Checkpoint'], Any]] = []
    
    def add_save_trigger(self, trigger: Callable[['CheckpointManager', 'Checkpoint'], Any]):
        self.save_triggers.append(trigger)
    
    async def save_checkpoint(self, agent_id: str, state_name: str, 
                             context: Dict[str, Any], metadata: Dict[str, Any] = None) -> Optional[Checkpoint]:
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            agent_id=agent_id,
            timestamp=datetime.now().timestamp(),
            state_name=state_name,
            context=context,
            metadata=metadata or {}
        )
        
        success = await self.storage.save(checkpoint)
        if success:
            for trigger in self.save_triggers:
                result = trigger(self, checkpoint)
                if asyncio.iscoroutine(result):
                    await result
            return checkpoint
        return None
    
    async def load_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        return await self.storage.load(checkpoint_id)
    
    async def load_latest_checkpoint(self, agent_id: str) -> Optional[Checkpoint]:
        return await self.storage.load_latest(agent_id)
    
    async def list_agent_checkpoints(self, agent_id: str) -> List[Checkpoint]:
        return await self.storage.list_checkpoints(agent_id)
    
    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        return await self.storage.delete(checkpoint_id)
    
    async def cleanup_old_checkpoints(self, agent_id: str, keep_count: int = 5) -> int:
        return await self.storage.cleanup(agent_id, keep_count)


class CheckpointAgentMixin:
    def __init__(self):
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.auto_checkpoint_enabled = True
    
    def set_checkpoint_manager(self, manager: CheckpointManager):
        self.checkpoint_manager = manager
    
    async def save_checkpoint(self, metadata: Dict[str, Any] = None) -> Optional[Checkpoint]:
        if not self.checkpoint_manager:
            return None
        
        return await self.checkpoint_manager.save_checkpoint(
            agent_id=self.agent_id,
            state_name=self.get_state_name(),
            context=self.get_context(),
            metadata=metadata
        )
    
    async def load_from_checkpoint(self, checkpoint_id: str = None) -> bool:
        if not self.checkpoint_manager:
            return False
        
        if checkpoint_id:
            checkpoint = await self.checkpoint_manager.load_checkpoint(checkpoint_id)
        else:
            checkpoint = await self.checkpoint_manager.load_latest_checkpoint(self.agent_id)
        
        if checkpoint:
            self.context.update(checkpoint.context)
            return True
        return False


async def main():
    print("="*80)
    print("🏭 L5-02: Checkpoint（断点续传机制）")
    print("="*80)
    
    checkpoint_manager = CheckpointManager(FileSystemStorage())
    
    async def on_save(manager: CheckpointManager, checkpoint: Checkpoint):
        print(f"📸 Checkpoint已保存: {checkpoint}")
    
    checkpoint_manager.add_save_trigger(on_save)
    
    agent_id = "test_agent_001"
    
    print("\n" + "-"*60)
    print("步骤1: 创建多个Checkpoint")
    print("-"*60)
    
    await checkpoint_manager.save_checkpoint(
        agent_id=agent_id,
        state_name="running",
        context={"progress": 25, "task": "数据处理"},
        metadata={"version": "1.0"}
    )
    
    await asyncio.sleep(0.1)
    
    await checkpoint_manager.save_checkpoint(
        agent_id=agent_id,
        state_name="running",
        context={"progress": 50, "task": "数据处理"},
        metadata={"version": "1.0"}
    )
    
    await asyncio.sleep(0.1)
    
    await checkpoint_manager.save_checkpoint(
        agent_id=agent_id,
        state_name="completed",
        context={"progress": 100, "task": "数据处理", "result": "成功"},
        metadata={"version": "1.0"}
    )
    
    print("\n" + "-"*60)
    print("步骤2: 列出所有Checkpoint")
    print("-"*60)
    
    checkpoints = await checkpoint_manager.list_agent_checkpoints(agent_id)
    for i, cp in enumerate(checkpoints, 1):
        print(f"\n{i}. {cp}")
        print(f"   进度: {cp.context.get('progress', 0)}%")
        print(f"   版本: {cp.version}")
    
    print("\n" + "-"*60)
    print("步骤3: 加载最新Checkpoint")
    print("-"*60)
    
    latest = await checkpoint_manager.load_latest_checkpoint(agent_id)
    if latest:
        print(f"最新Checkpoint: {latest}")
        print(f"状态名称: {latest.state_name}")
        print(f"上下文: {latest.context}")
    
    print("\n" + "-"*60)
    print("步骤4: 验证Checkpoint完整性")
    print("-"*60)
    
    if latest and latest.verify_checksum():
        print("✅ Checkpoint校验通过")
    else:
        print("❌ Checkpoint校验失败")
    
    print("\n" + "-"*60)
    print("步骤5: 模拟故障恢复")
    print("-"*60)
    
    print("假设系统崩溃，从Checkpoint恢复...")
    recovered_context = latest.context if latest else {}
    print(f"恢复的进度: {recovered_context.get('progress', 0)}%")
    print(f"恢复的任务: {recovered_context.get('task', '未知')}")
    
    print("\n" + "-"*60)
    print("步骤6: 清理旧Checkpoint")
    print("-"*60)
    
    deleted = await checkpoint_manager.cleanup_old_checkpoints(agent_id, keep_count=2)
    print(f"已清理 {deleted} 个旧Checkpoint")
    
    remaining = await checkpoint_manager.list_agent_checkpoints(agent_id)
    print(f"剩余 {len(remaining)} 个Checkpoint")
    
    print("\n" + "="*80)
    print("✅ Checkpoint机制演示完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())