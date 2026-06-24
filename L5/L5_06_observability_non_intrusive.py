import asyncio
import uuid
import time
import json
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
from functools import wraps
from collections import defaultdict, deque


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None


@dataclass
class Span:
    name: str
    context: SpanContext
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self, status: str = "completed"):
        self.end_time = time.time()
        self.status = status
    
    @property
    def duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time


@dataclass
class MetricData:
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())


class StructuredLogger:
    def __init__(self, name: str):
        self.name = name
    
    def _format_log(self, level: LogLevel, message: str, **kwargs) -> str:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "logger": self.name,
            "message": message,
            **kwargs
        }
        return json.dumps(log_entry, ensure_ascii=False)
    
    def debug(self, message: str, **kwargs):
        print(self._format_log(LogLevel.DEBUG, message, **kwargs))
    
    def info(self, message: str, **kwargs):
        print(self._format_log(LogLevel.INFO, message, **kwargs))
    
    def warning(self, message: str, **kwargs):
        print(self._format_log(LogLevel.WARNING, message, **kwargs))
    
    def error(self, message: str, **kwargs):
        print(self._format_log(LogLevel.ERROR, message, **kwargs))
    
    def critical(self, message: str, **kwargs):
        print(self._format_log(LogLevel.CRITICAL, message, **kwargs))


class MetricsTracker:
    def __init__(self):
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._summaries: Dict[str, List[float]] = defaultdict(list)
    
    def increment(self, name: str, value: float = 1.0, **labels):
        label_key = tuple(sorted(labels.items()))
        self._counters[name][label_key] += value
    
    def gauge(self, name: str, value: float, **labels):
        label_key = tuple(sorted(labels.items()))
        self._gauges[name][label_key] = value
    
    def histogram(self, name: str, value: float):
        if len(self._histograms[name]) >= 1000:
            self._histograms[name].pop(0)
        self._histograms[name].append(value)
    
    def summary(self, name: str, value: float):
        if len(self._summaries[name]) >= 1000:
            self._summaries[name].pop(0)
        self._summaries[name].append(value)
    
    def collect(self) -> List[MetricData]:
        metrics = []
        
        for name, label_dict in self._counters.items():
            for label_key, value in label_dict.items():
                labels = dict(label_key) if label_key else {}
                metrics.append(MetricData(name=name, type=MetricType.COUNTER, value=value, labels=labels))
        
        for name, label_dict in self._gauges.items():
            for label_key, value in label_dict.items():
                labels = dict(label_key) if label_key else {}
                metrics.append(MetricData(name=name, type=MetricType.GAUGE, value=value, labels=labels))
        
        for name, values in self._histograms.items():
            if values:
                metrics.append(MetricData(name=f"{name}_count", type=MetricType.COUNTER, value=len(values)))
                metrics.append(MetricData(name=f"{name}_sum", type=MetricType.COUNTER, value=sum(values)))
                sorted_v = sorted(values)
                n = len(sorted_v)
                metrics.append(MetricData(name=f"{name}_p50", type=MetricType.GAUGE, value=sorted_v[int(n*0.5)]))
                metrics.append(MetricData(name=f"{name}_p90", type=MetricType.GAUGE, value=sorted_v[int(n*0.9)]))
                metrics.append(MetricData(name=f"{name}_p99", type=MetricType.GAUGE, value=sorted_v[int(n*0.99)]))
        
        return metrics


class Tracer:
    def __init__(self, service_name: str = "agent"):
        self.service_name = service_name
        self._current_span: Optional[Span] = None
        self._completed_spans: List[Span] = []
    
    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:16]
    
    def start_span(self, name: str, parent_span: Optional[Span] = None) -> Span:
        trace_id = parent_span.context.trace_id if parent_span else self._generate_id()
        span_id = self._generate_id()
        parent_span_id = parent_span.context.span_id if parent_span else None
        
        context = SpanContext(trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id)
        span = Span(name=name, context=context, start_time=time.time())
        return span
    
    def finish_span(self, span: Span, status: str = "completed"):
        span.finish(status)
        self._completed_spans.append(span)
    
    def get_trace_summary(self, trace_id: str) -> List[Dict[str, Any]]:
        summary = []
        for span in self._completed_spans:
            if span.context.trace_id == trace_id:
                summary.append({
                    "span_id": span.context.span_id,
                    "name": span.name,
                    "parent_span_id": span.context.parent_span_id,
                    "duration_ms": span.duration * 1000,
                    "status": span.status,
                })
        return sorted(summary, key=lambda x: x["span_id"])


