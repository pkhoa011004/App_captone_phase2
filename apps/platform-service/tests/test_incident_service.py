import pytest
from unittest.mock import MagicMock, AsyncMock
from models.incident import TriageRequest, TriageResponse, RootCause, RecommendedAction, TicketPayload
from services.incident_service import IncidentService

def make_service(ticket_id: str = "OPS-42"):
    ai_client = AsyncMock()
    # Mock AI response
    ai_client.triage.return_value = TriageResponse(
        incident_id="inc-test",
        classification="latency",
        severity="high",
        confidence=0.9,
        status="DIAGNOSED",
        suspected_root_cause=RootCause(summary="Test root cause", evidence=[]),
        recommended_actions=[RecommendedAction(type="HUMAN_REVIEW", priority=1, summary="Action 1")],
        ticket_payload=TicketPayload(
            project="OPS",
            summary="Test Summary",
            description="Test Description",
            labels=[],
            fields={}
        ),
        audit_id="audit-1"
    )

    ticket_creator = MagicMock()
    ticket_creator.create_ticket.return_value = ticket_id
    notifier = MagicMock()

    service = IncidentService(ai_client=ai_client, ticket_creator=ticket_creator, notifier=notifier)
    return service, ai_client, ticket_creator, notifier

def make_report(**kwargs) -> TriageRequest:
    defaults = {
        "correlation_id": "test-corr",
        "tenant_id": "test-tenant",
        "incident_id": "inc-test",
        "environment": "test",
        "received_at": "2026-06-22T08:00:00Z",
        "alert": {
            "alert_id": "alert-test",
            "source": "test",
            "service": "test",
            "severity": "high",
            "title": "Test Alert",
            "started_at": "2026-06-22T08:00:00Z"
        }
    }
    return TriageRequest(**{**defaults, **kwargs})

pytestmark = pytest.mark.anyio

class TestIncidentServiceHandle:
    async def test_returns_success_status(self):
        service, _, _, _ = make_service()
        result = await service.handle(make_report())
        assert result["status"] == "success"

    async def test_calls_ai_engine(self):
        service, ai_mock, _, _ = make_service()
        req = make_report()
        await service.handle(req)
        ai_mock.triage.assert_called_once_with(req)

    async def test_returns_ticket_id_from_creator(self):
        service, _, _, _ = make_service(ticket_id="OPS-777")
        result = await service.handle(make_report())
        assert result["ticket_id"] == "OPS-777"

    async def test_creates_ticket_with_correct_summary(self):
        service, _, ticket_mock, _ = make_service()
        await service.handle(make_report(incident_id="INC-999"))
        ticket_mock.create_ticket.assert_called_once()
        call_kwargs = ticket_mock.create_ticket.call_args.kwargs
        assert "Test Summary" in call_kwargs["summary"]

    async def test_creates_ticket_with_root_cause_in_description(self):
        service, _, ticket_mock, _ = make_service()
        await service.handle(make_report())
        call_kwargs = ticket_mock.create_ticket.call_args.kwargs
        assert "Test Description" in call_kwargs["description"]

    async def test_sends_notification_once(self):
        service, _, _, notifier_mock = make_service()
        await service.handle(make_report())
        notifier_mock.notify.assert_called_once()