import os


class AppConfig:
    """
    SRP: Lớp này chỉ chịu trách nhiệm tải và cung cấp cấu hình ứng dụng.
    """
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    SQS_QUEUE_URL: str = os.getenv("SQS_QUEUE_URL", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    ENV_NAME: str = os.getenv("ENV_NAME", "local")
    APP_NAME: str = "CDO Platform Service"

    # AI Engine
    AI_ENGINE_URL: str = os.getenv("AI_ENGINE_URL", "http://ai-engine:8080")

    # Slack Config
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")

    # Jira Config
    JIRA_URL: str = os.getenv("JIRA_URL", "")
    JIRA_USER: str = os.getenv("JIRA_USER", "")
    JIRA_TOKEN: str = os.getenv("JIRA_TOKEN", "")
    JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "OPS")

# Singleton config instance dùng chung toàn app
config = AppConfig()