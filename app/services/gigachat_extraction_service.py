import json
import re
from typing import Any

from app.services.gigachat_service import generate_answer


PROFILE_FIELDS = {
    "house_type",
    "region",
    "climate_zone",
    "water_source",
    "heating_type",
    "has_gas",
    "has_generator",
    "has_pool",
    "has_basement",
    "has_plot",
    "has_fireplace",
    "involvement_level",
}

BOOLEAN_FIELDS = {
    "has_gas",
    "has_generator",
    "has_pool",
    "has_basement",
    "has_plot",
    "has_fireplace",
}

BOOLEAN_FIELD_KEYWORDS = {
    "has_gas": ["газ"],
    "has_generator": ["генератор"],
    "has_pool": ["бассейн"],
    "has_basement": ["подвал"],
    "has_plot": ["участок", "земля", "сад", "огород"],
    "has_fireplace": ["камин"],
}

ALLOWED_VALUES = {
    "house_type": {"dacha", "pmzh"},
    "water_source": {"well", "kolodec", "central"},
    "heating_type": {"gas", "electric", "solid_fuel"},
    "involvement_level": {"low", "medium", "high"},
    "climate_zone": {"north", "middle", "south"},
}

FIELD_DESCRIPTIONS = {
    "house_type": "тип дома: dacha — дача, pmzh — постоянное проживание",
    "region": "регион, например: Московская область, Ленинградская область",
    "climate_zone": "климатическая зона: north, middle, south",
    "water_source": "источник воды: well — скважина, kolodec — колодец, central — центральное водоснабжение",
    "heating_type": "отопление: gas — газовое, electric — электрическое, solid_fuel — твёрдотопливное",
    "has_gas": "есть ли газ: true/false",
    "has_generator": "есть ли генератор: true/false",
    "has_pool": "есть ли бассейн: true/false",
    "has_basement": "есть ли подвал: true/false",
    "has_plot": "есть ли участок: true/false",
    "has_fireplace": "есть ли камин: true/false",
    "involvement_level": "уровень вовлечённости: low, medium, high",
}


def normalize_text(value: Any) -> str:
    return str(value).strip().lower().replace("ё", "е")


def extract_json_from_text(text: str) -> dict:
    cleaned = text.strip()

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

    if text in {"true", "да", "есть", "имеется", "yes", "1"}:
        return True

    if text in {"false", "нет", "нету", "отсутствует", "no", "0"}:
        return False

    return None


def normalize_profile_value(field: str, value: Any):
    if value is None:
        return None

    if field in BOOLEAN_FIELDS:
        return normalize_bool(value)

    text = normalize_text(value)

    if field == "house_type":
        if text in {"dacha", "дача", "дачный"} or "дач" in text:
            return "dacha"
        if text in {"pmzh", "пмж"} or "постоян" in text:
            return "pmzh"
        return None

    if field == "water_source":
        if text in {"well", "скважина"} or "скваж" in text:
            return "well"
        if text in {"kolodec", "колодец"} or "колод" in text:
            return "kolodec"
        if text in {"central", "центральное"} or "централ" in text or "водопровод" in text:
            return "central"
        return None

    if field == "heating_type":
        if text in {"gas", "газовое"} or "газ" in text:
            return "gas"
        if text in {"electric", "электрическое"} or "элект" in text:
            return "electric"
        if text in {"solid_fuel", "твердотопливное", "твёрдотопливное"}:
            return "solid_fuel"
        if "дров" in text or "уголь" in text or "тверд" in text:
            return "solid_fuel"
        return None

    if field == "involvement_level":
        if text in {"low", "низкий"} or "миним" in text or "низ" in text:
            return "low"
        if text in {"medium", "средний"} or "сред" in text or "крат" in text:
            return "medium"
        if text in {"high", "высокий"} or "подроб" in text or "сам" in text or "выс" in text:
            return "high"
        return None

    if field == "climate_zone":
        if text in {"north", "северная", "северный"} or "север" in text or "холод" in text:
            return "north"
        if text in {"middle", "средняя"} or "сред" in text or "умерен" in text:
            return "middle"
        if text in {"south", "южная", "южный"} or "юг" in text or "южн" in text or "тепл" in text:
            return "south"
        return None

    if field == "region":
        raw = str(value).strip()

        bad_values = {
            "привет",
            "здравствуйте",
            "не знаю",
            "не уверен",
            "не уверена",
            "без понятия",
        }

        if normalize_text(raw) in bad_values:
            return None

        if len(raw) < 3:
            return None

        if not re.search(r"[а-яa-z]", normalize_text(raw)):
            return None

        return raw

    return None


