import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.checklist import ChecklistResponse
from app.services.checklist_service import get_month_checklist
from app.services.profile_service import get_profile_by_user_id

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.get("/month", response_model=ChecklistResponse)
def get_checklist_for_month(
    month: str | None = Query(default=None),
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    return get_month_checklist(
        db=db,
        profile=profile,
        month=month
    )