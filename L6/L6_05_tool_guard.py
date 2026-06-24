"""
L6-05 扩展示例：工具调用行为护栏（Tool-Calling Behavior Guardrails）

演示 Agent 调用工具时的 5 道安全防线，串联 L6-04 人工审批：
  防线①: 工具白名单 + 读写分级（默认拒绝，权限最小化）
  防线②: 参数 Schema 校验（类型、范围、格式）
  防线③: 参数安全检测（SQL注入、命令注入、路径穿越、SSRF）
  防线④: 高危工具人工审批（结合 L6-04）
  防线⑤: 执行层防御（参数化查询、参数列表、路径边界）

核心理念：最可靠的不是"检测攻击"，而是"从架构上让攻击无效"。
"""
import asyncio
import os
import re
import sys
import socket
import shlex
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
from L6_04_human_in_loop import HumanInLoopManager, RiskLevel  # noqa: E402


# ============================================================
# 防线①: 工具权限分级与白名单
# ============================================================
class ToolPermission(Enum):
    READ = "read"        # 只读：查询、搜索（低风险，可自动）
    WRITE = "write"      # 写入：创建、更新（中风险，需审批）
    DELETE = "delete"    # 删除：删数据（高风险，需审批）
    EXECUTE = "execute"  # 执行：命令、代码（极高风险，强管控）


@dataclass
class ToolSpec:
    name: str
    permission: ToolPermission
    auto_execute: bool
    schema: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    executor: Optional[Callable] = None


class ToolPermissionError(Exception):
    pass


class ParamValidationError(Exception):
    pass


class SecurityViolationError(Exception):
    pass


# ============================================================
# 防线②: 轻量参数 Schema 校验（标准库实现）
# ============================================================
class ParamValidator:
    @staticmethod
    def validate(tool_name: str, schema: Dict[str, Dict[str, Any]], params: Dict[str, Any]) -> Dict[str, Any]:
        validated = {}
        for field_name, rule in schema.items():
            required = rule.get("required", False)
            if field_name not in params:
                if required:
                    raise ParamValidationError(f"[{tool_name}] 缺少必填参数: {field_name}")
                if "default" in rule:
                    validated[field_name] = rule["default"]
                continue

            value = params[field_name]
            expected_type = rule.get("type")
            if expected_type:
                # float 类型兼容 int（JSON数字常为int），但排除 bool
                if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
                    value = float(value)
                elif not isinstance(value, expected_type) or isinstance(value, bool) and expected_type is not bool:
                    raise ParamValidationError(
                        f"[{tool_name}] 参数 {field_name} 类型错误: 期望 {expected_type.__name__}, 实际 {type(value).__name__}")

            if isinstance(value, (int, float)):
                if "gt" in rule and not value > rule["gt"]:
                    raise ParamValidationError(f"[{tool_name}] {field_name}={value} 必须 > {rule['gt']}")
                if "le" in rule and not value <= rule["le"]:
                    raise ParamValidationError(f"[{tool_name}] {field_name}={value} 必须 <= {rule['le']}")

            if isinstance(value, str):
                if "pattern" in rule and not re.match(rule["pattern"], value):
                    raise ParamValidationError(f"[{tool_name}] {field_name} 格式非法")
                if "enum" in rule and value not in rule["enum"]:
                    raise ParamValidationError(f"[{tool_name}] {field_name}={value} 不在允许范围 {rule['enum']}")

            validated[field_name] = value
        return validated


