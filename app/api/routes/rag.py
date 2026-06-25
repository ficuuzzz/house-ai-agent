import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rag import RagIndexResponse, RagSearchResponse
from app.services.profile_service import get_profile_by_user_id
from app.services.qdrant_service import (
    index_knowledge_base,
    search_relevant_knowledge_base,
)
from app.services.specialist_service import analyze_specialist_recommendation

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.post("/reindex", response_model=RagIndexResponse)
def reindex_knowledge_base():
    return index_knowledge_base()


@router.get("/search", response_model=RagSearchResponse)
def search_knowledge_base(
    query: str = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    items = search_relevant_knowledge_base(
        query=query,
        profile=profile,
        limit=limit
    )

    specialist_decision = analyze_specialist_recommendation(
        query=query,
        items=items
    )

    return RagSearchResponse(
        query=query,
        total_items=len(items),
        recommend_specialist=specialist_decision["recommend_specialist"],
        specialist_reason=specialist_decision["specialist_reason"],
        items=items
    )