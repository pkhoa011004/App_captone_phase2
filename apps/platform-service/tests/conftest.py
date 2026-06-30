import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_incident_payload():
    return {
        "correlation_id": "test-corr",
        "tenant_id": "test-tenant",
        "incident_id": "inc-test",
        "environment": "test",
        "received_at": "2026-06-22T08:00:00Z",
        "alert": {
            "alert_id": "alert-test",
            "source": "test-source",
            "service": "test-service",
            "severity": "high",
            "title": "Test Alert",
            "started_at": "2026-06-22T08:00:00Z",
        },
        "metrics": [],
        "logs": [],
        "traces": [],
        "recent_deploys": []
    }

@pytest.fixture
def mock_sqs_queue():
    # Because moto might not be available or setup, we can just mock the sqs client entirely
    # But since the tests use moto, let's provide a basic moto sqs queue
    from moto import mock_aws
    import boto3
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        resp = sqs.create_queue(QueueName="test-queue")
        yield sqs, resp["QueueUrl"]

@pytest.fixture(autouse=True)
def mock_ai_engine():
    from models.incident import TriageResponse, RootCause, RecommendedAction, TicketPayload
    with patch("services.ai_engine_client.AiEngineClient.triage", new_callable=AsyncMock) as mock_triage:
        mock_triage.return_value = TriageResponse(
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
        yield mock_triage

@pytest.fixture
def async_client():
    from httpx import AsyncClient, ASGITransport
    from main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
