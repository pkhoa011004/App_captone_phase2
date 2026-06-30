import logging
from models.incident import TriageRequest, TriageResponse
from interfaces.notifier import INotifier
from interfaces.ticket_creator import ITicketCreator
from interfaces.ai_client import IAiClient
from config import config

logger = logging.getLogger(__name__)


class IncidentService:
    def __init__(self, ai_client: IAiClient, ticket_creator: ITicketCreator, notifier: INotifier) -> None:
        self._ai_client = ai_client
        self._ticket_creator = ticket_creator
        self._notifier = notifier

    async def handle(self, request: TriageRequest) -> dict:
        logger.info(f"Processing incident triage for: {request.incident_id}")

        # 1. Gọi AI Engine
        response: TriageResponse = await self._ai_client.triage(request)
        
        # 2. Lấy ticket payload và tạo Jira Ticket
        import asyncio
        ticket = response.ticket_payload
        ticket_id = await asyncio.to_thread(
            self._ticket_creator.create_ticket,
            summary=ticket.summary,
            description=ticket.description
        )

        # 3. Gửi Slack Notifier
        action_text = "\n".join([f"- {a.summary}" for a in response.recommended_actions])
        message = (
            f"🚨 *AI Triage Report: {ticket_id}*\n"
            f"*Status:* {response.status} (Confidence: {response.confidence})\n"
            f"*Root Cause:* {response.suspected_root_cause.summary}\n"
            f"*Recommended Actions:*\n{action_text}"
        )
        await asyncio.to_thread(self._notifier.notify, message)

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "environment": config.ENV_NAME,
        }