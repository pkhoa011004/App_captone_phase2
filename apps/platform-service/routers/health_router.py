from fastapi import APIRouter
from config import config

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict:
    """
    SRP: Endpoint này chỉ phản ánh trạng thái ứng dụng,
         tách biệt hoàn toàn khỏi business logic incident.
    """
    return {"status": "ok", "environment": config.ENV_NAME}