import json
import re
from typing import Any

from app.db.models import HouseProfile
from app.services.gigachat_service import generate_answer


PROFILE_FIELD_LABELS = {
    "house_type": "тип дома",
    "region": "регион",
    "climate_zone": "климатическая зона",
    "water_source": "источник воды",
    "heating_type": "тип отопления",
    "has_gas": "газ",
    "has_generator": "генератор",
    "has_pool": "бассейн",
    "has_basement": "подвал",
    "has_plot": "участок",
    "has_fireplace": "камин",
    "involvement_level": "уровень вовлечённости",
}


PROFILE_VALUE_LABELS = {
    "dacha": "дача",
    "pmzh": "дом для постоянного проживания",

    "well": "скважина",
    "kolodec": "колодец",
    "central": "центральное водоснабжение",

    "gas": "газовое",
    "electric": "электрическое",
    "solid_fuel": "твердотопливное",

    "low": "низкий",
    "medium": "средний",
    "high": "высокий",
}


BOOLEAN_FIELDS = {
    "has_gas",
    "has_generator",
    "has_pool",
    "has_basement",
    "has_plot",
    "has_fireplace",
}


STRING_FIELDS = {
    "region",
    "climate_zone",
}


ENUM_VALUES = {
    "house_type": {"dacha", "pmzh"},
    "water_source": {"well", "kolodec", "central"},
    "heating_type": {"gas", "electric", "solid_fuel"},
    "involvement_level": {"low", "medium", "high"},
}


def normalize_text(value: Any) -> str:
    return str(value or "").lower().replace("ё", "е").strip()


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


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    text = normalize_text(value)

    true_values = [
        "true",
        "да",
        "есть",
        "имеется",
        "присутствует",
        "добавь",
        "добавить",
        "появился",
        "появилась",
        "появилось",
    ]

    false_values = [
        "false",
        "нет",
        "нету",
        "отсутствует",
        "убери",
        "убрать",
        "не есть",
        "не имеется",
        "больше нет",
    ]

    if any(item in text for item in true_values):
        return True

    if any(item in text for item in false_values):
        return False

    return None


def normalize_enum_value(field: str, value: Any) -> str | None:
    text = normalize_text(value)

    if field == "house_type":
        if "дач" in text:
            return "dacha"
        if "пмж" in text or "постоян" in text or "круглогод" in text:
            return "pmzh"

    if field == "water_source":
        if "скваж" in text:
            return "well"
        if "колод" in text:
            return "kolodec"
        if "централ" in text or "водопровод" in text:
            return "central"

    if field == "heating_type":
        if "газ" in text:
            return "gas"
        if "электр" in text:
            return "electric"
        if "тверд" in text or "дров" in text or "уголь" in text:
            return "solid_fuel"

    if field == "involvement_level":
        if "низ" in text or "миним" in text or "low" in text:
            return "low"
        if "сред" in text or "medium" in text:
            return "medium"
        if "выс" in text or "сам" in text or "high" in text:
            return "high"

    if text in ENUM_VALUES.get(field, set()):
        return text

    return None


def validate_profile_changes(raw_changes: dict) -> dict:
    result = {}

    if not isinstance(raw_changes, dict):
        return result

    for field, raw_value in raw_changes.items():
        if field in BOOLEAN_FIELDS:
            value = normalize_bool(raw_value)

            if value is not None:
                result[field] = value

            continue

        if field in STRING_FIELDS:
            value = str(raw_value or "").strip()

            if value:
                result[field] = value[:255]

            continue

        if field in ENUM_VALUES:
            value = normalize_enum_value(field, raw_value)

            if value in ENUM_VALUES[field]:
                result[field] = value

            continue

    return result


