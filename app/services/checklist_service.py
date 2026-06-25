from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import HouseProfile
from app.schemas.checklist import ChecklistItemResponse, ChecklistResponse
from app.services.kb_loader import load_knowledge_base_from_excel
from app.utils.conditions import is_kb_item_relevant
from app.utils.date_utils import get_season_by_month_number


MONTH_ALIASES = {
    "january": "january",
    "jan": "january",
    "январь": "january",
    "января": "january",

    "february": "february",
    "feb": "february",
    "февраль": "february",
    "февраля": "february",

    "march": "march",
    "mar": "march",
    "март": "march",
    "марта": "march",

    "april": "april",
    "apr": "april",
    "апрель": "april",
    "апреля": "april",

    "may": "may",
    "май": "may",
    "мая": "may",

    "june": "june",
    "jun": "june",
    "июнь": "june",
    "июня": "june",

    "july": "july",
    "jul": "july",
    "июль": "july",
    "июля": "july",

    "august": "august",
    "aug": "august",
    "август": "august",
    "августа": "august",

    "september": "september",
    "sep": "september",
    "сентябрь": "september",
    "сентября": "september",

    "october": "october",
    "oct": "october",
    "октябрь": "october",
    "октября": "october",

    "november": "november",
    "nov": "november",
    "ноябрь": "november",
    "ноября": "november",

    "december": "december",
    "dec": "december",
    "декабрь": "december",
    "декабря": "december",

    "this month": "__current__",
    "current month": "__current__",
    "текущий месяц": "__current__",
    "этот месяц": "__current__",
    "в этом месяце": "__current__",
    "сейчас": "__current__",
}


MONTH_BY_NUMBER = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}

MONTH_USER_NAMES = {
    "january": "январь",
    "february": "февраль",
    "march": "март",
    "april": "апрель",
    "may": "май",
    "june": "июнь",
    "july": "июль",
    "august": "август",
    "september": "сентябрь",
    "october": "октябрь",
    "november": "ноябрь",
    "december": "декабрь",
}


def get_month_user_name(month: str | None) -> str:
    normalized_month = normalize_month(month)

    return MONTH_USER_NAMES.get(normalized_month, normalized_month)

MONTH_NUMBER_BY_NAME = {
    value: key
    for key, value in MONTH_BY_NUMBER.items()
}


SEASON_ALIASES = {
    "winter": "winter",
    "зима": "winter",

    "spring": "spring",
    "весна": "spring",

    "summer": "summer",
    "лето": "summer",

    "autumn": "autumn",
    "fall": "autumn",
    "осень": "autumn",
}


PRIORITY_ORDER = {
    "высокий": 0,
    "high": 0,
    "средний": 1,
    "medium": 1,
    "низкий": 2,
    "low": 2,
}


def normalize_month(value: str | None) -> str:
    if value is None:
        return MONTH_BY_NUMBER[date.today().month]

    text = str(value).strip().lower()

    month = MONTH_ALIASES.get(text, text)

    if month == "__current__":
        return MONTH_BY_NUMBER[date.today().month]

    if month not in MONTH_NUMBER_BY_NAME:
        return MONTH_BY_NUMBER[date.today().month]

    return month

def get_season_for_month(month: str) -> str:
    month_number = MONTH_NUMBER_BY_NAME.get(month)

    if month_number is None:
        return get_season_by_month_number(date.today().month)

    return get_season_by_month_number(month_number)


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def normalize_season(value: str | None) -> str:
    text = normalize_text(value)

    return SEASON_ALIASES.get(text, text)


def is_month_relevant(kb_month: str | None, target_month: str) -> bool:
    kb_month_normalized = normalize_month(kb_month)

    return kb_month_normalized == target_month


def is_season_relevant(kb_season: str | None, target_season: str) -> bool:
    kb_season_normalized = normalize_season(kb_season)

    if kb_season_normalized in ["", "all", "любой", "все"]:
        return True

    return kb_season_normalized == target_season


def get_priority_sort_value(priority: str | None) -> int:
    normalized_priority = normalize_text(priority)

    return PRIORITY_ORDER.get(normalized_priority, 99)


def get_month_checklist(
    db: Session,
    profile: HouseProfile | None,
    month: str | None = None
) -> ChecklistResponse:
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="HouseProfile not found"
        )

    target_month = normalize_month(month)
    target_season = get_season_for_month(target_month)

    try:
        kb_items = load_knowledge_base_from_excel()
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    relevant_items = []

    for item in kb_items:
        if not is_month_relevant(item.get("month"), target_month):
            continue

        if not is_season_relevant(item.get("season"), target_season):
            continue

        if not is_kb_item_relevant(item.get("conditions", []), profile):
            continue

        relevant_items.append(item)

    relevant_items.sort(
        key=lambda item: get_priority_sort_value(item.get("priority"))
    )

    response_items = [
        ChecklistItemResponse(
            kb_id=str(item.get("kb_id")),
            month=item.get("month"),
            season=item.get("season"),
            category=item.get("category"),
            subcategory=item.get("subcategory"),
            title=str(item.get("title")),
            task_description=item.get("task_description"),
            instructions=item.get("instructions"),
            purpose=item.get("purpose"),
            conditions=item.get("conditions", []),
            can_do_self=item.get("can_do_self"),
            priority=item.get("priority"),
            source_url=item.get("source_url"),
        )
        for item in relevant_items
    ]

    return ChecklistResponse(
        month=target_month,
        season=target_season,
        total_items=len(response_items),
        items=response_items
    )