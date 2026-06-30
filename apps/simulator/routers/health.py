from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health():
    """
    Kiểm tra tình trạng sức khoẻ của Mock Service
    """
    return {"status": "ok", "service": "simulator"}
