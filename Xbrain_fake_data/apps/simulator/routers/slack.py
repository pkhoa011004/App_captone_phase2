from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/services", tags=["Slack"])

@router.post("/{path:path}")
async def slack_webhook(path: str, request: Request):
    """
    Mock Slack Webhook Endpoint.
    Bắt mọi request POST gửi tới dạng /services/Txxxxx/Bxxxxx/...
    - Nhận: JSON payload chứa { "text": "..." }
    - Trả về: Text "ok" kèm HTTP 200 (Chuẩn webhook của Slack)
    """
    try:
        data = await request.json()
    except Exception:
        return PlainTextResponse("invalid_payload", status_code=400)
        
    text = data.get("text")
    if not text:
        return PlainTextResponse("missing_text_field", status_code=400)
        
    print(f"✅ [MOCK SLACK] MESSAGE RECEIVED on /services/{path}: \n{text}\n")
    return PlainTextResponse("ok", status_code=status.HTTP_200_OK)
