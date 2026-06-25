import re

from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.services.checklist_service import normalize_month, normalize_season
from app.db.models import HouseProfile
from app.services.embedding_service import get_embedding, get_embedding_size
from app.services.kb_loader import load_knowledge_base_from_excel
from app.utils.conditions import is_kb_item_relevant



BASE_DIR = Path(__file__).resolve().parents[2]
QDRANT_PATH = BASE_DIR / "data" / "qdrant"

COLLECTION_NAME = "knowledge_base"


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(path=str(QDRANT_PATH))


def build_kb_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("title"),
        item.get("task_description"),
        item.get("instructions"),
        item.get("purpose"),
        item.get("category"),
        item.get("subcategory"),
    ]

    return "\n".join(str(part) for part in parts if part)


def recreate_kb_collection(client: QdrantClient):
    vector_size = get_embedding_size()

    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE
        )
    )


def index_knowledge_base() -> dict:
    client = get_qdrant_client()
    kb_items = load_knowledge_base_from_excel()

    recreate_kb_collection(client)

    points = []

    for index, item in enumerate(kb_items):
        text = build_kb_text(item)
        vector = get_embedding(text)

        payload = {
            **item,
            "embedding_text": text,
        }

        points.append(
            PointStruct(
                id=index,
                vector=vector,
                payload=payload
            )
        )

    if points:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

    return {
        "collection_name": COLLECTION_NAME,
        "indexed_items": len(points)
    }


def search_knowledge_base_raw(
    query: str,
    limit: int = 10
):
    client = get_qdrant_client()
    query_vector = get_embedding(query)

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        with_payload=True
    )

    return response.points

def normalize_for_search(text: str | None) -> str:
    if text is None:
        return ""

    return str(text).lower().replace("ё", "е")


def extract_query_words(query: str) -> set[str]:
    normalized_query = normalize_for_search(query)

    words = re.findall(r"[а-яa-z0-9]+", normalized_query)

    stop_words = {
        "что",
        "как",
        "если",
        "почему",
        "где",
        "когда",
        "делать",
        "идет",
        "идёт",
        "надо",
        "нужно",
        "при",
        "из",
        "в",
        "на",
        "и",
        "или",
    }

    return {
        word
        for word in words
        if len(word) >= 3 and word not in stop_words
    }


def calculate_rag_bonus(
    query: str,
    payload: dict,
    month: str | None = None,
    season: str | None = None,
) -> float:
    query_words = extract_query_words(query)

    searchable_text = normalize_for_search(
        " ".join(
            str(payload.get(field) or "")
            for field in [
                "title",
                "category",
                "subcategory",
                "task_description",
                "instructions",
                "purpose",
            ]
        )
    )

    bonus = 0.0

    for word in query_words:
        if word in searchable_text:
            bonus += 0.05

    query_normalized = normalize_for_search(query)
    category = normalize_for_search(payload.get("category"))
    title = normalize_for_search(payload.get("title"))
    subcategory = normalize_for_search(payload.get("subcategory"))

    water_problem_words = [
        "вода",
        "воды",
        "водоснабжение",
        "напор",
        "насос",
        "скважина",
        "рывками",
        "фильтр",
        "труба",
        "трубы",
    ]

    if any(word in query_normalized for word in water_problem_words):
        if "водоснабжение" in category:
            bonus += 0.25

        if "насос" in title or "скважин" in title or "водоснабжен" in title:
            bonus += 0.15

        if "насос" in subcategory or "скважин" in subcategory:
            bonus += 0.1

    if month:
        target_month = normalize_month(month)
        item_month_raw = payload.get("month")

        if item_month_raw:
            item_month = normalize_month(item_month_raw)

            if item_month == target_month:
                bonus += 0.12

    if season:
        target_season = normalize_season(season)
        item_season_raw = payload.get("season")

        if item_season_raw:
            item_season = normalize_season(item_season_raw)

            if item_season == target_season:
                bonus += 0.08
            elif item_season not in ["", "all", "любой", "все"]:
                bonus -= 0.04

    return bonus

def search_relevant_knowledge_base(
    query: str,
    profile: HouseProfile,
    limit: int = 5,
    raw_limit: int = 20,
    month: str | None = None,
    season: str | None = None,
) -> list[dict]:
    raw_results = search_knowledge_base_raw(
        query=query,
        limit=raw_limit
    )

    relevant_results = []

    for result in raw_results:
        payload = result.payload or {}
        conditions = payload.get("conditions", [])

        if not is_kb_item_relevant(conditions, profile):
            continue

        semantic_score = float(result.score)
        rerank_bonus = calculate_rag_bonus(
            query=query,
            payload=payload,
            month=month,
            season=season,
        )
        final_score = semantic_score + rerank_bonus

        relevant_results.append(
            {
                "score": final_score,
                "semantic_score": semantic_score,
                "rerank_bonus": rerank_bonus,
                "kb_id": payload.get("kb_id"),
                "month": payload.get("month"),
                "season": payload.get("season"),
                "title": payload.get("title"),
                "category": payload.get("category"),
                "subcategory": payload.get("subcategory"),
                "task_description": payload.get("task_description"),
                "instructions": payload.get("instructions"),
                "purpose": payload.get("purpose"),
                "conditions": conditions,
                "can_do_self": payload.get("can_do_self"),
                "priority": payload.get("priority"),
                "source_url": payload.get("source_url"),
            }
        )

    relevant_results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return relevant_results[:limit]