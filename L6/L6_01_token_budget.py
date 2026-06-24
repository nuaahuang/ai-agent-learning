import asyncio
import time
import json
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict


class BudgetStatus(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"


class BudgetPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    last_updated: float = field(default_factory=time.time)
    
    def add(self, input_tokens: int, output_tokens: int):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.call_count += 1
        self.last_updated = time.time()
    
    def reset(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.call_count = 0
        self.last_updated = time.time()


@dataclass
class BudgetConfig:
    total_tokens: int
    warning_threshold: float = 0.8
    critical_threshold: float = 0.9
    period: BudgetPeriod = BudgetPeriod.DAILY


class BudgetExceededError(Exception):
    """预算超限异常"""
    def __init__(self, message: str, usage: TokenUsage, budget: int):
        super().__init__(message)
        self.usage = usage
        self.budget = budget


class TokenBudgetManager:
    """Token 预算管理器"""
    
    def __init__(self):
        self._global_budget: Optional[BudgetConfig] = None
        self._agent_budgets: Dict[str, BudgetConfig] = {}
        self._global_usage = TokenUsage()
        self._agent_usage: Dict[str, TokenUsage] = defaultdict(TokenUsage)
        self._last_reset: Dict[str, float] = {}
        self._alerts: Dict[str, bool] = {}
    
    def set_global_budget(self, total_tokens: int, **kwargs):
        self._global_budget = BudgetConfig(total_tokens=total_tokens, **kwargs)
        self._last_reset["global"] = time.time()
    
    def set_agent_budget(self, agent_id: str, total_tokens: int, **kwargs):
        self._agent_budgets[agent_id] = BudgetConfig(total_tokens=total_tokens, **kwargs)
        self._last_reset[agent_id] = time.time()
    
    def _check_reset(self, key: str, config: BudgetConfig):
        now = time.time()
        last_reset = self._last_reset.get(key, 0)
        
        period_seconds = {
            BudgetPeriod.DAILY: 86400,
            BudgetPeriod.WEEKLY: 604800,
            BudgetPeriod.MONTHLY: 2592000,
        }[config.period]
        
        if now - last_reset >= period_seconds:
            if key == "global":
                self._global_usage.reset()
            else:
                self._agent_usage[key].reset()
            self._last_reset[key] = now
            self._alerts[key] = False
    
    def get_usage(self, agent_id: str = None) -> TokenUsage:
        if agent_id and agent_id in self._agent_budgets:
            self._check_reset(agent_id, self._agent_budgets[agent_id])
            return self._agent_usage[agent_id]
        return self._global_usage
    
    def get_status(self, agent_id: str = None) -> BudgetStatus:
        usage = self.get_usage(agent_id)
        
        if agent_id and agent_id in self._agent_budgets:
            budget = self._agent_budgets[agent_id]
        elif self._global_budget:
            budget = self._global_budget
        else:
            return BudgetStatus.NORMAL
        
        ratio = usage.total_tokens / budget.total_tokens
        
        if ratio >= 1.0:
            return BudgetStatus.EXHAUSTED
        elif ratio >= budget.critical_threshold:
            return BudgetStatus.CRITICAL
        elif ratio >= budget.warning_threshold:
            return BudgetStatus.WARNING
        return BudgetStatus.NORMAL
    
    def check_budget(self, agent_id: str = None, estimated_tokens: int = 0) -> bool:
        status = self.get_status(agent_id)
        
        if status == BudgetStatus.EXHAUSTED:
            return False
        
        usage = self.get_usage(agent_id)
        if agent_id and agent_id in self._agent_budgets:
            budget = self._agent_budgets[agent_id]
        elif self._global_budget:
            budget = self._global_budget
        else:
            return True
        
        if usage.total_tokens + estimated_tokens > budget.total_tokens:
            return False
        
        return True
    
    def consume(self, input_tokens: int, output_tokens: int, agent_id: str = None):
        if self._global_budget:
            self._check_reset("global", self._global_budget)
            self._global_usage.add(input_tokens, output_tokens)
            self._check_alert("global", self._global_budget, self._global_usage)
        
        if agent_id and agent_id in self._agent_budgets:
            self._check_reset(agent_id, self._agent_budgets[agent_id])
            self._agent_usage[agent_id].add(input_tokens, output_tokens)
            self._check_alert(agent_id, self._agent_budgets[agent_id], self._agent_usage[agent_id])
    
    def _check_alert(self, key: str, config: BudgetConfig, usage: TokenUsage):
        ratio = usage.total_tokens / config.total_tokens
        alert_key = f"alert_{key}"
        
        if ratio >= config.warning_threshold and not self._alerts.get(alert_key):
            self._alerts[alert_key] = True
            level = "WARNING" if ratio < config.critical_threshold else "CRITICAL"
            print(f"⚠️  [预算告警] {key} Token使用已达 {ratio*100:.1f}% ({level})")
    
    def get_remaining(self, agent_id: str = None) -> int:
        usage = self.get_usage(agent_id)
        
        if agent_id and agent_id in self._agent_budgets:
            return max(0, self._agent_budgets[agent_id].total_tokens - usage.total_tokens)
        elif self._global_budget:
            return max(0, self._global_budget.total_tokens - usage.total_tokens)
        return float('inf')
    
    def get_usage_report(self, agent_id: str = None) -> Dict[str, Any]:
        usage = self.get_usage(agent_id)
        status = self.get_status(agent_id)
        remaining = self.get_remaining(agent_id)
        
        if agent_id and agent_id in self._agent_budgets:
            budget = self._agent_budgets[agent_id].total_tokens
        elif self._global_budget:
            budget = self._global_budget.total_tokens
        else:
            budget = None
        
        return {
            "scope": agent_id or "global",
            "status": status.value,
            "budget": budget,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "call_count": usage.call_count,
            },
            "remaining_tokens": remaining,
            "usage_percentage": (usage.total_tokens / budget * 100) if budget else 0,
        }


class BudgetAwareLLMClient:
    """带预算控制的LLM客户端"""
    
    def __init__(self, budget_manager: TokenBudgetManager, agent_id: str = None):
        self.budget_manager = budget_manager
        self.agent_id = agent_id
        self.api_key = os.getenv("API_KEY", "")
        self.base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
        self.model = os.getenv("MODEL", "deepseek-chat")
    
    async def call_llm(self, messages: list, **kwargs) -> Dict[str, Any]:
        import httpx
        
        estimated_input = sum(len(m["content"]) for m in messages) // 4
        
        if not self.budget_manager.check_budget(self.agent_id, estimated_input):
            usage = self.budget_manager.get_usage(self.agent_id)
            budget = (self.budget_manager._agent_budgets.get(self.agent_id, 
                      self.budget_manager._global_budget))
            raise BudgetExceededError(
                f"Token预算不足，已使用 {usage.total_tokens} / {budget.total_tokens if budget else 'N/A'}",
                usage,
                budget.total_tokens if budget else 0
            )
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": kwargs.get("max_tokens", 1024),
                    "temperature": kwargs.get("temperature", 0.7),
                },
            )
            response.raise_for_status()
            result = response.json()
        
        usage_data = result.get("usage", {})
        input_tokens = usage_data.get("prompt_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0)
        
        self.budget_manager.consume(input_tokens, output_tokens, self.agent_id)
        
        return {
            "content": result["choices"][0]["message"]["content"],
            "usage": usage_data,
        }


async def main():
    print("=" * 80)
    print("💰 L6-01: Token 预算与熔断")
    print("=" * 80)
    
    budget_manager = TokenBudgetManager()
    
    budget_manager.set_global_budget(
        total_tokens=50000,
        warning_threshold=0.6,
        critical_threshold=0.8,
        period=BudgetPeriod.DAILY
    )
    
    budget_manager.set_agent_budget(
        "agent_a",
        total_tokens=20000,
        warning_threshold=0.6,
        critical_threshold=0.8,
    )
    
    budget_manager.set_agent_budget(
        "agent_b",
        total_tokens=30000,
        warning_threshold=0.6,
        critical_threshold=0.8,
    )
    
    print("\n" + "-" * 60)
    print("📊 初始预算状态")
    print("-" * 60)
    
    global_report = budget_manager.get_usage_report()
    print(f"全局预算: {global_report['budget']:,} tokens")
    print(f"Agent A 预算: {budget_manager._agent_budgets['agent_a'].total_tokens:,} tokens")
    print(f"Agent B 预算: {budget_manager._agent_budgets['agent_b'].total_tokens:,} tokens")
    
    print("\n" + "-" * 60)
    print("🔧 模拟 Token 消耗")
    print("-" * 60)
    
    for i in range(5):
        budget_manager.consume(1500 + i * 200, 800 + i * 100, "agent_a")
        status = budget_manager.get_status("agent_a")
        usage = budget_manager.get_usage("agent_a")
        print(f"  调用 {i+1}: Agent A 使用 {usage.total_tokens:,} tokens [{status.value}]")
    
    for i in range(3):
        budget_manager.consume(2000, 1200, "agent_b")
        status = budget_manager.get_status("agent_b")
        usage = budget_manager.get_usage("agent_b")
        print(f"  调用 {i+1}: Agent B 使用 {usage.total_tokens:,} tokens [{status.value}]")
    
    print("\n" + "-" * 60)
    print("📈 使用报告")
    print("-" * 60)
    
    agent_a_report = budget_manager.get_usage_report("agent_a")
    agent_b_report = budget_manager.get_usage_report("agent_b")
    
    print(f"\nAgent A:")
    print(f"  状态: {agent_a_report['status']}")
    print(f"  输入Token: {agent_a_report['usage']['input_tokens']:,}")
    print(f"  输出Token: {agent_a_report['usage']['output_tokens']:,}")
    print(f"  总Token: {agent_a_report['usage']['total_tokens']:,}")
    print(f"  调用次数: {agent_a_report['usage']['call_count']}")
    print(f"  使用率: {agent_a_report['usage_percentage']:.1f}%")
    print(f"  剩余: {agent_a_report['remaining_tokens']:,}")
    
    print(f"\nAgent B:")
    print(f"  状态: {agent_b_report['status']}")
    print(f"  总Token: {agent_b_report['usage']['total_tokens']:,}")
    print(f"  使用率: {agent_b_report['usage_percentage']:.1f}%")
    print(f"  剩余: {agent_b_report['remaining_tokens']:,}")
    
    print("\n" + "-" * 60)
    print("🔒 预算检查测试")
    print("-" * 60)
    
    can_call = budget_manager.check_budget("agent_a", 10000)
    print(f"Agent A 还能调用10000token吗? {'可以' if can_call else '不行'}")
    
    can_call = budget_manager.check_budget("agent_b", 25000)
    print(f"Agent B 还能调用25000token吗? {'可以' if can_call else '不行'}")
    
    print("\n" + "=" * 80)
    print("✅ Token 预算与熔断演示完成")
    print("=" * 80)
    
    print("""
💡 核心功能:
   - 全局预算 + 每个Agent独立预算
   - 三级告警: WARNING(60%) → CRITICAL(80%) → EXHAUSTED(100%)
   - 自动按周期重置（每日/每周/每月）
   - 调用前预检查，防止超额
   - 真实LLM调用后精确统计
""")


if __name__ == "__main__":
    asyncio.run(main())