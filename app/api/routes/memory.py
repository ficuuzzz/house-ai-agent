import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.memory import (
    HouseMemoryResponse,
    HouseMemoryServiceUpdate,
    MemoryInitializeRequest,
)
from app.services.memory_service import (
    create_or_update_memory_records,
    get_memory_by_house_id,
    update_memory_service,
)
from app.services.profile_service import get_profile_by_user_id

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.post("/initialize", response_model=list[HouseMemoryResponse])
def initialize_house_memory(
    request: MemoryInitializeRequest,
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    return create_or_update_memory_records(
        db=db,
        profile=profile,
        items=request.items
    )


@router.get("/", response_model=list[HouseMemoryResponse])
def get_house_memory(
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    if not profile:
        return []

    return get_memory_by_house_id(db, profile.house_id)


@router.patch("/{memory_id}/service", response_model=HouseMemoryResponse)
def update_house_memory_service(
    memory_id: str,
    update_data: HouseMemoryServiceUpdate,
    db: Session = Depends(get_db)
):
    return update_memory_service(
        db=db,
        memory_id=memory_id,
        update_data=update_data
    )