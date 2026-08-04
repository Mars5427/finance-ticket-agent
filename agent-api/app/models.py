from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

TicketType = Literal[
    "reimbursement_policy",
    "balance_anomaly",
    "reconciliation_anomaly",
    "unsupported",
]

TicketStatus = Literal["completed", "needs_more_info", "escalated", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketContinueRequest(BaseModel):
    message: str = Field(min_length=1)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("trace"))
    step: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class TicketResult(BaseModel):
    summary: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    needs_human: bool = False
    escalation_reason: str | None = None
    follow_up_question: str | None = None


class TicketResponse(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ticket"))
    title: str
    description: str
    type: TicketType
    status: TicketStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    dialogue_context: list[dict[str, Any]] = Field(default_factory=list)
    result: TicketResult
    trace: list[TraceEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