def build_profile_edit_prompt(message: str, profile: HouseProfile) -> str:
    return f"""
Ты извлекаешь изменения профиля дома из сообщения пользователя.

Верни только JSON.

Текущий профиль:
{{
  "house_type": "{profile.house_type}",
  "region": "{profile.region}",
  "climate_zone": "{profile.climate_zone}",
  "water_source": "{profile.water_source}",
  "heating_type": "{profile.heating_type}",
  "has_gas": {str(profile.has_gas).lower()},
  "has_generator": {str(profile.has_generator).lower()},
  "has_pool": {str(profile.has_pool).lower()},
  "has_basement": {str(profile.has_basement).lower()},
  "has_plot": {str(profile.has_plot).lower()},
  "has_fireplace": {str(profile.has_fireplace).lower()},
  "involvement_level": "{profile.involvement_level}"
}}

Поля, которые можно изменить:
- house_type: dacha | pmzh
- region: string
- climate_zone: string
- water_source: well | kolodec | central
- heating_type: gas | electric | solid_fuel
- has_gas: boolean
- has_generator: boolean
- has_pool: boolean
- has_basement: boolean
- has_plot: boolean
- has_fireplace: boolean
- involvement_level: low | medium | high

Правила:
- Верни только те поля, которые пользователь явно хочет изменить.
- Не придумывай изменения.
- Нельзя удалять поле профиля полностью.
- Если пользователь говорит "убери бассейн", это значит has_pool=false.
- Если пользователь говорит "добавь генератор", это значит has_generator=true.
- Если пользователь меняет несколько параметров, верни их все.
- Не возвращай null.
- Не объясняй ответ текстом.

Сообщение пользователя:
{message}

Формат:
{{
  "changes": {{
    "field": "value"
  }}
}}

Примеры:

Пользователь: "измени отопление на электрическое"
Ответ:
{{
  "changes": {{
    "heating_type": "electric"
  }}
}}

Пользователь: "добавь что у меня есть газ и генератор"
Ответ:
{{
  "changes": {{
    "has_gas": true,
    "has_generator": true
  }}
}}

Пользователь: "у меня теперь центральная вода и нет бассейна"
Ответ:
{{
  "changes": {{
    "water_source": "central",
    "has_pool": false
  }}
}}
"""


def extract_profile_changes_with_gigachat(
    message: str,
    profile: HouseProfile,
) -> dict:
    prompt = build_profile_edit_prompt(
        message=message,
        profile=profile,
    )

    try:
        raw_answer = generate_answer(prompt)
        parsed = extract_json_from_text(raw_answer)
        changes = validate_profile_changes(parsed.get("changes") or {})
    except Exception:
        changes = {}

    if changes:
        return changes

    return extract_profile_changes_fallback(message)


def extract_profile_changes_fallback(message: str) -> dict:
    text = normalize_text(message)
    changes = {}

    if "скваж" in text:
        changes["water_source"] = "well"
    elif "колод" in text:
        changes["water_source"] = "kolodec"
    elif "централ" in text or "водопровод" in text:
        changes["water_source"] = "central"

    if "отоплен" in text or "котел" in text or "котёл" in text:
        if "газ" in text:
            changes["heating_type"] = "gas"
        elif "электр" in text:
            changes["heating_type"] = "electric"
        elif "тверд" in text or "дров" in text or "уголь" in text:
            changes["heating_type"] = "solid_fuel"

    if "дач" in text:
        changes["house_type"] = "dacha"
    elif "пмж" in text or "постоян" in text or "круглогод" in text:
        changes["house_type"] = "pmzh"

    field_keywords = {
        "has_gas": ["газ"],
        "has_generator": ["генератор"],
        "has_pool": ["бассейн"],
        "has_basement": ["подвал"],
        "has_plot": ["участок"],
        "has_fireplace": ["камин"],
    }

    negative_words = [
        "нет",
        "нету",
        "без",
        "убери",
        "убрать",
        "отсутствует",
        "больше нет",
    ]

    positive_words = [
        "есть",
        "добавь",
        "добавить",
        "появился",
        "появилась",
        "появилось",
        "имеется",
    ]

    for field, keywords in field_keywords.items():
        if not any(keyword in text for keyword in keywords):
            continue

        if any(word in text for word in negative_words):
            changes[field] = False
        elif any(word in text for word in positive_words):
            changes[field] = True

    if "низ" in text and "вовлеч" in text:
        changes["involvement_level"] = "low"
    elif "сред" in text and "вовлеч" in text:
        changes["involvement_level"] = "medium"
    elif "выс" in text and "вовлеч" in text:
        changes["involvement_level"] = "high"

    return validate_profile_changes(changes)


def value_to_user_text(field: str, value: Any) -> str:
    if field in BOOLEAN_FIELDS:
        return "есть" if value else "нет"

    return PROFILE_VALUE_LABELS.get(str(value), str(value))


def build_profile_edit_confirmation_answer(
    profile: HouseProfile,
    changes: dict,
) -> str:
    lines = [
        "Я понял так:",
        "",
        "Нужно изменить профиль дома:",
    ]

    for field, new_value in changes.items():
        label = PROFILE_FIELD_LABELS.get(field, field)
        old_value = getattr(profile, field, None)

        lines.append(
            f"- {label}: {value_to_user_text(field, old_value)} → "
            f"{value_to_user_text(field, new_value)}"
        )

    lines.extend(["", "Сохранить изменения?"])

    return "\n".join(lines)