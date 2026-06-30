import logging
import httpx
import uuid
from interfaces.ticket_creator import ITicketCreator
from config import config

logger = logging.getLogger(__name__)


class JiraTicketCreator(ITicketCreator):
    """
    SRP: Chỉ chịu trách nhiệm tạo ticket trên Jira.
    """

    def __init__(self):
        self.jira_url = config.JIRA_URL
        self.jira_user = config.JIRA_USER
        self.jira_token = config.JIRA_TOKEN
        self.jira_project = config.JIRA_PROJECT_KEY

    def create_ticket(self, summary: str, description: str) -> str:
        if not all([self.jira_url, self.jira_user, self.jira_token]):
            ticket_id = f"{self.jira_project}-{uuid.uuid4().hex[:6]}"
            logger.warning(f"Jira credentials not fully configured. Using mock ticket ID: {ticket_id}")
            return ticket_id

        logger.info(f"Creating Jira ticket: {summary}")
        url = f"{self.jira_url.rstrip('/')}/rest/api/2/issue"
        auth = (self.jira_user, self.jira_token)
        payload = {
            "fields": {
                "project": {"key": self.jira_project},
                "summary": summary,
                "description": description,
                "issuetype": {"name": "Task"}
            }
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, auth=auth)
                response.raise_for_status()
                return response.json().get("key", f"{self.jira_project}-UNKNOWN")
        except Exception as e:
            logger.error(f"Failed to create Jira ticket: {e}")
            return f"{self.jira_project}-ERROR-{uuid.uuid4().hex[:4]}"