# ============================================================
# 防线③: 参数安全检测（注入防护）
# ============================================================
class SecurityChecker:
    SQL_INJECTION_PATTERNS = [
        r"('|\")\s*(or|and)\s*('|\"|\d)",
        r";\s*(drop|delete|update|insert|truncate|alter)\s",
        r"--",
        r"/\*.*\*/",
        r"\bunion\s+select\b",
        r"\bdrop\s+table\b",
    ]

    COMMAND_INJECTION_CHARS = [";", "|", "&", "$", "`", ">", "<", "\n", "&&", "||"]

    @classmethod
    def check_sql(cls, value: str) -> Optional[str]:
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return f"疑似SQL注入: 命中模式 {pattern}"
        return None

    @classmethod
    def check_command(cls, value: str) -> Optional[str]:
        for ch in cls.COMMAND_INJECTION_CHARS:
            if ch in value:
                return f"疑似命令注入: 含危险字符 '{ch}'"
        return None

    @classmethod
    def check_path_traversal(cls, value: str, base_dir: str) -> Optional[str]:
        full_path = os.path.realpath(os.path.join(base_dir, value))
        if not full_path.startswith(os.path.realpath(base_dir)):
            return f"疑似路径穿越: {value} 越出 {base_dir}"
        return None

    @classmethod
    def check_ssrf(cls, url: str) -> Optional[str]:
        try:
            host = urlparse(url).hostname
            if not host:
                return "非法URL"
            ip = socket.gethostbyname(host) if not cls._is_ip(host) else host
            if cls._is_private_ip(ip):
                return f"疑似SSRF: 禁止访问内网地址 {ip}"
        except Exception:
            return "URL解析失败"
        return None

    @staticmethod
    def _is_ip(s: str) -> bool:
        return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", s))

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        if ip.startswith(("10.", "127.", "192.168.", "169.254.", "0.")):
            return True
        if ip.startswith("172."):
            second = int(ip.split(".")[1])
            return 16 <= second <= 31
        return False


# ============================================================
# 实际工具执行层（防线⑤: 安全的执行实现）
# ============================================================
class SafeTools:
    ALLOWED_TABLES = {"products", "orders"}
    ALLOWED_COLUMNS = {"id", "name", "price", "status"}
    BASE_DIR = os.path.join(os.path.dirname(__file__), "_tool_sandbox")

    @classmethod
    async def query_database(cls, table: str, column: str, value: str) -> Dict[str, Any]:
        # 表名/字段名走白名单，值走"参数化"（此处模拟）
        if table not in cls.ALLOWED_TABLES:
            raise SecurityViolationError(f"不允许查询表: {table}")
        if column not in cls.ALLOWED_COLUMNS:
            raise SecurityViolationError(f"不允许查询字段: {column}")
        # 模拟参数化查询: cursor.execute("... WHERE %s = %s", (column, value))
        return {"sql": f"SELECT * FROM {table} WHERE {column} = ?", "params": [value], "rows": 3}

    @classmethod
    async def search_docs(cls, keyword: str) -> Dict[str, Any]:
        return {"keyword": keyword, "results": [f"文档{i}" for i in range(1, 4)]}

    @classmethod
    async def create_order(cls, product_id: str, amount: float) -> Dict[str, Any]:
        return {"order_id": "ord_20260624", "product_id": product_id, "amount": amount, "status": "created"}

    @classmethod
    async def delete_user(cls, user_id: str) -> Dict[str, Any]:
        return {"user_id": user_id, "deleted": True}

    @classmethod
    async def ping_host(cls, host: str) -> Dict[str, Any]:
        # 参数列表 + shell=False，绝不拼接
        cmd = ["ping", "-c", "1", host]
        return {"command": cmd, "shell": False, "result": "模拟ping成功"}