class ObservationContext:
    _instance = None
    
    def __init__(self):
        self.logger = StructuredLogger("observation")
        self.metrics = MetricsTracker()
        self.tracer = Tracer()
        self._active_span: Optional[Span] = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_active_span(self) -> Optional[Span]:
        return self._active_span
    
    def set_active_span(self, span: Optional[Span]):
        self._active_span = span


class observ:
    """非侵入式可观测性装饰器集合"""
    
    @staticmethod
    def span(name: str = None, log_args: bool = False, log_result: bool = False):
        """
        追踪装饰器 - 自动创建span并记录执行时间
        
        使用方式:
            @observ.span()
            async def my_function():
                pass
        """
        def decorator(func):
            span_name = name or func.__name__
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                parent = ctx.get_active_span()
                span = ctx.tracer.start_span(span_name, parent)
                ctx.set_active_span(span)
                
                if log_args:
                    ctx.logger.debug(f"进入 {span_name}", args=str(args)[:100], kwargs=str(kwargs)[:100])
                
                try:
                    result = await func(*args, **kwargs)
                    ctx.tracer.finish_span(span, "completed")
                    
                    if log_result:
                        ctx.logger.debug(f"完成 {span_name}", result=str(result)[:100])
                    
                    return result
                except Exception as e:
                    span.attributes["error"] = str(e)
                    ctx.tracer.finish_span(span, "error")
                    ctx.logger.error(f"失败 {span_name}", error=str(e))
                    raise
                finally:
                    ctx.set_active_span(parent)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                parent = ctx.get_active_span()
                span = ctx.tracer.start_span(span_name, parent)
                ctx.set_active_span(span)
                
                if log_args:
                    ctx.logger.debug(f"进入 {span_name}", args=str(args)[:100], kwargs=str(kwargs)[:100])
                
                try:
                    result = func(*args, **kwargs)
                    ctx.tracer.finish_span(span, "completed")
                    
                    if log_result:
                        ctx.logger.debug(f"完成 {span_name}", result=str(result)[:100])
                    
                    return result
                except Exception as e:
                    span.attributes["error"] = str(e)
                    ctx.tracer.finish_span(span, "error")
                    ctx.logger.error(f"失败 {span_name}", error=str(e))
                    raise
                finally:
                    ctx.set_active_span(parent)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    @staticmethod
    def counter(metric_name: str, labels: Dict[str, str] = None):
        """
        计数器装饰器 - 自动记录调用次数
        
        使用方式:
            @observ.counter("api_calls")
            async def my_api():
                pass
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                ctx.metrics.increment(metric_name, **(labels or {}))
                return await func(*args, **kwargs)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                ctx.metrics.increment(metric_name, **(labels or {}))
                return func(*args, **kwargs)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    @staticmethod
    def latency(metric_name: str, labels: Dict[str, str] = None):
        """
        延迟装饰器 - 自动记录执行延迟
        
        使用方式:
            @observ.latency("api_latency")
            async def my_api():
                pass
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                start = time.time()
                try:
                    return await func(*args, **kwargs)
                finally:
                    latency = time.time() - start
                    ctx.metrics.histogram(metric_name, latency)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                start = time.time()
                try:
                    return func(*args, **kwargs)
                finally:
                    latency = time.time() - start
                    ctx.metrics.histogram(metric_name, latency)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    @staticmethod
    def error_counter(metric_name: str = "errors_total", labels: Dict[str, str] = None):
        """
        错误计数器装饰器 - 自动记录错误次数
        
        使用方式:
            @observ.error_counter()
            async def my_api():
                pass
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    ctx.metrics.increment(metric_name, **(labels or {}))
                    raise
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                ctx = ObservationContext.get_instance()
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    ctx.metrics.increment(metric_name, **(labels or {}))
                    raise
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    @staticmethod
    def monitored(name: str = None, log_level: LogLevel = LogLevel.INFO):
        """
        综合监控装饰器 - span + counter + latency + error + log 一站式
        
        使用方式:
            @observ.monitored()
            async def my_function():
                pass
        """
        def decorator(func):
            monitored_name = name or func.__name__
            
            counter_deco = observ.counter(f"{monitored_name}_total")
            latency_deco = observ.latency(f"{monitored_name}_latency")
            error_deco = observ.error_counter(f"{monitored_name}_errors")
            span_deco = observ.span(monitored_name, log_args=False, log_result=False)
            
            if asyncio.iscoroutinefunction(func):
                return span_deco(error_deco(latency_deco(counter_deco(func))))
            return span_deco(error_deco(latency_deco(counter_deco(func))))
        
        return decorator


class CleanBusinessAgent:
    """
    干净的业务Agent - 业务代码完全没有观测代码
    
    所有可观测性功能都通过装饰器实现
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
    
    @observ.monitored(name="process_request")
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求 - 纯业务逻辑"""
        await self._validate_request(request)
        data = await self._fetch_data(request.get("id"))
        result = await self._process_data(data)
        return {"status": "success", "data": result}
    
    @observ.span(name="validate_request")
    async def _validate_request(self, request: Dict[str, Any]):
        """验证请求"""
        await asyncio.sleep(0.02)
        if not request.get("id"):
            raise ValueError("请求缺少ID")
    
    @observ.span(name="fetch_data")
    async def _fetch_data(self, data_id: str) -> Dict[str, Any]:
        """获取数据"""
        await asyncio.sleep(0.05)
        return {"id": data_id, "content": "模拟数据", "value": 100}
    
    @observ.span(name="process_data")
    async def _process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理数据"""
        await asyncio.sleep(0.03)
        processed = data.copy()
        processed["processed"] = True
        processed["value"] = processed.get("value", 0) * 2
        return processed


