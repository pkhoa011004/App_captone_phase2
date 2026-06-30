from pydantic import BaseModel, Field
from typing import Any, List, Optional, Literal

class Alert(BaseModel):
    alert_id: str
    source: str
    service: str
    severity: str
    title: str
    description: Optional[str] = None
    started_at: str
    labels: dict[str, Any] = Field(default_factory=dict)

class TriageRequest(BaseModel):
    correlation_id: str
    tenant_id: str
    incident_id: str
    environment: str
    received_at: str
    alert: Alert
    metrics: List[Any] = Field(default_factory=list)
    logs: List[Any] = Field(default_factory=list)
    traces: List[Any] = Field(default_factory=list)
    recent_deploys: List[Any] = Field(default_factory=list)
    ownership: Optional[dict[str, Any]] = None

class RootCause(BaseModel):
    summary: str
    evidence: List[str]

class RecommendedAction(BaseModel):
    type: str
    priority: int
    summary: str
    runbook_ref: Optional[str] = None

class TicketPayload(BaseModel):
    project: str
    summary: str
    description: str
    labels: List[str]
    fields: dict[str, Any]

class TriageResponse(BaseModel):
    incident_id: str
    classification: str
    severity: str
    confidence: float
    status: str
    suspected_root_cause: RootCause
    recommended_actions: List[RecommendedAction]
    ticket_payload: TicketPayload
    suggested_assignee_account_id: Optional[str] = None
    suggestion_reason: Optional[str] = None
    audit_id: str