from datetime import date
from typing import Optional

from pydantic import BaseModel


class SummaryItem(BaseModel):
    memory_id: str
    component_type: str
    component_name: str

    status: str

    last_service_date: Optional[date]
    service_interval_days: Optional[int]
    next_service_date: Optional[date]

    comment: Optional[str]


class HouseSummaryResponse(BaseModel):
    total_items: int
    status_counts: dict[str, int]
    items: list[SummaryItem]