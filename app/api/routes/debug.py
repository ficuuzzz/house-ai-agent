import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.profile_service import get_profile_by_user_id
from app.utils.conditions import is_kb_item_relevant, profile_to_conditions

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.get("/profile-conditions")
def get_profile_conditions(
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    if not profile:
        return {"error": "HouseProfile not found"}

    return {
        "conditions": sorted(profile_to_conditions(profile))
    }


@router.get("/check-condition")
def check_condition(
    condition: str,
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    if not profile:
        return {"error": "HouseProfile not found"}

    return {
        "condition": condition,
        "is_relevant": is_kb_item_relevant([condition], profile)
    }