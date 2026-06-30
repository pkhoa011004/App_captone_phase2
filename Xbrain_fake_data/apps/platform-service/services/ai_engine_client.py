import httpx
import logging
from interfaces.ai_client import IAiClient
from models.incident import TriageRequest, TriageResponse
from config import config

logger = logging.getLogger(__name__)

class AiEngineClient(IAiClient):
    def __init__(self):
        self.base_url = config.AI_ENGINE_URL

    async def triage(self, request: TriageRequest) -> TriageResponse:
        url = f"{self.base_url}/v1/triage"
        headers = {
            "X-Tenant-Id": request.tenant_id,
            "X-Correlation-Id": request.correlation_id,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=request.model_dump(), headers=headers)
                response.raise_for_status()
                return TriageResponse(**response.json())
            except Exception as e:
                logger.error(f"Failed to call AI engine: {e}")
                raise
