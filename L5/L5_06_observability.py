import asyncio
import uuid
import time
import json
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
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
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    name: str
    context: SpanContext
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
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
        return json.dumps(log_entry, ensure_ascii=False, indent=2)
    
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
        self._collectors: List[Callable[[], List[MetricData]]] = []
    
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
    
    def add_collector(self, collector: Callable[[], List[MetricData]]):
        self._collectors.append(collector)
    
    def collect(self) -> List[MetricData]:
        metrics = []
        
        for name, label_dict in self._counters.items():
            for label_key, value in label_dict.items():
                labels = dict(label_key) if label_key else {}
                metrics.append(MetricData(
                    name=name,
                    type=MetricType.COUNTER,
                    value=value,
                    labels=labels
                ))
        
        for name, label_dict in self._gauges.items():
            for label_key, value in label_dict.items():
                labels = dict(label_key) if label_key else {}
                metrics.append(MetricData(
                    name=name,
                    type=MetricType.GAUGE,
                    value=value,
                    labels=labels
                ))
        
        for name, values in self._histograms.items():
            if values:
                metrics.append(MetricData(
                    name=f"{name}_count",
                    type=MetricType.COUNTER,
                    value=len(values)
                ))
                metrics.append(MetricData(
                    name=f"{name}_sum",
                    type=MetricType.COUNTER,
                    value=sum(values)
                ))
        
        for name, values in self._summaries.items():
            if values:
                sorted_values = sorted(values)
                n = len(sorted_values)
                p50 = sorted_values[int(n * 0.5)] if n > 0 else 0
                p90 = sorted_values[int(n * 0.9)] if n > 0 else 0
                p99 = sorted_values[int(n * 0.99)] if n > 0 else 0
                
                metrics.append(MetricData(name=f"{name}_p50", type=MetricType.GAUGE, value=p50))
                metrics.append(MetricData(name=f"{name}_p90", type=MetricType.GAUGE, value=p90))
                metrics.append(MetricData(name=f"{name}_p99", type=MetricType.GAUGE, value=p99))
        
        for collector in self._collectors:
            metrics.extend(collector())
        
        return metrics


class Tracer:
    def __init__(self, service_name: str = "agent"):
        self.service_name = service_name
        self._current_spans: Dict[str, Span] = {}
        self._completed_spans: List[Span] = []
    
    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:16]
    
    def start_span(self, name: str, parent_span: Optional[Span] = None) -> Span:
        trace_id = parent_span.context.trace_id if parent_span else self._generate_id()
        span_id = self._generate_id()
        parent_span_id = parent_span.context.span_id if parent_span else None
        
        context = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id
        )
        
        span = Span(
            name=name,
            context=context,
            start_time=time.time()
        )
        
        self._current_spans[span_id] = span
        return span
    
    def finish_span(self, span: Span, status: str = "completed"):
        span.finish(status)
        self._completed_spans.append(span)
        if span.context.span_id in self._current_spans:
            del self._current_spans[span.context.span_id]
    
    def inject(self, span: Span, carrier: Dict[str, str]) -> None:
        carrier["trace-id"] = span.context.trace_id
        carrier["span-id"] = span.context.span_id
        if span.context.parent_span_id:
            carrier["parent-span-id"] = span.context.parent_span_id
    
    def extract(self, carrier: Dict[str, str]) -> Optional[SpanContext]:
        trace_id = carrier.get("trace-id")
        span_id = carrier.get("span-id")
        if not trace_id or not span_id:
            return None
        
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=carrier.get("parent-span-id")
        )
    
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
                    "start_time": span.start_time,
                    "attributes": span.attributes
                })
        return sorted(summary, key=lambda x: x["start_time"])
    
    def clear_completed_spans(self):
        self._completed_spans.clear()


class ObservationCollector:
    def __init__(self):
        self.logger = StructuredLogger("observation")
        self.metrics = MetricsTracker()
        self.tracer = Tracer()
        self._exporters: List[Callable[[List[Any]], None]] = []
    
    def add_exporter(self, exporter: Callable[[List[Any]], None]):
        self._exporters.append(exporter)
    
    def export(self, data: List[Any]):
        for exporter in self._exporters:
            exporter(data)


