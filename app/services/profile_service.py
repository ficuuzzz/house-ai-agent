from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import HouseProfile
from app.schemas.profile import HouseProfileCreate


def get_profile_by_user_id(db: Session, user_id: str):
    return (
        db.query(HouseProfile)
        .filter(HouseProfile.user_id == user_id)
        .first()
    )


def create_profile(
    db: Session,
    profile_data: HouseProfileCreate,
    user_id: str
):
    existing_profile = get_profile_by_user_id(db, user_id)

    if existing_profile:
        raise HTTPException(
            status_code=400,
            detail="HouseProfile for this user already exists"
        )

    profile = HouseProfile(
        user_id=user_id,
        **profile_data.model_dump()
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile