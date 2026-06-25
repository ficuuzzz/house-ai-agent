import re
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComponentType(str, Enum):
    generator = "generator"
    boiler = "boiler"
    pump = "pump"
    water_filter = "water_filter"
    septic = "septic"
    electrical_panel = "electrical_panel"
    ventilation = "ventilation"
    roof = "roof"
    gutter = "gutter"
    basement = "basement"
    drainage = "drainage"
    pool = "pool"
    fireplace = "fireplace"
    chimney = "chimney"


class MemoryStatus(str, Enum):
    ok = "ok"
    soon = "soon"
    overdue = "overdue"
    no_data = "no_data"


class HouseMemoryCreateItem(BaseModel):
    component_type: str = Field(..., min_length=2, max_length=64)
    component_name: Optional[str] = None

    last_service_date: Optional[date] = None
    service_interval_days: Optional[int] = Field(default=None, ge=1)

    comment: Optional[str] = None

    @field_validator("component_type")
    @classmethod
    def validate_component_type(cls, value: str) -> str:
        normalized = value.strip().lower()

        if not re.fullmatch(r"[a-z0-9_]+", normalized):
            raise ValueError(
                "component_type must contain only latin letters, digits and underscores"
            )

        return normalized

class MemoryInitializeRequest(BaseModel):
    items: list[HouseMemoryCreateItem]


class HouseMemoryServiceUpdate(BaseModel):
    last_service_date: date
    service_interval_days: Optional[int] = Field(default=None, ge=1)
    comment: Optional[str] = None


class HouseMemoryResponse(BaseModel):
    memory_id: str
    house_id: str

    component_type: str
    component_name: str

    last_service_date: Optional[date]
    service_interval_days: Optional[int]
    next_service_date: Optional[date]

    status: str

    last_check_result: Optional[str]
    comment: Optional[str]

    model_config = ConfigDict(from_attributes=True)