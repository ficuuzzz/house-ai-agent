from datetime import date
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.rag import RagSearchItem


class AgentAskRequest(BaseModel):
    message: str


class AgentMemoryItem(BaseModel):
    memory_id: str
    component_type: str
    component_name: str

    status: str

    last_service_date: Optional[date]
    service_interval_days: Optional[int]
    next_service_date: Optional[date]

    comment: Optional[str]


class AgentAskResponse(BaseModel):
    scenario: str
    answer: str

    recommend_specialist: bool = False
    specialist_reason: Optional[str] = None

    memory_context: list[AgentMemoryItem] = []
    rag_items: list[RagSearchItem] = []

    checklist: Optional[dict[str, Any]] = None
    summary: Optional[dict[str, Any]] = None
    profile: Optional[dict[str, Any]] = None

    action_required: Optional[str] = None