# ============================================================
# 工具调用安全网关：串联 5 道防线
# ============================================================
class SecureToolGateway:
    def __init__(self, granted_permissions: set, hitl_manager: HumanInLoopManager):
        self.granted = granted_permissions
        self.hitl = hitl_manager
        self.registry: Dict[str, ToolSpec] = {}
        self._setup_tools()

    def _setup_tools(self):
        self.register(ToolSpec(
            name="search_docs",
            permission=ToolPermission.READ,
            auto_execute=True,
            schema={"keyword": {"type": str, "required": True}},
            executor=SafeTools.search_docs
        ))
        self.register(ToolSpec(
            name="query_database",
            permission=ToolPermission.READ,
            auto_execute=True,
            schema={
                "table": {"type": str, "required": True},
                "column": {"type": str, "required": True},
                "value": {"type": str, "required": True},
            },
            executor=SafeTools.query_database
        ))
        self.register(ToolSpec(
            name="create_order",
            permission=ToolPermission.WRITE,
            auto_execute=False,
            schema={
                "product_id": {"type": str, "required": True, "pattern": r"^[A-Za-z0-9_]+$"},
                "amount": {"type": float, "required": True, "gt": 0, "le": 100000},
            },
            executor=SafeTools.create_order
        ))
        self.register(ToolSpec(
            name="delete_user",
            permission=ToolPermission.DELETE,
            auto_execute=False,
            schema={"user_id": {"type": str, "required": True, "pattern": r"^\d+$"}},
            executor=SafeTools.delete_user
        ))
        self.register(ToolSpec(
            name="ping_host",
            permission=ToolPermission.EXECUTE,
            auto_execute=False,
            schema={"host": {"type": str, "required": True}},
            executor=SafeTools.ping_host
        ))

    def register(self, spec: ToolSpec):
        self.registry[spec.name] = spec

    async def call(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n🔧 请求调用工具: {tool_name}  参数: {params}")

        # ---- 防线①: 白名单 + 权限分级 ----
        spec = self.registry.get(tool_name)
        if not spec:
            return self._deny("防线①", f"未注册的工具: {tool_name}")
        if spec.permission not in self.granted:
            return self._deny("防线①", f"无权限调用 {spec.permission.value} 类工具 (当前权限: {[p.value for p in self.granted]})")
        print(f"   ✓ 防线①通过: {tool_name} 属于 {spec.permission.value} 类，已授权")

        # ---- 防线②: 参数 Schema 校验 ----
        try:
            validated = ParamValidator.validate(tool_name, spec.schema, params)
        except ParamValidationError as e:
            return self._deny("防线②", str(e))
        print(f"   ✓ 防线②通过: 参数Schema校验合法")

        # ---- 防线③: 参数安全检测 ----
        violation = self._security_scan(tool_name, validated)
        if violation:
            return self._deny("防线③", violation)
        print(f"   ✓ 防线③通过: 无注入风险")

        # ---- 防线④: 高危工具人工审批 ----
        if not spec.auto_execute:
            print(f"   ⏸️  防线④: {spec.permission.value} 类工具需人工审批...")
            approver_task = asyncio.create_task(self._auto_approve(spec.permission))
            result = await self.hitl.execute_with_approval(
                action=tool_name,
                params=validated,
                confidence=0.9,
                executor=spec.executor,
                timeout=10.0
            )
            await approver_task
            if result["status"] not in ("approved", "auto_approved"):
                return self._deny("防线④", f"审批未通过: {result['status']}")
            print(f"   ✓ 防线④通过: 审批通过")
            return {"success": True, "tool": tool_name, "result": result.get("result")}
        else:
            # ---- 防线⑤: 安全执行 ----
            try:
                result = await spec.executor(**validated)
            except SecurityViolationError as e:
                return self._deny("防线⑤", str(e))
            print(f"   ✓ 防线⑤通过: 安全执行完成")
            return {"success": True, "tool": tool_name, "result": result}

    def _security_scan(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        for key, value in params.items():
            if not isinstance(value, str):
                continue
            if tool_name == "query_database":
                v = SecurityChecker.check_sql(value)
                if v:
                    return f"参数 {key}: {v}"
            if tool_name == "ping_host":
                v = SecurityChecker.check_command(value)
                if v:
                    return f"参数 {key}: {v}"
        return None

    async def _auto_approve(self, permission: ToolPermission):
        await asyncio.sleep(0.5)
        pending = self.hitl.queue.get_pending()
        for req in pending:
            if permission == ToolPermission.DELETE:
                self.hitl.queue.decide(req.request_id, True, "security_admin", "删除操作已核实")
            else:
                self.hitl.queue.decide(req.request_id, True, "ops_admin", "操作合规")

    @staticmethod
    def _deny(line: str, reason: str) -> Dict[str, Any]:
        print(f"   ❌ {line}拦截: {reason}")
        return {"success": False, "blocked_at": line, "reason": reason}


# ============================================================
# 测试场景
# ============================================================
async def test_permission_control():
    print("\n" + "=" * 70)
    print("场景一：权限最小化 —— 只读Agent无法调用写/删工具")
    print("=" * 70)

    hitl = HumanInLoopManager()
    # 该Agent只被授予 READ 权限
    gateway = SecureToolGateway({ToolPermission.READ}, hitl)

    await gateway.call("search_docs", {"keyword": "机器学习"})
    await gateway.call("delete_user", {"user_id": "123"})  # 应被防线①拦截


async def test_param_validation():
    print("\n" + "=" * 70)
    print("场景二：参数Schema校验 —— 越界/格式非法被拦截")
    print("=" * 70)

    hitl = HumanInLoopManager()
    gateway = SecureToolGateway({ToolPermission.READ, ToolPermission.WRITE}, hitl)

    await gateway.call("create_order", {"product_id": "P001", "amount": 999999})  # 金额超限
    await gateway.call("create_order", {"product_id": "'; DROP--", "amount": 100})  # 格式非法


async def test_sql_injection():
    print("\n" + "=" * 70)
    print("场景三：SQL注入防护")
    print("=" * 70)

    hitl = HumanInLoopManager()
    gateway = SecureToolGateway({ToolPermission.READ}, hitl)

    await gateway.call("query_database", {"table": "products", "column": "name", "value": "iphone"})
    await gateway.call("query_database", {"table": "users", "column": "name", "value": "x'; DROP TABLE users--"})


async def test_command_injection():
    print("\n" + "=" * 70)
    print("场景四：命令注入防护")
    print("=" * 70)

    hitl = HumanInLoopManager()
    gateway = SecureToolGateway({ToolPermission.READ, ToolPermission.EXECUTE}, hitl)

    await gateway.call("ping_host", {"host": "example.com"})
    await gateway.call("ping_host", {"host": "example.com; rm -rf /"})  # 命令注入


async def test_approval_flow():
    print("\n" + "=" * 70)
    print("场景五：高危写操作 —— 人工审批流程")
    print("=" * 70)

    hitl = HumanInLoopManager()
    gateway = SecureToolGateway(
        {ToolPermission.READ, ToolPermission.WRITE, ToolPermission.DELETE}, hitl)

    await gateway.call("create_order", {"product_id": "P001", "amount": 5000})
    await gateway.call("delete_user", {"user_id": "456"})


async def main():
    print("=" * 80)
    print("🛡️ L6-05 扩展: 工具调用行为护栏 (5道防线)")
    print("=" * 80)

    await test_permission_control()
    await test_param_validation()
    await test_sql_injection()
    await test_command_injection()
    await test_approval_flow()

    print("\n" + "=" * 80)
    print("✅ 工具调用行为护栏演示完成")
    print("=" * 80)
    print("""
💡 5道防线总结:
   ① 工具白名单+读写分级: 默认拒绝，权限最小化（最可靠）
   ② 参数Schema校验: 类型/范围/格式约束
   ③ 参数安全检测: SQL注入/命令注入/路径穿越/SSRF
   ④ 高危工具人工审批: 写/删/执行类需人工确认
   ⑤ 执行层防御: 参数化查询/参数列表/白名单兜底

🔑 核心理念: 最可靠的不是"检测攻击"，而是"从架构上让攻击无效"
""")


if __name__ == "__main__":
    asyncio.run(main())