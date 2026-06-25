import json
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import HouseMemory, HouseProfile
from app.services.gigachat_memory_extraction_service import (
    normalize_component_type,
)
from app.services.gigachat_service import generate_answer


TARGET_WORD_NORMALIZATION = {
    "генератору": "генератор",
    "генератора": "генератор",
    "генератором": "генератор",

    "септику": "септик",
    "септика": "септик",
    "септиком": "септик",

    "насосу": "насос",
    "насоса": "насос",
    "насосом": "насос",

    "фильтру": "фильтр",
    "фильтра": "фильтр",
    "фильтром": "фильтр",

    "котлу": "котел",
    "котла": "котел",
    "котлом": "котел",

    "бойлеру": "бойлер",
    "бойлера": "бойлер",

    "холодильнику": "холодильник",
    "холодильника": "холодильник",
    "холодильником": "холодильник",

    "бассейну": "бассейн",
    "бассейна": "бассейн",

    "камину": "камин",
    "камина": "камин",

    "подвалу": "подвал",
    "подвала": "подвал",
}


def normalize_text(value: Any) -> str:
    return str(value or "").lower().replace("ё", "е").strip()


def normalize_target_text(value: Any) -> str:
    text = normalize_text(value)

    words = []

    for word in text.split():
        words.append(TARGET_WORD_NORMALIZATION.get(word, word))

    return " ".join(words).strip()


def extract_json_from_text(text: str) -> dict:
    cleaned = str(text or "").strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```json", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^```", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def parse_user_date(value: Any) -> str | None:
    if value is None:
        return None

    text = normalize_text(value)
    today = date.today()

    if not text:
        return None

    iso_match = re.search(r"\d{4}-\d{2}-\d{2}", text)

    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(0)).isoformat()
        except ValueError:
            return None

    if "сегодня" in text:
        return today.isoformat()

    if "вчера" in text:
        return (today - timedelta(days=1)).isoformat()

    if "неделю назад" in text:
        return (today - timedelta(days=7)).isoformat()

    if "месяц назад" in text:
        return (today - timedelta(days=30)).isoformat()

    if "полгода назад" in text:
        return (today - timedelta(days=180)).isoformat()

    if "год назад" in text:
        return (today - timedelta(days=365)).isoformat()

    return None


def parse_interval(value: Any) -> int | None:
    if value is None:
        return None

    text = normalize_text(value)

    try:
        interval = int(value)
        return interval if interval > 0 else None
    except (TypeError, ValueError):
        pass

    number_match = re.search(r"(\d+)\s*(день|дня|дней|суток|сутки)", text)

    if number_match:
        interval = int(number_match.group(1))
        return interval if interval > 0 else None

    if "раз в месяц" in text or "ежемесячно" in text:
        return 30

    if "раз в полгода" in text or "каждые полгода" in text:
        return 180

    if "раз в год" in text or "ежегодно" in text:
        return 365

    return None


def build_memory_edit_prompt(message: str) -> str:
    today = date.today().isoformat()

    return f"""
Ты извлекаешь изменение объекта HouseMemory из сообщения пользователя.

Сегодня: {today}

Нужно вернуть только JSON.

Пользователь может менять:
- дату последнего обслуживания;
- интервал обслуживания в днях;
- комментарий;
- название объекта.

Правила:
- Не добавляй новый объект, если пользователь просит изменить существующий.
- Не удаляй объект.
- target — это объект, который пользователь хочет изменить.
- Если пользователь пишет "генератору", target должен быть "генератор".
- Если пользователь пишет "септику", target должен быть "септик".
- Если пользователь не указал поле, не возвращай его в updates.
- Если пользователь хочет убрать комментарий, верни clear_comment=true.
- Если пользователь сказал "сегодня", преобразуй дату в YYYY-MM-DD.
- Если пользователь сказал "вчера", преобразуй дату в YYYY-MM-DD.
- Если пользователь сказал "месяц назад", преобразуй примерно в дату на 30 дней раньше.
- Если пользователь сказал "раз в год", service_interval_days=365.
- Если пользователь сказал "раз в месяц", service_interval_days=30.
- Если пользователь сказал "раз в полгода", service_interval_days=180.

Сообщение пользователя:
{message}

Формат:
{{
  "target": "название объекта",
  "updates": {{
    "last_service_date": "YYYY-MM-DD",
    "service_interval_days": 365,
    "comment": "текст комментария",
    "clear_comment": false,
    "component_name": "новое название"
  }}
}}

Примеры:

Пользователь: "поставь генератору интервал обслуживания 365 дней"
Ответ:
{{
  "target": "генератор",
  "updates": {{
    "service_interval_days": 365
  }}
}}

Пользователь: "добавь комментарий к септику: чистить только весной"
Ответ:
{{
  "target": "септик",
  "updates": {{
    "comment": "чистить только весной"
  }}
}}

Пользователь: "убери комментарий у холодильника"
Ответ:
{{
  "target": "холодильник",
  "updates": {{
    "clear_comment": true
  }}
}}

Пользователь: "переименуй холодильник в кухонный холодильник"
Ответ:
{{
  "target": "холодильник",
  "updates": {{
    "component_name": "Кухонный холодильник"
  }}
}}

Пользователь: "фильтр обслуживали вчера"
Ответ:
{{
  "target": "фильтр",
  "updates": {{
    "last_service_date": "YYYY-MM-DD"
  }}
}}
"""


