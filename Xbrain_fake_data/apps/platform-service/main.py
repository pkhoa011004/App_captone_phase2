import asyncio
import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from config import config
from dependencies import get_incident_service
from routers.incident_router import router as incident_router
from routers.health_router import router as health_router
from services.sqs_consumer import SQSConsumer

# --- Logging setup (SRP: tập trung tại đây, không rải rác) ---
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


import uuid
from datetime import datetime
from models.incident import TriageRequest, Alert

# --- SQS alert handler (bridge SQS message → IncidentService) ---
async def handle_alert(body: dict) -> None:
    """
    Adapter chuyển dict từ SQS thành TriageRequest và gọi service.
    Hỗ trợ payload raw từ Alertmanager Webhook.
    """
    service = get_incident_service()
    
    if "alerts" in body and isinstance(body.get("alerts"), list):
        # Đây là Alertmanager Webhook payload
        for am_alert in body["alerts"]:
            if am_alert.get("status") != "firing":
                continue
                
            labels = am_alert.get("labels", {})
            annotations = am_alert.get("annotations", {})
            
            alert = Alert(
                alert_id=labels.get("alertname", "UnknownAlert"),
                source="prometheus",
                service=labels.get("service", "unknown"),
                severity=labels.get("severity", "high"),
                title=annotations.get("summary", labels.get("alertname", "Alert")),
                description=annotations.get("description", ""),
                started_at=am_alert.get("startsAt", ""),
                labels=labels
            )
            
            request = TriageRequest(
                correlation_id=str(uuid.uuid4()),
                tenant_id=labels.get("tenant_id", "unknown"),
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                environment=labels.get("environment", "sandbox"),
                received_at=datetime.utcnow().isoformat() + "Z",
                alert=alert
            )
            await service.handle(request)
    else:
        # Nếu payload đã là TriageRequest chuẩn
        request = TriageRequest(**body)
        await service.handle(request)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Lifespan context manager thay thế on_event("startup") deprecated.
    SRP: main.py chịu trách nhiệm khởi động background task.
    SQSConsumer được inject handler từ bên ngoài (DIP).
    """
    consumer = SQSConsumer(message_handler=handle_alert)
    task = asyncio.create_task(consumer.poll())
    logger.info("SQS consumer started.")
    yield
    task.cancel()


# --- App bootstrap ---
app = FastAPI(title=config.APP_NAME, lifespan=lifespan)
app.include_router(incident_router)
app.include_router(health_router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)