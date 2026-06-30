"""
tests/test_api.py

Integration tests cho FastAPI HTTP endpoints.
Dùng httpx.AsyncClient với ASGI transport — không cần server thật.
"""
import pytest
from unittest.mock import patch


pytestmark = pytest.mark.anyio


class TestHealthEndpoint:

    async def test_health_returns_200(self, async_client):
        response = await async_client.get("/health")
        assert response.status_code == 200

    async def test_health_returns_ok_status(self, async_client):
        response = await async_client.get("/health")
        assert response.json()["status"] == "ok"

    async def test_health_returns_environment(self, async_client):
        response = await async_client.get("/health")
        assert "environment" in response.json()


class TestNotifyEndpoint:

    async def test_notify_returns_200(self, async_client, mock_incident_payload):
        with patch("services.jira_ticket_creator.JiraTicketCreator.create_ticket", return_value="OPS-1"), \
             patch("services.slack_notifier.SlackNotifier.notify"):
            response = await async_client.post("/api/v1/notify", json=mock_incident_payload)
        assert response.status_code == 200

    async def test_notify_returns_ticket_id(self, async_client, mock_incident_payload):
        with patch("services.jira_ticket_creator.JiraTicketCreator.create_ticket", return_value="OPS-42"), \
             patch("services.slack_notifier.SlackNotifier.notify"):
            response = await async_client.post("/api/v1/notify", json=mock_incident_payload)
        assert response.json()["ticket_id"] == "OPS-42"

    async def test_notify_returns_success_status(self, async_client, mock_incident_payload):
        with patch("services.jira_ticket_creator.JiraTicketCreator.create_ticket", return_value="OPS-1"), \
             patch("services.slack_notifier.SlackNotifier.notify"):
            response = await async_client.post("/api/v1/notify", json=mock_incident_payload)
        assert response.json()["status"] == "success"

    async def test_notify_missing_field_returns_422(self, async_client):
        """Pydantic validation: thiếu field bắt buộc → 422 Unprocessable Entity."""
        response = await async_client.post("/api/v1/notify", json={"incident_id": "INC-1"})
        assert response.status_code == 422

    async def test_notify_calls_jira_once(self, async_client, mock_incident_payload):
        with patch("services.jira_ticket_creator.JiraTicketCreator.create_ticket", return_value="OPS-1") as mock_jira, \
             patch("services.slack_notifier.SlackNotifier.notify"):
            await async_client.post("/api/v1/notify", json=mock_incident_payload)
        mock_jira.assert_called_once()

    async def test_notify_calls_slack_once(self, async_client, mock_incident_payload):
        with patch("services.jira_ticket_creator.JiraTicketCreator.create_ticket", return_value="OPS-1"), \
             patch("services.slack_notifier.SlackNotifier.notify") as mock_slack:
            await async_client.post("/api/v1/notify", json=mock_incident_payload)
        mock_slack.assert_called_once()