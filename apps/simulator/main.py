from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from routers import jira, slack, health, dumbproxy

app = FastAPI(title="Mock Services for Jira, Slack and Telemetry Simulator")

# Include the routers
app.include_router(health.router)
app.include_router(jira.router)
app.include_router(slack.router)
app.include_router(dumbproxy.router)

@app.get("/metrics")
async def metrics():
    """
    Expose metrics cho Prometheus quét (thay thế cho start_http_server ở code cũ)
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
