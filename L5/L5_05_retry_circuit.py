import asyncio
import time
import random
from enum import Enum
from typing import Callable, Any, Optional, List, Type
from dataclasses import dataclass


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    pass


class RollingWindowMetrics:
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.successes = 0
        self.failures = 0
        self._buffer = []
    
    def record_success(self):
        self.successes += 1
        self._buffer.append(True)
        self._trim()
    
    def record_failure(self):
        self.failures += 1
        self._buffer.append(False)
        self._trim()
    
    def _trim(self):
        while len(self._buffer) > self.window_size:
            result = self._buffer.pop(0)
            if result:
                self.successes -= 1
            else:
                self.failures -= 1
    
    def get_failure_rate(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 0.0
        return self.failures / total
    
    def get_total_count(self) -> int:
        return self.successes + self.failures
    
    def reset(self):
        self.successes = 0
        self.failures = 0
        self._buffer = []


class BackoffStrategy:
    def get_delay(self, attempt: int) -> float:
        raise NotImplementedError


class FixedBackoff(BackoffStrategy):
    def __init__(self, delay: float = 1.0):
        self.delay = delay
    
    def get_delay(self, attempt: int) -> float:
        return self.delay


class ExponentialBackoff(BackoffStrategy):
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)


class JitterBackoff(BackoffStrategy):
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        delay = min(delay, self.max_delay)
        jitter = random.uniform(0, delay * 0.5)
        return delay + jitter


class RetryPolicy:
    def __init__(
        self,
        max_retries: int = 3,
        backoff_strategy: BackoffStrategy = None,
        retry_on: Optional[List[Type[Exception]]] = None
    ):
        self.max_retries = max_retries
        self.backoff_strategy = backoff_strategy or ExponentialBackoff()
        self.retry_on = retry_on or []
    
    def _should_retry(self, exception: Exception) -> bool:
        if not self.retry_on:
            return True
        return isinstance(exception, tuple(self.retry_on))
    
    async def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                last_exception = e
                
                if not self._should_retry(e):
                    raise
                
                if attempt < self.max_retries:
                    delay = self.backoff_strategy.get_delay(attempt)
                    print(f"⏳ 重试 {attempt + 1}/{self.max_retries}, 等待 {delay:.2f}s...")
                    await asyncio.sleep(delay)
        
        raise last_exception


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: float = 0.5,
        reset_timeout: float = 30.0,
        sliding_window_size: int = 100,
        half_open_max_calls: int = 10
    ):
        self.state = CircuitState.CLOSED
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        self.metrics = RollingWindowMetrics(window_size=sliding_window_size)
        self.last_open_time = 0.0
        self.half_open_call_count = 0
    
    def _check_state(self):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_open_time >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_call_count = 0
                self.metrics.reset()
                print("🔄 熔断状态变为 Half-Open")
    
    def _update_state(self):
        failure_rate = self.metrics.get_failure_rate()
        
        if self.state == CircuitState.HALF_OPEN:
            if self.metrics.get_total_count() >= self.half_open_max_calls:
                if failure_rate < self.failure_threshold:
                    self.state = CircuitState.CLOSED
                    self.metrics.reset()
                    print("✅ 熔断状态变为 Closed")
                else:
                    self.state = CircuitState.OPEN
                    self.last_open_time = time.time()
                    print("❌ 熔断状态变为 Open")
        elif self.state == CircuitState.CLOSED:
            if self.metrics.get_total_count() >= self.metrics.window_size:
                if failure_rate >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.last_open_time = time.time()
                    print("🔥 熔断触发！状态变为 Open")
    
    async def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        self._check_state()
        
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(f"熔断已触发，拒绝调用（上次打开时间: {time.time() - self.last_open_time:.1f}s 前）")
        
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_call_count += 1
        
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            
            self.metrics.record_success()
            self._update_state()
            return result
        except Exception as e:
            self.metrics.record_failure()
            self._update_state()
            raise
    
    def get_state(self) -> CircuitState:
        self._check_state()
        return self.state
    
    def get_metrics(self) -> dict:
        return {
            "state": self.state.value,
            "successes": self.metrics.successes,
            "failures": self.metrics.failures,
            "failure_rate": self.metrics.get_failure_rate(),
            "last_open_time": self.last_open_time
        }


