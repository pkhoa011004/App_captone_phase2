from services.incident_service import IncidentService
from services.jira_ticket_creator import JiraTicketCreator
from services.slack_notifier import SlackNotifier


from services.ai_engine_client import AiEngineClient

def get_incident_service() -> IncidentService:
    return IncidentService(
        ai_client=AiEngineClient(),
        ticket_creator=JiraTicketCreator(),
        notifier=SlackNotifier(),
    )