import sys
import os
from pathlib import Path

# Add platform-service path to sys.path
sys.path.append(str(Path("d:/GitHub/App_captone_phase2/Xbrain_fake_data/apps/platform-service")))

import datetime
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc
    sys.modules["datetime"].UTC = datetime.timezone.utc

# Setup logging
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Load python-dotenv manually to support loading from .env
def load_dotenv(dotenv_path):
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

# Try to load .env from platform-service
dotenv_path = Path("d:/GitHub/App_captone_phase2/Xbrain_fake_data/apps/platform-service/.env")
load_dotenv(dotenv_path)

from services.slack_notifier import SlackNotifier
from services.jira_ticket_creator import JiraTicketCreator
from models.incident import TriageRequest, TriageResponse, RootCause, RecommendedAction, TicketPayload, Alert
from services.incident_service import IncidentService
from config import config

# Update config singleton manually in case os.environ was updated
config.SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", config.SLACK_WEBHOOK_URL)
config.JIRA_URL = os.environ.get("JIRA_URL", config.JIRA_URL)
config.JIRA_USER = os.environ.get("JIRA_USER", config.JIRA_USER)
config.JIRA_TOKEN = os.environ.get("JIRA_TOKEN", config.JIRA_TOKEN)

print("=== Slack & Jira Integration Dispatcher Test ===")
print("SLACK_WEBHOOK_URL:", config.SLACK_WEBHOOK_URL or "(Not configured)")
print("JIRA_URL         :", config.JIRA_URL or "(Not configured)")
print("JIRA_USER        :", config.JIRA_USER or "(Not configured)")
print("JIRA_TOKEN       :", config.JIRA_TOKEN or "(Not configured)")

# Build a mock IncidentService where AI Engine is mocked to return the Scenario 3 NullPointerException diagnosis
class MockAiClient:
    async def triage(self, request: TriageRequest) -> TriageResponse:
        print("\n[AI Client Mock] Simulating AI Engine analysis of Scenario 3 Evidence Bundle...")
        return TriageResponse(
            incident_id=request.incident_id,
            classification="code_bug",
            severity="critical",
            confidence=0.95,
            status="DIAGNOSED",
            suspected_root_cause=RootCause(
                summary="Bug in PromoHandler.java:42 (NullPointerException) after deployment v1.4.3",
                evidence=["NullPointerException in logs", "http_5xx_rate spike to 18.5 req/sec", "Recent deploy of version v1.4.3"]
            ),
            recommended_actions=[
                RecommendedAction(type="ROLLBACK", priority=1, summary="Rollback book-service to version v1.4.2"),
                RecommendedAction(type="CODE_FIX", priority=2, summary="Check PromoHandler.java at line 42 for potential null references")
            ],
            ticket_payload=TicketPayload(
                project=config.JIRA_PROJECT_KEY,
                summary=f"[Triage Hub] [CRITICAL] http_5xx_high error on {request.alert.service}",
                description=(
                    f"Incident ID: {request.incident_id}\n"
                    f"Correlation ID: {request.correlation_id}\n"
                    f"Service: {request.alert.service}\n\n"
                    f"Suspected Root Cause:\n"
                    f"NullPointerException in PromoHandler.java:42 triggered by user applying coupon code.\n\n"
                    f"Evidence gathered in window:\n"
                    f"- Logs: java.lang.NullPointerException at com.bookhub.promo.PromoHandler.applyPromoCode(PromoHandler.java:42)\n"
                    f"- Metric http_5xx_rate spiked to 18.5 req/sec\n"
                    f"- K8s events: Readiness probe failed with status 500\n"
                    f"- Recent Deploy: version v1.4.3 deployed at 2026-06-29T12:55:00Z\n\n"
                    f"Recommended Action:\n"
                    f"- Revert book-service deployment to version v1.4.2"
                ),
                labels=["cdo-triage", "api-5xx"],
                fields={}
            ),
            audit_id="audit-sc3-001"
        )

# Construct Service
ai_client = MockAiClient()
ticket_creator = JiraTicketCreator()
notifier = SlackNotifier()
incident_service = IncidentService(ai_client=ai_client, ticket_creator=ticket_creator, notifier=notifier)

# Mock input TriageRequest (Scenario 3)
alert = Alert(
    alert_id="alert-book-service-5xx-spike",
    source="prometheus",
    service="book-service",
    severity="critical",
    title="High 5xx rate on book-service after deployment",
    started_at="2026-06-29T13:00:00Z"
)
request = TriageRequest(
    correlation_id="corr-tenant-a-prod-book-service-202606291300",
    tenant_id="tenant-a",
    incident_id="inc-tenant-a-prod-book-service-202606291300",
    environment="prod",
    received_at="2026-06-29T13:00:05Z",
    alert=alert
)

# Run
import asyncio
async def main():
    print("\nRunning Triage process flow...")
    result = await incident_service.handle(request)
    print("\n=== Dispatch Results ===")
    print("Status:", result["status"])
    print("Ticket ID:", result["ticket_id"])

if __name__ == "__main__":
    asyncio.run(main())
