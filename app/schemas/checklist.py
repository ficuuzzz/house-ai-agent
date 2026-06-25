from typing import Optional

from pydantic import BaseModel


class ChecklistItemResponse(BaseModel):
    kb_id: str
    month: Optional[str]
    season: Optional[str]

    category: Optional[str]
    subcategory: Optional[str]

    title: str
    task_description: Optional[str]
    instructions: Optional[str]
    purpose: Optional[str]

    conditions: list[str]

    can_do_self: Optional[str]
    priority: Optional[str]
    source_url: Optional[str]


class ChecklistResponse(BaseModel):
    month: str
    season: str
    total_items: int
    items: list[ChecklistItemResponse]