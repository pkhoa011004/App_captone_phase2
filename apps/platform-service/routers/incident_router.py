import logging
from fastapi import APIRouter, Depends
from models.incident import TriageRequest
from services.incident_service import IncidentService
from dependencies import get_incident_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Incidents"])


@router.post("/notify")
async def notify_incident(
    request: TriageRequest,
    service: IncidentService = Depends(get_incident_service),
) -> dict:
    """
    SRP: Router chỉ nhận request và ủy thác cho IncidentService.
    DIP: Nhận IncidentService qua FastAPI Depends (dependency injection).
    """
    logger.info(f"Received incident report for {request.incident_id}")
    return await service.handle(request)