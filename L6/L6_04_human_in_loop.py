import asyncio
import time
import uuid
from enum import Enum
from typing import Dict, Optional, Any, List, Callable
from dataclasses import dataclass, field


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    AUTO_APPROVED = "auto_approved"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    params: Dict[str, Any]
    risk_level: RiskLevel
    confidence: float
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    timeout: float = 300.0
    approver: Optional[str] = None
    decision_reason: Optional[str] = None
    decided_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.timeout

    @property
    def wait_time(self) -> float:
        end = self.decided_at or time.time()
        return end - self.created_at


class RiskAssessor:
    """风险评估器：根据动作和参数评估风险等级"""

    def __init__(self):
        self._rules: List[Callable[[str, Dict], Optional[RiskLevel]]] = []
        self._high_risk_actions = {"transfer_money", "delete_data", "send_email", "execute_command"}
        self._amount_threshold = 5000

    def add_rule(self, rule: Callable[[str, Dict], Optional[RiskLevel]]):
        self._rules.append(rule)

    def assess(self, action: str, params: Dict[str, Any], confidence: float) -> RiskLevel:
        for rule in self._rules:
            result = rule(action, params)
            if result:
                return result

        if action == "transfer_money":
            amount = params.get("amount", 0)
            if amount >= 50000:
                return RiskLevel.CRITICAL
            if amount >= self._amount_threshold:
                return RiskLevel.HIGH

        if action in self._high_risk_actions:
            return RiskLevel.HIGH

        if confidence < 0.6:
            return RiskLevel.HIGH
        if confidence < 0.8:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW


class ApprovalQueue:
    """审批队列：管理待审批请求"""

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._events: Dict[str, asyncio.Event] = {}

    def submit(self, request: ApprovalRequest) -> asyncio.Event:
        self._requests[request.request_id] = request
        event = asyncio.Event()
        self._events[request.request_id] = event
        return event

    def decide(self, request_id: str, approved: bool, approver: str, reason: str = ""):
        request = self._requests.get(request_id)
        if not request or request.status != ApprovalStatus.PENDING:
            return False

        request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        request.approver = approver
        request.decision_reason = reason
        request.decided_at = time.time()

        event = self._events.get(request_id)
        if event:
            event.set()
        return True

    def get_pending(self) -> List[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)