def validate_extracted_fields(
    raw_fields: dict,
    current_step: str,
    user_message: str
) -> dict:
    result = {}

    for field, value in raw_fields.items():
        if field not in PROFILE_FIELDS:
            continue

        # Важная защита:
        # boolean-поля принимаем только если это текущий вопрос
        # или пользователь явно упомянул соответствующий объект.
        if field in BOOLEAN_FIELDS:
            if not is_boolean_field_relevant(
                field=field,
                current_step=current_step,
                user_message=user_message
            ):
                continue

        normalized_value = normalize_profile_value(field, value)

        if normalized_value is None:
            continue

        if field in ALLOWED_VALUES and normalized_value not in ALLOWED_VALUES[field]:
            continue

        result[field] = normalized_value

    # Газовое отопление логически означает наличие газа.
    if result.get("heating_type") == "gas":
        result["has_gas"] = True

    return result


def build_profile_extraction_prompt(
    current_step: str,
    user_message: str,
    draft_data: dict
) -> str:
    fields_description = "\n".join(
        f"- {field}: {description}"
        for field, description in FIELD_DESCRIPTIONS.items()
    )

    return f"""
Ты извлекаешь структурированные данные для профиля загородного дома.

Сейчас backend ожидает поле:
{current_step}

Но пользователь может в одном сообщении указать сразу несколько полей.
Извлекай все поля, которые можно понять уверенно.

Уже собранные данные:
{json.dumps(draft_data, ensure_ascii=False, indent=2)}

Допустимые поля:
{fields_description}

Сообщение пользователя:
{user_message}

Правила:
- Верни только JSON.
- Не добавляй пояснения вне JSON.
- Не выдумывай данные.
- Если пользователь просто здоровается или не отвечает по смыслу, верни пустой fields.
- Если значение неясно, не заполняй это поле.
- Для boolean используй true или false.
- Для enum используй только допустимые технические значения.

Формат ответа:
{{
  "fields": {{}},
  "confidence": 0.0,
  "need_clarification": false,
  "clarification_question": null
}}

Важно:
- fields должен содержать только те поля, которые пользователь явно указал в сообщении.
- Не включай has_generator, has_pool, has_basement, has_plot, has_fireplace со значением false, если пользователь явно не сказал, что этого объекта нет.
- Не используй false как значение по умолчанию.
- Если пользователь отвечает только на текущий вопрос, верни только текущее поле.
- Если пользователь в одном сообщении указал несколько параметров, можно вернуть несколько полей.

Примеры:

Ответ пользователя:
"Да"
Если backend ожидает поле has_generator:
{{
  "fields": {{
    "has_generator": true
  }},
  "confidence": 0.9,
  "need_clarification": false,
  "clarification_question": null
}}

Ответ пользователя:
"Нет"
Если backend ожидает поле has_pool:
{{
  "fields": {{
    "has_pool": false
  }},
  "confidence": 0.9,
  "need_clarification": false,
  "clarification_question": null
}}

Ответ пользователя:
"Это дача в Ленинградской области, вода центральная"
{{
  "fields": {{
    "house_type": "dacha",
    "region": "Ленинградская область",
    "water_source": "central"
  }},
  "confidence": 0.9,
  "need_clarification": false,
  "clarification_question": null
}}
"""


def extract_profile_fields_with_gigachat(
    current_step: str,
    user_message: str,
    draft_data: dict
) -> dict:
    prompt = build_profile_extraction_prompt(
        current_step=current_step,
        user_message=user_message,
        draft_data=draft_data
    )

    try:
        raw_answer = generate_answer(prompt)
        parsed = extract_json_from_text(raw_answer)
    except Exception as error:
        return {
            "fields": {},
            "confidence": 0.0,
            "need_clarification": True,
            "clarification_question": None,
            "error": str(error),
        }

    raw_fields = parsed.get("fields") or {}
    fields = validate_extracted_fields(
        raw_fields=raw_fields,
        current_step=current_step,
        user_message=user_message
    )
    confidence = parsed.get("confidence", 0.0)

    try:
        confidence = float(confidence)
    except TypeError:
        confidence = 0.0
    except ValueError:
        confidence = 0.0

    return {
        "fields": fields,
        "confidence": confidence,
        "need_clarification": bool(parsed.get("need_clarification", False)),
        "clarification_question": parsed.get("clarification_question"),
    }

def is_boolean_field_relevant(
    field: str,
    current_step: str,
    user_message: str
) -> bool:
    if field == current_step:
        return True

    text = normalize_text(user_message)

    keywords = BOOLEAN_FIELD_KEYWORDS.get(field, [])

    return any(keyword in text for keyword in keywords)