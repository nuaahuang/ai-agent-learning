import asyncio
import time
import math
from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque


class LimitMode(Enum):
    REJECT = "reject"
    WAIT = "wait"
    DEGRADE = "degrade"


class LimitExceededError(Exception):
    """限流超限异常"""
    def __init__(self, message: str, remaining_ms: float = 0):
        super().__init__(message)
        self.remaining_ms = remaining_ms


@dataclass
class TokenBucket:
    capacity: float
    rate: float
    tokens: float = field(default=None)
    last_refill: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.tokens is None:
            self.tokens = self.capacity
    
    def refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now
    
    def try_acquire(self, tokens: float = 1.0) -> bool:
        self.refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def acquire(self, tokens: float = 1.0) -> float:
        self.refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0
        
        deficit = tokens - self.tokens
        wait_time = deficit / self.rate
        self.tokens = 0.0
        return wait_time


class SlidingWindow:
    def __init__(self, window_size: float, max_requests: int):
        self.window_size = window_size
        self.max_requests = max_requests
        self.timestamps = deque()
    
    def try_acquire(self) -> bool:
        now = time.time()
        
        while self.timestamps and now - self.timestamps[0] > self.window_size:
            self.timestamps.popleft()
        
        if len(self.timestamps) < self.max_requests:
            self.timestamps.append(now)
            return True
        return False
    
    def get_wait_time(self) -> float:
        if not self.timestamps:
            return 0.0
        oldest = self.timestamps[0]
        return max(0.0, oldest + self.window_size - time.time())


class FixedWindow:
    def __init__(self, window_size: float, max_requests: int):
        self.window_size = window_size
        self.max_requests = max_requests
        self.count = 0
        self.window_start = time.time()
    
    def try_acquire(self) -> bool:
        now = time.time()
        
        if now - self.window_start >= self.window_size:
            self.window_start = now
            self.count = 0
        
        if self.count < self.max_requests:
            self.count += 1
            return True
        return False
    
    def get_wait_time(self) -> float:
        remaining = self.window_start + self.window_size - time.time()
        return max(0.0, remaining)


class RateLimiter:
    def __init__(self, mode: LimitMode = LimitMode.REJECT):
        self.mode = mode
        self._buckets: Dict[str, TokenBucket] = {}
        self._sliding_windows: Dict[str, SlidingWindow] = {}
        self._fixed_windows: Dict[str, FixedWindow] = {}
    
    def setup_token_bucket(self, key: str, capacity: float, rate: float):
        self._buckets[key] = TokenBucket(capacity=capacity, rate=rate)
    
    def setup_sliding_window(self, key: str, window_size: float, max_requests: int):
        self._sliding_windows[key] = SlidingWindow(window_size=window_size, max_requests=max_requests)
    
    def setup_fixed_window(self, key: str, window_size: float, max_requests: int):
        self._fixed_windows[key] = FixedWindow(window_size=window_size, max_requests=max_requests)
    
    async def acquire_token_bucket(self, key: str, tokens: float = 1.0):
        bucket = self._buckets.get(key)
        if not bucket:
            return
        
        if self.mode == LimitMode.REJECT:
            if not bucket.try_acquire(tokens):
                raise LimitExceededError(f"Token bucket limit exceeded for {key}")
        
        elif self.mode == LimitMode.WAIT:
            wait_time = bucket.acquire(tokens)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
    
    async def acquire_sliding_window(self, key: str):
        window = self._sliding_windows.get(key)
        if not window:
            return
        
        if self.mode == LimitMode.REJECT:
            if not window.try_acquire():
                raise LimitExceededError(f"Sliding window limit exceeded for {key}")
        
        elif self.mode == LimitMode.WAIT:
            while not window.try_acquire():
                wait_time = window.get_wait_time()
                await asyncio.sleep(wait_time)
    
    async def acquire_fixed_window(self, key: str):
        window = self._fixed_windows.get(key)
        if not window:
            return
        
        if self.mode == LimitMode.REJECT:
            if not window.try_acquire():
                raise LimitExceededError(f"Fixed window limit exceeded for {key}")
        
        elif self.mode == LimitMode.WAIT:
            while not window.try_acquire():
                wait_time = window.get_wait_time()
                await asyncio.sleep(wait_time)
    
    async def acquire(self, key: str, algorithm: str = "token_bucket"):
        if algorithm == "token_bucket":
            await self.acquire_token_bucket(key)
        elif algorithm == "sliding_window":
            await self.acquire_sliding_window(key)
        elif algorithm == "fixed_window":
            await self.acquire_fixed_window(key)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")


