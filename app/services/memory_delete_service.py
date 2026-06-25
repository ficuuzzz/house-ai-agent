import re

from sqlalchemy.orm import Session

from app.db.models import HouseMemory, HouseProfile
from app.services.gigachat_memory_extraction_service import normalize_component_type


def normalize_text(value: str | None) -> str:
    return str(value or "").lower().replace("ё", "е").strip()


def is_memory_delete_text(message: str) -> bool:
    text = normalize_text(message)

    delete_patterns = [
        "удали",
        "удалить",
        "убери",
        "убрать",
        "сотри",
        "стереть",
        "исключи",
        "исключить",
    ]

    memory_context_patterns = [
        "из памяти",
        "память дома",
        "housememory",
        "house memory",
        "из обслуживаемых",
        "обслуживаемый объект",
        "обслуживаемые объекты",
        "из объектов",
        "из компонентов",
    ]

    if "профил" in text:
        return False

    has_delete_intent = any(pattern in text for pattern in delete_patterns)
    has_memory_context = any(pattern in text for pattern in memory_context_patterns)

    return has_delete_intent and has_memory_context


def extract_memory_delete_target(message: str) -> str | None:
    text = normalize_text(message)

    if not text:
        return None

    cleaned = text

    phrases_to_remove = [
        "пожалуйста",
        "из памяти дома",
        "из памяти",
        "память дома",
        "housememory",
        "house memory",
        "из обслуживаемых объектов",
        "из обслуживаемых",
        "обслуживаемый объект",
        "обслуживаемые объекты",
        "из объектов",
        "из компонентов",
        "объект",
        "компонент",
        "дома",
        "дом",
    ]

    for phrase in phrases_to_remove:
        cleaned = cleaned.replace(phrase, " ")

    cleaned = re.sub(
        r"\b(удали|удалить|убери|убрать|сотри|стереть|исключи|исключить)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\b(из|с|со|в|во)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;!?")

    if not cleaned:
        return None

    too_general = {
        "память",
        "обслуживание",
        "данные",
        "информация",
        "все",
        "всё",
    }

    if cleaned in too_general:
        return None

    if len(cleaned) > 120:
        return None

    return cleaned


def find_memory_records_for_delete(
    db: Session,
    profile: HouseProfile,
    target: str,
) -> list[HouseMemory]:
    target_normalized = normalize_text(target)
    target_component_type = normalize_component_type(target)

    records = (
        db.query(HouseMemory)
        .filter(HouseMemory.house_id == profile.house_id)
        .all()
    )

    matches_by_id = {}

    for record in records:
        name_normalized = normalize_text(record.component_name)
        type_normalized = normalize_text(record.component_type)

        is_match = False

        if target_component_type and type_normalized == target_component_type:
            is_match = True

        if target_normalized == name_normalized:
            is_match = True

        if target_normalized and target_normalized in name_normalized:
            is_match = True

        if name_normalized and name_normalized in target_normalized:
            is_match = True

        if target_component_type and target_component_type in type_normalized:
            is_match = True

        if is_match:
            matches_by_id[record.memory_id] = record

    return list(matches_by_id.values())


def build_memory_delete_confirmation_answer(records: list[HouseMemory]) -> str:
    lines = [
        "Я понял так:",
        "",
        "Нужно удалить из памяти дома:",
    ]

    for record in records:
        lines.append(f"- {record.component_name}")

    lines.extend(["", "Удалить?"])

    return "\n".join(lines)


def build_memory_delete_not_found_answer(target: str) -> str:
    return (
        f"Я не нашёл в памяти дома объект «{target}».\n\n"
        "Можно посмотреть текущую память командой: «покажи память дома»."
    )


def build_memory_delete_ambiguous_answer(records: list[HouseMemory]) -> str:
    lines = [
        "Я нашёл несколько похожих объектов в памяти дома:",
        "",
    ]

    for index, record in enumerate(records, start=1):
        lines.append(f"{index}. {record.component_name}")

    lines.extend(
        [
            "",
            "Напишите точнее, какой объект нужно удалить.",
            "Например: «удали насос скважины из памяти».",
        ]
    )

    return "\n".join(lines)