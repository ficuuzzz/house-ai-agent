
from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.db.session import Base


class HouseProfile(Base):
    __tablename__ = "house_profiles"

    house_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, unique=True)

    house_type = Column(String, nullable=False)
    region = Column(String, nullable=False)
    climate_zone = Column(String, nullable=False)

    water_source = Column(String, nullable=False)
    heating_type = Column(String, nullable=False)

    has_gas = Column(Boolean, nullable=False)
    has_generator = Column(Boolean, nullable=False)
    has_pool = Column(Boolean, nullable=False)
    has_basement = Column(Boolean, nullable=False)
    has_plot = Column(Boolean, nullable=False)
    has_fireplace = Column(Boolean, nullable=False)

    involvement_level = Column(String, nullable=False)


class HouseMemory(Base):
    __tablename__ = "house_memory"

    __table_args__ = (
        UniqueConstraint("house_id", "component_type", name="uq_house_component"),
    )

    memory_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    house_id = Column(
        String,
        ForeignKey("house_profiles.house_id"),
        nullable=False
    )

    component_type = Column(String, nullable=False)
    component_name = Column(String, nullable=False)

    last_service_date = Column(Date, nullable=True)
    service_interval_days = Column(Integer, nullable=True)
    next_service_date = Column(Date, nullable=True)

    status = Column(String, nullable=False, default="no_data")

    last_check_result = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)

class AgentSession(Base):
    __tablename__ = "agent_sessions"

    session_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    user_id = Column(String, nullable=False, unique=True)

    current_scenario = Column(String, nullable=False, default="idle")
    current_step = Column(String, nullable=True)

    draft_data = Column(JSON, nullable=False, default=dict)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )