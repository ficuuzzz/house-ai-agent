import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.summary import HouseSummaryResponse
from app.services.profile_service import get_profile_by_user_id
from app.services.summary_service import get_house_summary

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.get("/house", response_model=HouseSummaryResponse)
def get_my_house_summary(
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    return get_house_summary(
        db=db,
        profile=profile
    )