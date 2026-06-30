import os
import uuid
import time
import json
import asyncio
from datetime import datetime
from typing import Literal, Dict, Optional, List

from fastapi import APIRouter
from pydantic import BaseModel, Field
import httpx
import prometheus_client as prom

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanContext, TraceFlags, NonRecordingSpan
from opentelemetry.trace.status import Status, StatusCode

from config import settings

router = APIRouter(prefix="/dumbproxy", tags=["Telemetry Proxy"])

# --- Pydantic Models ---
class MetricPayload(BaseModel):
    name: str
    type: Literal["gauge", "counter"]
    value: float
    labels: Dict[str, str]

class LogPayload(BaseModel):
    tenant_id: str
    service: str
    environment: str
    level: str = "info"
    message: str
    trace_id: Optional[str] = None
    timestamp: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)

class TracePayload(BaseModel):
    tenant_id: str
    service: str
    environment: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation: str
    duration_ms: float
    status_code: str = "200"
    timestamp: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)

class TelemetryBatch(BaseModel):
    metrics: List[MetricPayload] = Field(default_factory=list)
    logs: List[LogPayload] = Field(default_factory=list)
    traces: List[TracePayload] = Field(default_factory=list)

# --- State ---
metric_registry = {}
log_queue = asyncio.Queue()

# --- OTel Setup ---
otlp_endpoint = os.getenv("OTLP_ENDPOINT", "")
resource = Resource.create({"service.name": settings.SERVICE_NAME})
provider = TracerProvider(resource=resource)
if otlp_endpoint:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(settings.TRACER_NAME)

# --- Background Workers ---
async def loki_worker():
    loki_url = settings.DEFAULT_LOKI_URL
    async with httpx.AsyncClient() as client:
        while True:
            logs = []
            try:
                # Wait for at least one log
                log = await log_queue.get()
                logs.append(log)
                
                # Fetch more logs if available to batch them up
                while len(logs) < 500:
                    try:
                        next_log = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                        logs.append(next_log)
                    except asyncio.TimeoutError:
                        break
                
                streams = []
                for l in logs:
                    labels = {
                        "job": settings.SERVICE_NAME,
                        "tenant_id": l.tenant_id,
                        "service": l.service,
                        "environment": l.environment,
                        "level": l.level
                    }
                    labels.update(l.labels)
                    
                    line = json.dumps({
                        "message": l.message,
                        "trace_id": l.trace_id,
                        "timestamp": l.timestamp or datetime.now().isoformat()
                    })
                    ts_ns = str(time.time_ns())
                    streams.append({"stream": labels, "values": [[ts_ns, line]]})
                
                payload = {"streams": streams}
                await client.post(f"{loki_url.rstrip('/')}/loki/api/v1/push", json=payload, timeout=settings.LOKI_TIMEOUT)
            except Exception as e:
                print(f"Loki worker error: {e}")

@router.on_event("startup")
async def startup_event():
    asyncio.create_task(loki_worker())

# --- API Endpoints ---
@router.post("/inject-batch", status_code=202)
async def inject_batch(batch: TelemetryBatch):
    # Process Metrics
    for m in batch.metrics:
        if m.name not in metric_registry:
            label_keys = list(m.labels.keys())
            if m.type == "gauge":
                metric_registry[m.name] = prom.Gauge(m.name, "Dynamic gauge", label_keys)
            else:
                metric_registry[m.name] = prom.Counter(m.name, "Dynamic counter", label_keys)
        
        prom_metric = metric_registry[m.name]
        try:
            if m.type == "gauge":
                prom_metric.labels(**m.labels).set(m.value)
            else:
                prom_metric.labels(**m.labels).inc(m.value)
        except Exception as e:
            print(f"Metric label error for {m.name}: {e}")
            
    # Process Logs
    for log in batch.logs:
        await log_queue.put(log)
        
    # Process Traces
    for t in batch.traces:
        try:
            tid = int(t.trace_id.replace("-", ""), 16) if t.trace_id else uuid.uuid4().int
            pid = int(t.parent_span_id.replace("-", ""), 16) if t.parent_span_id else 0
        except ValueError:
            tid = uuid.uuid4().int
            pid = 0
            
        ctx = trace.set_span_in_context(NonRecordingSpan(SpanContext(
            trace_id=tid & ((1 << 128) - 1),  # ensure 128-bit
            span_id=pid & ((1 << 64) - 1),    # ensure 64-bit
            is_remote=True,
            trace_flags=TraceFlags(0x01)
        )))
        
        end_ns = time.time_ns()
        start_ns = end_ns - int(t.duration_ms * 1_000_000)
        
        span = tracer.start_span(t.operation, context=ctx, start_time=start_ns)
        attrs = {
            "tenant_id": t.tenant_id,
            "service": t.service,
            "environment": t.environment,
        }
        attrs.update(t.labels)
        span.set_attributes(attrs)
        
        if t.status_code != "200":
            span.set_status(Status(StatusCode.ERROR))
            
        span.end(end_time=end_ns)
        
    return {"status": "accepted", "metrics": len(batch.metrics), "logs": len(batch.logs), "traces": len(batch.traces)}
