"""
L6-04 扩展示例：检查点式人工介入（Checkpoint-based Human-in-the-Loop）

结合 L5-02 的 Checkpoint 机制与 L6-04 的审批机制，演示真实流程审批场景：
  阶段1: 流程执行到审批点 → 保存检查点（状态落盘）→ 进程可以退出
  (人工审批，可能几小时/几天后)
  阶段2: 审批通过 → 任意进程加载检查点 → 从断点恢复执行

相比阻塞式（asyncio.wait_for 挂起进程），检查点式具备：
  - 状态持久化，进程可释放资源
  - 服务崩溃/重启后可恢复
  - 支持超长时间审批流程
  - 可横向扩展（任意实例恢复执行）
"""
import asyncio
import os
import sys
import uuid
import time
from enum import Enum
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "L5"))
from L5_02_checkpoint import CheckpointManager, FileSystemStorage  # noqa: E402

from L6_04_human_in_loop import RiskAssessor, RiskLevel, ApprovalStatus  # noqa: E402


CHECKPOINT_DIR = os.path.join(os.path.dirname(__file__), "_hitl_checkpoints")


class WorkflowStatus(Enum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED_RESUMED = "approved_resumed"
    REJECTED = "rejected"
    COMPLETED = "completed"


class ApprovalStore:
    """模拟持久化的审批记录存储（实际中可用数据库）"""

    def __init__(self, base_path: str):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _path(self, request_id: str) -> str:
        return os.path.join(self.base_path, f"approval_{request_id}.json")

    def create(self, request_id: str, checkpoint_id: str, action: str, params: Dict[str, Any], risk: str):
        import json
        data = {
            "request_id": request_id,
            "checkpoint_id": checkpoint_id,
            "action": action,
            "params": params,
            "risk_level": risk,
            "status": ApprovalStatus.PENDING.value,
            "approver": None,
            "decision_reason": None,
            "created_at": time.time(),
        }
        with open(self._path(request_id), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def decide(self, request_id: str, approved: bool, approver: str, reason: str = ""):
        import json
        path = self._path(request_id)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = ApprovalStatus.APPROVED.value if approved else ApprovalStatus.REJECTED.value
        data["approver"] = approver
        data["decision_reason"] = reason
        data["decided_at"] = time.time()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, request_id: str) -> Optional[Dict[str, Any]]:
        import json
        path = self._path(request_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


class CheckpointApprovalWorkflow:
    """检查点式审批工作流：报销审批流程"""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.checkpoint_mgr = CheckpointManager(FileSystemStorage(CHECKPOINT_DIR))
        self.approval_store = ApprovalStore(CHECKPOINT_DIR)
        self.assessor = RiskAssessor()
        self.assessor.add_rule(self._expense_risk_rule)

    @staticmethod
    def _expense_risk_rule(action: str, params: Dict[str, Any]) -> Optional[RiskLevel]:
        """报销金额风险规则：仅按金额判定"""
        if action != "expense_payment":
            return None
        amount = params.get("amount", 0)
        if amount >= 50000:
            return RiskLevel.CRITICAL
        if amount >= 5000:
            return RiskLevel.HIGH
        return RiskLevel.LOW

    async def phase1_run_until_approval(self, expense: Dict[str, Any]) -> Dict[str, Any]:
        """阶段1：执行流程，遇到审批点则保存检查点并退出"""
        print(f"\n📋 [阶段1] 开始处理报销流程 (workflow={self.workflow_id})")

        # 步骤1: 校验
        print("   ✓ 步骤1: 报销单校验通过")
        # 步骤2: 计算金额
        amount = expense["amount"]
        print(f"   ✓ 步骤2: 报销金额合计 {amount} 元")

        # 步骤3: 风险评估，判断是否需要审批
        risk = self.assessor.assess("expense_payment", {"amount": amount}, confidence=0.9)
        print(f"   ✓ 步骤3: 风险评估 = {risk.value}")

        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            # 保存检查点：记录当前流程状态和上下文
            request_id = f"req_{uuid.uuid4().hex[:8]}"
            workflow_state = {
                "workflow_id": self.workflow_id,
                "status": WorkflowStatus.WAITING_APPROVAL.value,
                "expense": expense,
                "amount": amount,
                "risk_level": risk.value,
                "request_id": request_id,
                "completed_steps": ["校验", "金额计算", "风险评估"],
                "next_step": "财务打款",
            }

            checkpoint = await self.checkpoint_mgr.save_checkpoint(
                agent_id=self.workflow_id,
                state_name=WorkflowStatus.WAITING_APPROVAL.value,
                context=workflow_state,
                metadata={"request_id": request_id, "amount": amount}
            )

            # 创建审批记录（关联检查点）
            self.approval_store.create(
                request_id=request_id,
                checkpoint_id=checkpoint.checkpoint_id,
                action="expense_payment",
                params=expense,
                risk=risk.value
            )

            print(f"\n   ⏸️  金额较大需人工审批，已保存检查点")
            print(f"      检查点ID: {checkpoint.checkpoint_id[:8]}")
            print(f"      审批单号: {request_id}")
            print(f"   💤 阶段1进程可以退出，等待审批...")

            return {
                "status": WorkflowStatus.WAITING_APPROVAL.value,
                "request_id": request_id,
                "checkpoint_id": checkpoint.checkpoint_id
            }
        else:
            # 低风险直接完成
            print("   ✓ 步骤4: 低风险，自动打款完成")
            return {"status": WorkflowStatus.COMPLETED.value}

    async def phase2_resume_after_approval(self, request_id: str) -> Dict[str, Any]:
        """阶段2：审批完成后，从检查点恢复并继续执行"""
        print(f"\n📋 [阶段2] 审批完成，尝试恢复流程 (request={request_id})")

        # 读取审批结果
        approval = self.approval_store.get(request_id)
        if not approval:
            print("   ❌ 找不到审批记录")
            return {"status": "error"}

        if approval["status"] == ApprovalStatus.PENDING.value:
            print("   ⏳ 审批尚未完成，无法恢复")
            return {"status": WorkflowStatus.WAITING_APPROVAL.value}

        # 从检查点恢复工作流状态（模拟新进程：重新创建 manager 加载）
        checkpoint = await self.checkpoint_mgr.load_checkpoint(approval["checkpoint_id"])
        if not checkpoint:
            print("   ❌ 检查点加载失败")
            return {"status": "error"}

        if not checkpoint.verify_checksum():
            print("   ❌ 检查点校验失败")
            return {"status": "error"}

        state = checkpoint.context
        print(f"   ✓ 从检查点恢复状态成功 (检查点ID: {checkpoint.checkpoint_id[:8]})")
        print(f"      已完成步骤: {state['completed_steps']}")
        print(f"      待执行步骤: {state['next_step']}")

        if approval["status"] == ApprovalStatus.REJECTED.value:
            print(f"   ❌ 审批被拒绝 (审批人: {approval['approver']}, 原因: {approval['decision_reason']})")
            return {"status": WorkflowStatus.REJECTED.value}

        # 审批通过，继续执行后续步骤
        print(f"   ✅ 审批通过 (审批人: {approval['approver']})")
        print(f"   ✓ 步骤4: 财务打款 {state['amount']} 元，流程完成")

        return {
            "status": WorkflowStatus.COMPLETED.value,
            "amount": state["amount"],
            "approver": approval["approver"]
        }


async def simulate_human_approval(workflow: CheckpointApprovalWorkflow, request_id: str, approved: bool):
    """模拟人工审批（可能发生在另一个进程/几天后）"""
    approver = "finance_manager" if approved else "finance_manager"
    reason = "费用合理，同意报销" if approved else "缺少发票，驳回"
    workflow.approval_store.decide(request_id, approved, approver, reason)
    status = "批准" if approved else "拒绝"
    print(f"\n👤 [人工审批] {approver} {status}了审批单 {request_id}")


async def demo_approved_flow():
    print("\n" + "=" * 80)
    print("场景一：大额报销 → 审批通过 → 检查点恢复完成")
    print("=" * 80)

    workflow = CheckpointApprovalWorkflow(f"expense_{uuid.uuid4().hex[:6]}")

    # 阶段1：执行到审批点，保存检查点
    result1 = await workflow.phase1_run_until_approval({"amount": 30000, "type": "差旅费"})

    # 模拟进程退出后，人工审批
    await asyncio.sleep(0.5)
    await simulate_human_approval(workflow, result1["request_id"], approved=True)

    # 阶段2：新进程加载检查点并恢复
    await asyncio.sleep(0.5)
    workflow_resumed = CheckpointApprovalWorkflow(workflow.workflow_id)
    result2 = await workflow_resumed.phase2_resume_after_approval(result1["request_id"])

    print(f"\n🎯 最终结果: {result2['status']}")


async def demo_rejected_flow():
    print("\n" + "=" * 80)
    print("场景二：大额报销 → 审批拒绝 → 检查点恢复终止")
    print("=" * 80)

    workflow = CheckpointApprovalWorkflow(f"expense_{uuid.uuid4().hex[:6]}")

    result1 = await workflow.phase1_run_until_approval({"amount": 80000, "type": "设备采购"})

    await asyncio.sleep(0.5)
    await simulate_human_approval(workflow, result1["request_id"], approved=False)

    await asyncio.sleep(0.5)
    workflow_resumed = CheckpointApprovalWorkflow(workflow.workflow_id)
    result2 = await workflow_resumed.phase2_resume_after_approval(result1["request_id"])

    print(f"\n🎯 最终结果: {result2['status']}")


async def demo_low_risk_flow():
    print("\n" + "=" * 80)
    print("场景三：小额报销 → 低风险 → 自动完成（无需审批）")
    print("=" * 80)

    workflow = CheckpointApprovalWorkflow(f"expense_{uuid.uuid4().hex[:6]}")
    result = await workflow.phase1_run_until_approval({"amount": 200, "type": "办公用品"})

    print(f"\n🎯 最终结果: {result['status']}")


def cleanup():
    """清理演示产生的检查点文件"""
    import shutil
    if os.path.exists(CHECKPOINT_DIR):
        shutil.rmtree(CHECKPOINT_DIR)


async def main():
    print("=" * 80)
    print("🔐 L6-04 扩展: 检查点式人工介入 (Checkpoint-based HITL)")
    print("=" * 80)

    await demo_approved_flow()
    await demo_rejected_flow()
    await demo_low_risk_flow()

    print("\n" + "=" * 80)
    print("✅ 检查点式人工介入演示完成")
    print("=" * 80)
    print("""
💡 核心优势（对比阻塞式）:
   - 状态持久化: 检查点落盘，审批期间进程可退出释放资源
   - 崩溃可恢复: 服务重启后从检查点继续，不丢失流程状态
   - 支持长流程: 审批等多久都不影响（无超时挂起进程）
   - 可横向扩展: 阶段2可由任意进程实例加载检查点恢复执行
   - 可审计追溯: 检查点 + 审批记录形成完整审计链
""")

    cleanup()


if __name__ == "__main__":
    asyncio.run(main())