@dataclass
class ResilientCallResult:
    success: bool
    result: Optional[Any]
    error: Optional[Exception]
    retry_attempts: int
    circuit_state: CircuitState


class ResilientClient:
    def __init__(
        self,
        retry_policy: RetryPolicy = None,
        circuit_breaker: CircuitBreaker = None
    ):
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
    
    async def execute(
        self,
        func: Callable[..., Any],
        *args,
        **kwargs
    ) -> ResilientCallResult:
        attempts = 0
        
        async def wrapped_func():
            nonlocal attempts
            attempts += 1
            return await self.circuit_breaker.execute(func, *args, **kwargs)
        
        try:
            result = await self.retry_policy.execute(wrapped_func)
            return ResilientCallResult(
                success=True,
                result=result,
                error=None,
                retry_attempts=attempts,
                circuit_state=self.circuit_breaker.get_state()
            )
        except CircuitBreakerError as e:
            return ResilientCallResult(
                success=False,
                result=None,
                error=e,
                retry_attempts=attempts,
                circuit_state=self.circuit_breaker.get_state()
            )
        except Exception as e:
            return ResilientCallResult(
                success=False,
                result=None,
                error=e,
                retry_attempts=attempts,
                circuit_state=self.circuit_breaker.get_state()
            )


class UnreliableService:
    def __init__(self, failure_rate: float = 0.3):
        self.failure_rate = failure_rate
        self.call_count = 0
    
    async def process_request(self, request_id: str) -> str:
        self.call_count += 1
        print(f"📡 处理请求 #{self.call_count}: {request_id}")
        
        if random.random() < self.failure_rate:
            raise Exception(f"服务暂时不可用 - 请求 {request_id}")
        
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return f"请求 {request_id} 处理成功"


async def simulate_service_failure(service: UnreliableService, duration: float = 10):
    original_rate = service.failure_rate
    service.failure_rate = 0.95
    print(f"⚠️ 模拟服务故障开始（持续 {duration}s）")
    
    await asyncio.sleep(duration)
    
    service.failure_rate = original_rate
    print("✅ 服务恢复正常")


async def main():
    print("="*80)
    print("🏭 L5-05: Retry & Circuit Breaker 演示")
    print("="*80)
    
    service = UnreliableService(failure_rate=0.3)
    
    retry_policy = RetryPolicy(
        max_retries=3,
        backoff_strategy=JitterBackoff(base_delay=0.5)
    )
    
    circuit_breaker = CircuitBreaker(
        failure_threshold=0.5,
        reset_timeout=5.0,
        sliding_window_size=20
    )
    
    client = ResilientClient(
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker
    )
    
    asyncio.create_task(simulate_service_failure(service, duration=15))
    
    successes = 0
    failures = 0
    
    for i in range(30):
        request_id = f"REQ-{i+1:03d}"
        
        result = await client.execute(service.process_request, request_id)
        
        if result.success:
            successes += 1
            print(f"✅ {result.result} (重试: {result.retry_attempts}次)")
        else:
            failures += 1
            print(f"❌ 请求 {request_id} 失败: {result.error}")
        
        await asyncio.sleep(0.2)
    
    print("\n" + "-"*60)
    print("执行统计")
    print("-"*60)
    print(f"总请求: {successes + failures}")
    print(f"成功: {successes} ({successes/(successes+failures)*100:.1f}%)")
    print(f"失败: {failures} ({failures/(successes+failures)*100:.1f}%)")
    print(f"最终熔断状态: {circuit_breaker.get_state().value}")
    print(f"熔断指标: {circuit_breaker.get_metrics()}")
    
    print("\n✅ Retry & Circuit Breaker 演示完成")


if __name__ == "__main__":
    asyncio.run(main())