class ObservabilityMixin:
    def __init__(self, collector: ObservationCollector = None):
        self._collector = collector or ObservationCollector()
    
    @property
    def logger(self) -> StructuredLogger:
        return self._collector.logger
    
    @property
    def metrics(self) -> MetricsTracker:
        return self._collector.metrics
    
    @property
    def tracer(self) -> Tracer:
        return self._collector.tracer


class MonitorAgent(ObservabilityMixin):
    def __init__(self, agent_id: str):
        super().__init__()
        self.agent_id = agent_id
        self._request_count = 0
        self._error_count = 0
        self._latency_records = deque(maxlen=100)
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        span = self.tracer.start_span(f"{self.agent_id}.process_request")
        start_time = time.time()
        
        self.metrics.increment("requests_total", agent_id=self.agent_id)
        self._request_count += 1
        
        try:
            await asyncio.sleep(0.1)
            
            if request.get("fail", False):
                raise Exception("模拟错误")
            
            latency = time.time() - start_time
            self._latency_records.append(latency)
            self.metrics.histogram("request_latency", latency)
            self.metrics.gauge("active_requests", self._request_count)
            
            span.attributes["status"] = "success"
            self.tracer.finish_span(span)
            
            self.logger.info(f"请求处理成功", 
                           request_id=request.get("id"),
                           latency_ms=latency * 1000)
            
            return {"status": "success", "data": "processed"}
            
        except Exception as e:
            self._error_count += 1
            self.metrics.increment("errors_total", agent_id=self.agent_id)
            
            span.attributes["status"] = "error"
            span.attributes["error"] = str(e)
            self.tracer.finish_span(span, status="error")
            
            self.logger.error(f"请求处理失败",
                           request_id=request.get("id"),
                           error=str(e))
            
            return {"status": "error", "error": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        latencies = list(self._latency_records)
        return {
            "agent_id": self.agent_id,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._request_count, 1),
            "avg_latency_ms": sum(latencies) / len(latencies) * 1000 if latencies else 0,
            "p90_latency_ms": sorted(latencies)[int(len(latencies)*0.9)] * 1000 if latencies else 0
        }


async def main():
    print("="*80)
    print("🏭 L5-06: Observability 可观测性演示")
    print("="*80)
    
    collector = ObservationCollector()
    monitor = MonitorAgent("demo_agent")
    monitor._collector = collector
    
    def console_exporter(data):
        print("\n📊 导出可观测数据:")
        for item in data:
            if isinstance(item, MetricData):
                print(f"  [{item.type.value}] {item.name} = {item.value:.2f} {json.dumps(item.labels)}")
    
    collector.add_exporter(console_exporter)
    
    print("\n📤 处理请求...")
    
    for i in range(10):
        request = {"id": f"REQ-{i+1}", "fail": i == 3 or i == 7}
        await monitor.process_request(request)
        await asyncio.sleep(0.05)
    
    print("\n" + "-"*60)
    print("📈 统计信息")
    print("-"*60)
    stats = monitor.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    print("\n" + "-"*60)
    print("📉 收集的指标")
    print("-"*60)
    metrics = collector.metrics.collect()
    for metric in metrics:
        print(f"  [{metric.type.value}] {metric.name} = {metric.value:.4f}")
    
    print("\n" + "-"*60)
    print("🔍 追踪信息")
    print("-"*60)
    if monitor.tracer._completed_spans:
        trace_id = monitor.tracer._completed_spans[0].context.trace_id
        trace_summary = monitor.tracer.get_trace_summary(trace_id)
        for span in trace_summary[:5]:
            print(f"  Span {span['span_id'][:8]}: {span['name']} ({span['duration_ms']:.2f}ms)")
    
    print("\n✅ Observability 演示完成")


if __name__ == "__main__":
    asyncio.run(main())