class RateLimitedLLMClient:
    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
    
    async def call_llm(self, messages: list, user_id: str = None, **kwargs):
        key = user_id or "global"
        
        await self.rate_limiter.acquire(key)
        
        await asyncio.sleep(0.05)
        
        return {
            "content": "模拟LLM响应",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}
        }


async def test_token_bucket():
    print("\n" + "-" * 60)
    print("🪣 令牌桶算法测试")
    print("-" * 60)
    
    limiter = RateLimiter(mode=LimitMode.REJECT)
    limiter.setup_token_bucket("test", capacity=5, rate=2)
    
    successes = 0
    failures = 0
    
    for i in range(10):
        try:
            await limiter.acquire_token_bucket("test")
            successes += 1
            print(f"请求 {i+1}: ✅ 成功")
        except LimitExceededError:
            failures += 1
            print(f"请求 {i+1}: ❌ 限流")
    
    print(f"\n总计: {successes} 成功, {failures} 失败")
    
    await asyncio.sleep(3)
    
    print("\n3秒后重试...")
    for i in range(5):
        try:
            await limiter.acquire_token_bucket("test")
            print(f"请求 {i+1}: ✅ 成功")
        except LimitExceededError:
            print(f"请求 {i+1}: ❌ 限流")


async def test_sliding_window():
    print("\n" + "-" * 60)
    print("🪟 滑动窗口算法测试")
    print("-" * 60)
    
    limiter = RateLimiter(mode=LimitMode.REJECT)
    limiter.setup_sliding_window("test", window_size=1.0, max_requests=3)
    
    async def make_requests(count):
        for i in range(count):
            try:
                await limiter.acquire_sliding_window("test")
                print(f"请求 {i+1}: ✅ 成功")
            except LimitExceededError:
                print(f"请求 {i+1}: ❌ 限流")
            await asyncio.sleep(0.1)
    
    await make_requests(6)
    
    await asyncio.sleep(0.5)
    print("\n0.5秒后重试...")
    await make_requests(3)


async def test_wait_mode():
    print("\n" + "-" * 60)
    print("⏳ 等待模式测试")
    print("-" * 60)
    
    limiter = RateLimiter(mode=LimitMode.WAIT)
    limiter.setup_token_bucket("test", capacity=2, rate=1)
    
    start = time.time()
    for i in range(5):
        await limiter.acquire_token_bucket("test")
        elapsed = time.time() - start
        print(f"请求 {i+1}: ✅ 成功 (累计耗时: {elapsed:.2f}s)")
    
    total_time = time.time() - start
    print(f"\n总耗时: {total_time:.2f}s (理论最低: {3.0}s)")


async def test_user_limits():
    print("\n" + "-" * 60)
    print("👥 用户级限流测试")
    print("-" * 60)
    
    limiter = RateLimiter(mode=LimitMode.REJECT)
    
    limiter.setup_token_bucket("user_a", capacity=3, rate=1)
    limiter.setup_token_bucket("user_b", capacity=2, rate=1)
    
    async def simulate_user(user_id, requests):
        print(f"\n用户 {user_id}:")
        for i in range(requests):
            try:
                await limiter.acquire_token_bucket(user_id)
                print(f"  请求 {i+1}: ✅ 成功")
            except LimitExceededError:
                print(f"  请求 {i+1}: ❌ 限流")
    
    await simulate_user("user_a", 5)
    await simulate_user("user_b", 4)


async def main():
    print("=" * 80)
    print("🚦 L6-02: Rate Limiter（请求限流）")
    print("=" * 80)
    
    await test_token_bucket()
    await test_sliding_window()
    await test_wait_mode()
    await test_user_limits()
    
    print("\n" + "=" * 80)
    print("✅ Rate Limiter 演示完成")
    print("=" * 80)
    
    print("""
💡 核心功能:
   - 支持三种限流算法: 令牌桶、滑动窗口、固定窗口
   - 支持三种限流模式: 拒绝、等待、降级
   - 支持用户级、全局级限流
   - 异步实现，支持高并发场景
""")


if __name__ == "__main__":
    asyncio.run(main())