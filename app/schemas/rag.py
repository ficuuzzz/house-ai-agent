from typing import Optional

from pydantic import BaseModel


class RagIndexResponse(BaseModel):
    collection_name: str
    indexed_items: int


class RagSearchItem(BaseModel):
    score: float
    semantic_score: Optional[float] = None
    rerank_bonus: Optional[float] = None

    kb_id: Optional[str]
    month: Optional[str] = None
    season: Optional[str] = None
    title: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]

    task_description: Optional[str]
    instructions: Optional[str]
    purpose: Optional[str]

    conditions: list[str]

    can_do_self: Optional[str]
    priority: Optional[str]
    source_url: Optional[str]


class RagSearchResponse(BaseModel):
    query: str
    total_items: int
    recommend_specialist: bool
    specialist_reason: Optional[str] = None
    items: list[RagSearchItem]
