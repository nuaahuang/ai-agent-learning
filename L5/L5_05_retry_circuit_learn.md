# L5-05: Retry & Circuit Breaker（重试与熔断）

## 1. 核心概念

### 1.1 重试机制 (Retry)

重试机制是一种容错策略，当调用失败时自动重新尝试调用，直到成功或达到最大重试次数。

**适用场景**：
- 瞬时网络抖动
- 服务临时不可用
- 资源暂时不可用

**重试策略**：
- **固定间隔重试**：每次重试间隔相同时间
- **指数退避重试**：重试间隔呈指数增长
- **抖动退避重试**：在指数退避基础上添加随机抖动

### 1.2 熔断机制 (Circuit Breaker)

熔断机制是一种保护机制，当服务故障率达到阈值时，自动断开调用，防止级联故障。

**三种状态**：
- **Closed（闭合）**：正常状态，允许调用
- **Open（打开）**：熔断状态，拒绝调用
- **Half-Open（半开）**：尝试恢复状态，允许少量调用

**工作原理**：
```
Closed → 失败率超过阈值 → Open → 等待一段时间 → Half-Open → 测试调用成功 → Closed
                                                              ↓ 失败
                                                           Open
```

---

## 2. 架构设计

### 2.1 组件关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                    调用方 (Caller)                              │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RetryPolicy                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  max_retries: 3                                        │   │
│  │  backoff_strategy: ExponentialBackoff                   │   │
│  │  retry_on: [NetworkError, TimeoutError]                 │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CircuitBreaker                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  State: Closed/Open/Half-Open                           │   │
│  │  failure_threshold: 50%                                 │   │
│  │  reset_timeout: 30s                                     │   │
│  │  sliding_window_size: 100                                │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    目标服务 (Target Service)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件职责

| 组件 | 职责 |
|------|------|
| **RetryPolicy** | 定义重试策略（次数、间隔、退避策略） |
| **CircuitBreaker** | 管理熔断状态，保护下游服务 |
| **BackoffStrategy** | 计算重试间隔时间 |
| **FailureDetector** | 检测失败并更新统计 |

---

## 3. 代码实现

### 3.1 Retry 核心逻辑

```python
class RetryPolicy:
    def __init__(
        self,
        max_retries: int = 3,
        backoff_strategy: BackoffStrategy = ExponentialBackoff()
    ):
        self.max_retries = max_retries
        self.backoff_strategy = backoff_strategy
    
    async def execute(self, func, *args, **kwargs):
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.backoff_strategy.get_delay(attempt)
                    await asyncio.sleep(delay)
        
        raise last_exception
```

### 3.2 Circuit Breaker 核心逻辑

```python
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: float = 0.5,
        reset_timeout: float = 30.0,
        sliding_window_size: int = 100
    ):
        self.state = CircuitState.CLOSED
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.sliding_window_size = sliding_window_size
        self.metrics = RollingWindowMetrics(window_size=sliding_window_size)
        self.last_open_time = 0.0
    
    async def execute(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_open_time >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerError("Circuit is open")
        
        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            self._update_state()
            raise
    
    def _update_state(self):
        failure_rate = self.metrics.get_failure_rate()
        if failure_rate >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.last_open_time = time.time()
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
```

---

## 4. 应用场景

### 4.1 微服务调用

在微服务架构中，重试和熔断是保护服务稳定性的关键机制。

### 4.2 API 调用

对外 API 调用时，网络不稳定是常见问题，需要重试机制。

### 4.3 数据库操作

数据库连接池可能暂时耗尽，需要重试获取连接。

### 4.4 大模型调用

大模型 API 可能有 rate limit，需要配合重试和熔断。

---

## 5. 关键特性

### 5.1 重试退避策略

| 策略 | 特点 | 适用场景 |
|------|------|----------|
| **固定间隔** | 每次间隔相同 | 简单场景 |
| **指数退避** | 间隔指数增长 | 高并发场景 |
| **抖动退避** | 指数+随机抖动 | 分布式系统 |

### 5.2 熔断状态管理

- **Closed**：正常工作状态
- **Open**：熔断状态，直接拒绝请求
- **Half-Open**：尝试恢复，允许少量请求测试

### 5.3 指标收集

收集调用成功率、延迟、错误类型等指标，用于监控和决策。

---

## 6. 实践要点

### 6.1 重试注意事项

- **幂等性**：确保重试操作是幂等的
- **超时设置**：为每次重试设置合理超时
- **错误类型过滤**：只对可重试错误进行重试

### 6.2 熔断配置

- **阈值设置**：根据服务特性设置合理的失败阈值
- **超时时间**：设置合理的熔断恢复时间
- **监控告警**：监控熔断状态变化并及时告警

### 6.3 组合使用

重试和熔断通常组合使用：
```
Retry → CircuitBreaker → Target Service
```

---

## 7. 总结

Retry 和 Circuit Breaker 是构建高可用系统的关键组件：
- **Retry** 解决瞬时故障问题
- **Circuit Breaker** 防止级联故障
- 两者结合可以显著提高系统稳定性