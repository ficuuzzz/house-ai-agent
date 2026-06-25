import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.profile import HouseProfileCreate, HouseProfileResponse
from app.services.profile_service import create_profile, get_profile_by_user_id

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.post("/", response_model=HouseProfileResponse)
def create_house_profile(
    profile_data: HouseProfileCreate,
    db: Session = Depends(get_db)
):
    return create_profile(
        db=db,
        profile_data=profile_data,
        user_id=DEMO_USER_ID
    )


@router.get("/me", response_model=HouseProfileResponse)
def get_my_house_profile(
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="HouseProfile not found"
        )

    return profile