def validate_memory_edit_payload(raw_payload: dict) -> dict:
    if not isinstance(raw_payload, dict):
        return {
            "target": None,
            "updates": {},
        }

    target = raw_payload.get("target")
    updates = raw_payload.get("updates") or {}

    if not isinstance(updates, dict):
        updates = {}

    result_updates = {}

    if updates.get("component_name"):
        component_name = str(updates["component_name"]).strip()

        if component_name:
            result_updates["component_name"] = component_name[:255]

    if updates.get("last_service_date"):
        parsed_date = parse_user_date(updates.get("last_service_date"))

        if parsed_date:
            result_updates["last_service_date"] = parsed_date

    if updates.get("service_interval_days") is not None:
        interval = parse_interval(updates.get("service_interval_days"))

        if interval:
            result_updates["service_interval_days"] = interval

    if updates.get("clear_comment") is True:
        result_updates["clear_comment"] = True
    elif updates.get("comment") is not None:
        comment = str(updates.get("comment")).strip()

        if comment:
            result_updates["comment"] = comment[:1000]

    return {
        "target": normalize_target_text(target) if target else None,
        "updates": result_updates,
    }


def extract_memory_edit_with_gigachat(message: str) -> dict:
    prompt = build_memory_edit_prompt(message)

    try:
        raw_answer = generate_answer(prompt)
        parsed = extract_json_from_text(raw_answer)
        validated = validate_memory_edit_payload(parsed)
    except Exception:
        validated = {
            "target": None,
            "updates": {},
        }

    if validated.get("target") and validated.get("updates"):
        return validated

    return extract_memory_edit_fallback(message)


def extract_memory_edit_fallback(message: str) -> dict:
    text = normalize_text(message)
    updates = {}
    target = None

    interval = parse_interval(text)

    if interval:
        updates["service_interval_days"] = interval

    parsed_date = parse_user_date(text)

    if parsed_date:
        updates["last_service_date"] = parsed_date

    if "убери комментар" in text or "удали комментар" in text or "очисти комментар" in text:
        updates["clear_comment"] = True

    if "комментар" in text and ":" in message and "clear_comment" not in updates:
        comment = message.split(":", 1)[1].strip()

        if comment:
            updates["comment"] = comment[:1000]

    rename_match = re.search(
        r"переименуй\s+(.+?)\s+в\s+(.+)",
        text,
        flags=re.IGNORECASE,
    )

    if rename_match:
        target = rename_match.group(1).strip()
        new_name = rename_match.group(2).strip(" .,:;")

        if new_name:
            updates["component_name"] = new_name[:1].upper() + new_name[1:]

    if target is None:
        target_patterns = [
            r"(?:поставь|укажи|задай|измени|поменяй|обнови)\s+(.+?)\s+(?:интервал|периодичность|дату|дату обслуживания|комментарий)",
            r"(?:интервал|периодичность|дата|дата обслуживания|комментарий)\s+(?:для|к|у)\s+(.+?)(?:\s+\d+|:|$)",
            r"(?:почистил|почистила|заменил|заменила|проверил|проверила|обслужил|обслужила)\s+(.+?)(?:\s+сегодня|\s+вчера|\s+месяц|\s+неделю|\s+год|$)",
            r"у\s+(.+?)\s+(?:интервал|дата|комментарий)",
            r"к\s+(.+?)\s+комментарий",
        ]

        for pattern in target_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)

            if match:
                target = match.group(1).strip(" .,:;")
                break

    if target is None:
        known_targets = [
            "генератор",
            "септик",
            "насос",
            "фильтр",
            "котел",
            "котёл",
            "бойлер",
            "холодильник",
            "бассейн",
            "подвал",
            "камин",
            "крыша",
            "водосток",
            "дымоход",
        ]

        for known_target in known_targets:
            if known_target in text:
                target = known_target
                break

    return {
        "target": normalize_target_text(target) if target else None,
        "updates": updates,
    }


def find_memory_records_for_edit(
    db: Session,
    profile: HouseProfile,
    target: str,
) -> list[HouseMemory]:
    target_normalized = normalize_target_text(target)
    target_component_type = normalize_component_type(target_normalized)

    records = (
        db.query(HouseMemory)
        .filter(HouseMemory.house_id == profile.house_id)
        .all()
    )

    matches_by_id = {}

    for record in records:
        name_normalized = normalize_target_text(record.component_name)
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


def build_memory_edit_not_found_answer(target: str) -> str:
    return (
        f"Я не нашёл в памяти дома объект «{target}».\n\n"
        "Можно посмотреть текущую память командой: «покажи память дома»."
    )


def build_memory_edit_ambiguous_answer(records: list[HouseMemory]) -> str:
    lines = [
        "Я нашёл несколько похожих объектов в памяти дома:",
        "",
    ]

    for index, record in enumerate(records, start=1):
        lines.append(f"{index}. {record.component_name}")

    lines.extend(
        [
            "",
            "Напишите точнее, какой объект нужно изменить.",
            "Например: «поставь насосу скважины интервал 180 дней».",
        ]
    )

    return "\n".join(lines)


def build_memory_edit_confirmation_answer(
    record: HouseMemory,
    updates: dict,
) -> str:
    lines = [
        "Я понял так:",
        "",
        f"Нужно обновить объект: {record.component_name}",
        "",
        "Что изменится:",
    ]

    if "component_name" in updates:
        lines.append(f"- название: {record.component_name} → {updates['component_name']}")

    if "last_service_date" in updates:
        lines.append(f"- дата последнего обслуживания: {updates['last_service_date']}")

    if "service_interval_days" in updates:
        lines.append(f"- интервал обслуживания: {updates['service_interval_days']} дней")

    if updates.get("clear_comment"):
        lines.append("- комментарий будет удалён")
    elif "comment" in updates:
        lines.append(f"- комментарий: {updates['comment']}")

    lines.extend(["", "Сохранить изменения?"])

    return "\n".join(lines)