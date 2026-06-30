import logging
import httpx
from interfaces.notifier import INotifier
from config import config

logger = logging.getLogger(__name__)


class SlackNotifier(INotifier):
    """
    SRP: Chỉ chịu trách nhiệm gửi thông báo qua Slack.
    """

    def __init__(self):
        self.webhook_url = config.SLACK_WEBHOOK_URL

    def notify(self, message: str) -> None:
        if not self.webhook_url:
            logger.warning(f"SLACK_WEBHOOK_URL not configured. Skipping Slack notification: {message}")
            return

        logger.info("Sending Slack notification.")
        try:
            # We use httpx.post synchronously because INotifier.notify is not async. 
            # In a fully async system, we should make INotifier.notify async.
            with httpx.Client() as client:
                response = client.post(self.webhook_url, json={"text": message})
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")