class HumanInLoopManager:
    """人工介入管理器：整合风险评估与审批流程"""

    def __init__(self, mode: str = "block"):
        self.mode = mode
        self.assessor = RiskAssessor()
        self.queue = ApprovalQueue()
        self._auto_approve_low = True

    async def execute_with_approval(
        self,
        action: str,
        params: Dict[str, Any],
        confidence: float = 1.0,
        executor: Optional[Callable] = None,
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        risk_level = self.assessor.assess(action, params, confidence)

        if risk_level == RiskLevel.LOW and self._auto_approve_low:
            result = await self._execute(executor, params)
            return {
                "status": ApprovalStatus.AUTO_APPROVED.value,
                "risk_level": risk_level.value,
                "result": result
            }

        request = ApprovalRequest(
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            action=action,
            params=params,
            risk_level=risk_level,
            confidence=confidence,
            reason=self._build_reason(action, params, risk_level, confidence),
            timeout=timeout
        )

        event = self.queue.submit(request)
        print(f"⏸️  需要人工审批: [{request.request_id}] {action} (风险: {risk_level.value})")
        print(f"   原因: {request.reason}")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            request.status = ApprovalStatus.TIMEOUT
            return {
                "status": ApprovalStatus.TIMEOUT.value,
                "risk_level": risk_level.value,
                "request_id": request.request_id,
                "result": None
            }

        if request.status == ApprovalStatus.APPROVED:
            result = await self._execute(executor, params)
            return {
                "status": ApprovalStatus.APPROVED.value,
                "risk_level": risk_level.value,
                "request_id": request.request_id,
                "approver": request.approver,
                "wait_time": request.wait_time,
                "result": result
            }
        else:
            return {
                "status": ApprovalStatus.REJECTED.value,
                "risk_level": risk_level.value,
                "request_id": request.request_id,
                "approver": request.approver,
                "decision_reason": request.decision_reason,
                "result": None
            }

    async def _execute(self, executor: Optional[Callable], params: Dict[str, Any]) -> Any:
        if executor is None:
            return f"已执行: {params}"
        if asyncio.iscoroutinefunction(executor):
            return await executor(**params)
        return executor(**params)

    def _build_reason(self, action: str, params: Dict, risk_level: RiskLevel, confidence: float) -> str:
        reasons = []
        if action == "transfer_money":
            reasons.append(f"转账金额 {params.get('amount', 0)} 元")
        if confidence < 0.8:
            reasons.append(f"置信度较低 ({confidence:.2f})")
        if action in self.assessor._high_risk_actions:
            reasons.append(f"高风险操作 ({action})")
        return "；".join(reasons) if reasons else f"风险等级: {risk_level.value}"


async def simulate_approver(manager: HumanInLoopManager, delay: float = 1.0):
    """模拟人工审批员：自动处理待审批请求"""
    await asyncio.sleep(delay)
    pending = manager.queue.get_pending()
    for request in pending:
        if request.risk_level == RiskLevel.CRITICAL:
            manager.queue.decide(request.request_id, False, "risk_manager", "金额过大，拒绝")
            print(f"❌ [risk_manager] 拒绝: {request.request_id} (金额过大)")
        else:
            manager.queue.decide(request.request_id, True, "ops_admin", "审核通过")
            print(f"✅ [ops_admin] 批准: {request.request_id}")


async def test_auto_approve():
    print("\n" + "-" * 60)
    print("✅ 低风险自动批准测试")
    print("-" * 60)

    manager = HumanInLoopManager()

    result = await manager.execute_with_approval(
        action="query_data",
        params={"table": "users"},
        confidence=0.95
    )
    print(f"动作: query_data")
    print(f"结果: {result['status']} (风险: {result['risk_level']})")


async def test_high_risk_approval():
    print("\n" + "-" * 60)
    print("⏸️  高风险人工审批测试")
    print("-" * 60)

    manager = HumanInLoopManager()

    approver_task = asyncio.create_task(simulate_approver(manager, delay=1.0))

    result = await manager.execute_with_approval(
        action="transfer_money",
        params={"amount": 10000, "to": "account_456"},
        confidence=0.9,
        timeout=10.0
    )

    await approver_task

    print(f"\n最终结果: {result['status']}")
    print(f"审批人: {result.get('approver')}")
    print(f"等待时间: {result.get('wait_time', 0):.2f}s")


async def test_critical_reject():
    print("\n" + "-" * 60)
    print("❌ 极高风险拒绝测试")
    print("-" * 60)

    manager = HumanInLoopManager()

    approver_task = asyncio.create_task(simulate_approver(manager, delay=1.0))

    result = await manager.execute_with_approval(
        action="transfer_money",
        params={"amount": 100000, "to": "unknown_account"},
        confidence=0.9,
        timeout=10.0
    )

    await approver_task

    print(f"\n最终结果: {result['status']}")
    print(f"拒绝原因: {result.get('decision_reason')}")


async def test_timeout():
    print("\n" + "-" * 60)
    print("⏱️  审批超时测试")
    print("-" * 60)

    manager = HumanInLoopManager()

    result = await manager.execute_with_approval(
        action="delete_data",
        params={"table": "important_data"},
        confidence=0.9,
        timeout=2.0
    )

    print(f"\n最终结果: {result['status']} (超时未审批，默认拒绝)")


async def test_low_confidence():
    print("\n" + "-" * 60)
    print("🤔 低置信度介入测试")
    print("-" * 60)

    manager = HumanInLoopManager()

    approver_task = asyncio.create_task(simulate_approver(manager, delay=1.0))

    result = await manager.execute_with_approval(
        action="generate_report",
        params={"type": "financial"},
        confidence=0.5,
        timeout=10.0
    )

    await approver_task

    print(f"\n最终结果: {result['status']} (置信度低触发审批)")


async def main():
    print("=" * 80)
    print("👤 L6-04: Human-in-the-Loop（人工介入）")
    print("=" * 80)

    await test_auto_approve()
    await test_high_risk_approval()
    await test_critical_reject()
    await test_timeout()
    await test_low_confidence()

    print("\n" + "=" * 80)
    print("✅ Human-in-the-Loop 演示完成")
    print("=" * 80)

    print("""
💡 核心功能:
   - 风险评估器: 根据动作、金额、置信度评估风险等级
   - 审批队列: 管理待审批请求和决策
   - 四种审批状态: 自动批准、批准、拒绝、超时
   - 四级风险等级: LOW、MEDIUM、HIGH、CRITICAL
   - 阻塞式介入: Agent 暂停等待人工决策
   - 超时保护: 超时后默认拒绝，确保安全
""")


if __name__ == "__main__":
    asyncio.run(main())