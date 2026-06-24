# L5-06: Observability（可观测性）

## 1. 核心概念

### 1.1 Observability 定义

可观测性是指通过系统产生的数据来理解和推断系统内部状态的能力。它包含三个核心支柱：

| 支柱 | 描述 | 用途 |
|------|------|------|
| **Metrics** | 可量化的指标数据 | 监控系统健康状态 |
| **Logging** | 结构化的日志记录 | 追踪事件和问题 |
| **Tracing** | 分布式链路追踪 | 分析请求流程 |

### 1.2 可观测性 vs 监控

| 对比维度 | 监控 (Monitoring) | 可观测性 (Observability) |
|---------|-----------------|------------------------|
| **目标** | 验证已知假设 | 发现未知问题 |
| **数据来源** | 预定义指标 | 任意可观测数据 |
| **方式** | 白盒 | 黑盒 |
| **视角** | 仪表盘 | 探索式分析 |

---

## 2. 架构设计

### 2.1 可观测性架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent 系统                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │ Agent A │  │ Agent B │  │ Agent C │  │ Agent D │            │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘            │
│       │             │             │             │                 │
│       ▼             ▼             ▼             ▼                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    ObservationCollector                    │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                   │   │
│  │  │ Metrics │  │ Logging │  │ Tracing │                   │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘                   │   │
│  └───────┼───────────┼───────────┼──────────────────────────┘   │
│          │           │           │                               │
└──────────┼───────────┼───────────┼──────────────────────────────┘
           │           │           │
           ▼           ▼           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Observability Platform                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Prometheus  │  │   Loki      │  │  Jaeger     │        │
│  │ (Metrics)   │  │ (Logging)   │  │ (Tracing)   │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          ▼                                 │
│              ┌─────────────────┐                          │
│              │    Grafana      │                          │
│              │   (Dashboard)   │                          │
│              └─────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件职责

| 组件 | 职责 |
|------|------|
| **ObservationCollector** | 收集和聚合可观测数据 |
| **MetricsTracker** | 收集和上报指标 |
| **Logger** | 结构化日志记录 |
| **Tracer** | 分布式链路追踪 |
| **Exporter** | 导出数据到外部系统 |

---

## 3. 代码实现

### 3.1 Metrics 核心类

```python
class MetricsTracker:
    def __init__(self):
        self.counters = {}
        self.gauges = {}
        self.histograms = {}
    
    def increment(self, name: str, value: float = 1.0, labels: dict = None):
        # 计数器：递增数值
    
    def gauge(self, name: str, value: float, labels: dict = None):
        # 仪表盘：设置当前值
    
    def histogram(self, name: str, value: float, labels: dict = None):
        # 直方图：记录分布
```

### 3.2 Logger 核心类

```python
class StructuredLogger:
    def __init__(self, name: str):
        self.name = name
    
    def log(self, level: LogLevel, message: str, **kwargs):
        # 结构化日志记录
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "logger": self.name,
            "message": message,
            **kwargs
        }
```

### 3.3 Tracer 核心类

```python
class Tracer:
    def start_span(self, name: str, parent_span: Optional[Span] = None) -> Span:
        # 创建新的追踪 span
    
    def inject(self, span: Span, carrier: dict):
        # 将 span 信息注入到载体中
    
    def extract(self, carrier: dict) -> Optional[SpanContext]:
        # 从载体中提取 span 上下文
```

---

## 4. 应用场景

### 4.1 Agent 性能监控

监控 Agent 的响应时间、吞吐量、错误率等指标。

### 4.2 分布式追踪

追踪跨多个 Agent 的请求流程，定位性能瓶颈。

### 4.3 异常检测

通过日志和指标发现异常行为并告警。

### 4.4 资源管理

监控系统资源使用情况，优化资源分配。

---

## 5. 关键特性

### 5.1 指标类型

| 类型 | 说明 | 示例 |
|------|------|------|
| **Counter** | 单调递增计数器 | 请求总数 |
| **Gauge** | 可增可减的仪表盘 | 当前内存使用 |
| **Histogram** | 分布统计 | 响应时间分布 |
| **Summary** | 摘要统计 | P50/P90/P99 延迟 |

### 5.2 日志级别

| 级别 | 说明 | 使用场景 |
|------|------|----------|
| **DEBUG** | 详细调试信息 | 开发调试 |
| **INFO** | 一般信息 | 正常运行日志 |
| **WARNING** | 警告信息 | 潜在问题 |
| **ERROR** | 错误信息 | 可恢复错误 |
| **CRITICAL** | 严重错误 | 系统崩溃 |

### 5.3 追踪上下文

- **Trace ID**: 唯一标识一个请求
- **Span ID**: 唯一标识一个操作
- **Parent Span ID**: 父操作标识

---

## 6. 实践要点

### 6.1 指标命名规范

使用层次化命名：`agent.{agent_id}.{metric_name}`

### 6.2 日志结构化

始终使用结构化日志，便于查询和分析。

### 6.3 采样策略

对于高吞吐量系统，使用采样减少追踪数据量。

### 6.4 上下文传递

确保跨服务调用时传递追踪上下文。

---

## 7. 总结

可观测性是构建可靠系统的关键：
- **Metrics** 提供量化指标
- **Logging** 记录事件详情
- **Tracing** 追踪请求路径
- 三者结合实现完整的系统可观测性