async def main():
    print("="*80)
    print("🏭 L5-06: 非侵入式可观测性演示")
    print("="*80)
    
    ctx = ObservationContext.get_instance()
    
    agent = CleanBusinessAgent("demo_agent")
    
    print("\n📤 处理请求 (业务代码完全干净!)")
    print("-" * 60)
    
    for i in range(5):
        try:
            request = {"id": f"REQ-{i+1}", "fail": i == 2}
            result = await agent.process_request(request)
            print(f"✅ REQ-{i+1}: {result['status']}")
        except Exception as e:
            print(f"❌ REQ-{i+1}: {str(e)}")
    
    print("\n" + "-" * 60)
    print("📈 自动收集的指标")
    print("-" * 60)
    metrics = ctx.metrics.collect()
    for metric in metrics:
        print(f"  [{metric.type.value}] {metric.name} = {metric.value:.4f}")
    
    print("\n" + "-" * 60)
    print("🔍 自动生成的追踪链路")
    print("-" * 60)
    
    trace_ids = list(set(span.context.trace_id for span in ctx.tracer._completed_spans))
    print(f"共 {len(trace_ids)} 条追踪链路 (展示前2条):\n")
    
    for i, trace_id in enumerate(trace_ids[:2]):
        trace_summary = ctx.tracer.get_trace_summary(trace_id)
        print(f"📋 Trace {i+1}: {trace_id[:8]}...")
        
        span_map = {s["span_id"]: s for s in trace_summary}
        root_spans = [s for s in trace_summary if not s["parent_span_id"]]
        
        def print_span(span, level=0):
            indent = "  " * level
            print(f"{indent}↳ {span['name']} ({span['duration_ms']:.2f}ms) [{span['status']}]")
            children = [s for s in trace_summary if s["parent_span_id"] == span["span_id"]]
            for child in children:
                print_span(child, level + 1)
        
        for root in root_spans:
            print_span(root)
        
        if i < len(trace_ids[:2]) - 1:
            print()
    
    print("\n" + "=" * 80)
    print("✅ 非侵入式可观测性演示完成")
    print("=" * 80)
    
    print("""
💡 关键特点:
   - 业务代码完全干净，没有观测相关代码
   - 通过装饰器 @observ.monitored() 一键接入
   - 自动记录: 调用次数 + 延迟 + 错误数 + 追踪链路 + 日志
   - 支持同步和异步函数
""")


if __name__ == "__main__":
    asyncio.run(main())