import json
import re
from datetime import date
from typing import Any, Optional

from app.services.gigachat_service import generate_answer


ALLOWED_COMPONENT_TYPES = {
    "generator",
    "boiler",
    "pump",
    "water_filter",
    "septic",
    "electrical_panel",
    "ventilation",
    "roof",
    "gutter",
    "basement",
    "drainage",
    "pool",
    "fireplace",
    "chimney",
}


COMPONENT_NAME_DEFAULTS = {
    "generator": "Генератор",
    "boiler": "Котёл",
    "pump": "Насос",
    "water_filter": "Фильтр воды",
    "septic": "Септик",
    "electrical_panel": "Электрощит",
    "ventilation": "Вентиляция",
    "roof": "Крыша",
    "gutter": "Водосток",
    "basement": "Подвал",
    "drainage": "Дренаж",
    "pool": "Бассейн",
    "fireplace": "Камин",
    "chimney": "Дымоход",
}

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def make_component_slug(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip().lower().replace("ё", "е")

    if not text:
        return None

    result = []

    for char in text:
        if char in CYRILLIC_TO_LATIN:
            result.append(CYRILLIC_TO_LATIN[char])
        elif char.isascii() and char.isalnum():
            result.append(char)
        else:
            result.append("_")

    slug = "".join(result)
    slug = re.sub(r"_+", "_", slug).strip("_")

    if not slug:
        return None

    return slug[:64]


def humanize_component_name(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text[:1].upper() + text[1:]

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


def normalize_component_type(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip().lower().replace("ё", "е")

    aliases = {
        "генератор": "generator",
        "generator": "generator",

        "котел": "boiler",
        "котёл": "boiler",
        "бойлер": "boiler",
        "boiler": "boiler",

        "насос": "pump",
        "pump": "pump",

        "фильтр": "water_filter",
        "фильтр воды": "water_filter",
        "water_filter": "water_filter",

        "септик": "septic",
        "septic": "septic",

        "электрощит": "electrical_panel",
        "щиток": "electrical_panel",
        "electrical_panel": "electrical_panel",

        "вентиляция": "ventilation",
        "ventilation": "ventilation",

        "крыша": "roof",
        "кровля": "roof",
        "roof": "roof",

        "водосток": "gutter",
        "желоб": "gutter",
        "gutter": "gutter",

        "подвал": "basement",
        "basement": "basement",

        "дренаж": "drainage",
        "drainage": "drainage",

        "бассейн": "pool",
        "pool": "pool",

        "камин": "fireplace",
        "fireplace": "fireplace",

        "дымоход": "chimney",
        "chimney": "chimney",

        "холодильник": "refrigerator",
        "рефрижератор": "refrigerator",
        "fridge": "refrigerator",
        "refrigerator": "refrigerator",
    }

    if text in aliases:
        return aliases[text]

    if text in ALLOWED_COMPONENT_TYPES:
        return text

    return make_component_slug(text)


def normalize_date(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        parsed = date.fromisoformat(text)
        return parsed.isoformat()
    except ValueError:
        return None


def normalize_interval(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        interval = int(value)
    except (TypeError, ValueError):
        return None

    if interval <= 0:
        return None

    return interval


def validate_memory_items(raw_items: list[dict]) -> list[dict]:
    result = []

    for raw_item in raw_items:
        raw_component_name = raw_item.get("component_name")
        raw_component_type = raw_item.get("component_type") or raw_component_name

        component_type = normalize_component_type(raw_component_type)

        if component_type is None:
            continue

        component_name = (
            raw_component_name
            or COMPONENT_NAME_DEFAULTS.get(component_type)
            or humanize_component_name(raw_component_type)
            or component_type
        )

        last_service_date = normalize_date(raw_item.get("last_service_date"))
        service_interval_days = normalize_interval(raw_item.get("service_interval_days"))

        comment = raw_item.get("comment")

        result.append(
            {
                "component_type": component_type,
                "component_name": str(component_name),
                "last_service_date": last_service_date,
                "service_interval_days": service_interval_days,
                "comment": str(comment) if comment else None,
            }
        )

    return result

def extract_plain_component_items_from_text(user_message: str) -> list[dict]:
    text = str(user_message or "").strip()

    if not text:
        return []

    normalized = text.lower().replace("ё", "е").strip()

    ignore_patterns = [
        "покажи",
        "что у меня",
        "что ты знаешь",
        "какие данные",
        "профиль",
        "сводк",
        "чеклист",
        "чек-лист",
        "что сделать",
        "как ",
        "почему",
        "?",
    ]

    if any(pattern in normalized for pattern in ignore_patterns):
        return []

    service_words = [
        "обслуж",
        "почист",
        "замен",
        "провер",
        "отремонт",
        "почини",
    ]

    # Если это явное сообщение об обслуживании, лучше пусть его разбирает LLM.
    # Fallback нужен именно для простых списков объектов.
    if any(pattern in normalized for pattern in service_words):
        return []

    cleaned = normalized

    prefixes = [
        "добавь",
        "добавить",
        "добавим",
        "запиши",
        "у меня есть",
        "есть",
        "объекты:",
        "объект:",
    ]

    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip(" ,.:;")

    if not cleaned:
        return []

    parts = re.split(r",|;|\s+и\s+", cleaned)

    result = []

    for part in parts:
        name = part.strip(" .,:;")

        if not name:
            continue

        # Не превращаем длинное предложение в название объекта.
        if len(name.split()) > 4:
            continue

        component_type = normalize_component_type(name)

        if not component_type:
            continue

        result.append(
            {
                "component_type": component_type,
                "component_name": humanize_component_name(name) or name,
                "last_service_date": None,
                "service_interval_days": None,
                "comment": None,
            }
        )

    return result

def build_memory_extraction_prompt(user_message: str) -> str:
    today = date.today().isoformat()

    return f"""
Ты извлекаешь обслуживаемые объекты загородного дома для HouseMemory.

Сегодняшняя дата: {today}

Пользователь может свободным текстом описать:
- какие объекты есть в доме;
- когда они обслуживались;
- через сколько дней повторять обслуживание;
- если дату не знает.

component_type не ограничен фиксированным списком.
Если объект типовой, используй понятный английский snake_case:
- generator — генератор
- boiler — котёл или бойлер
- pump — насос
- water_filter — фильтр воды
- septic — септик
- electrical_panel — электрощит
- ventilation — вентиляция
- roof — крыша
- gutter — водосток / желоба
- basement — подвал
- drainage — дренаж
- pool — бассейн
- fireplace — камин
- chimney — дымоход
- refrigerator — холодильник

Если объект не из примеров, придумай короткий component_type на английском в snake_case.
Пользователь component_type не видит, это только техническое имя для базы.

Правила:
Правила:
- Верни только JSON.
- Не добавляй пояснений вне JSON.
- Не выдумывай объект, если пользователь его не называл.
- Если пользователь сказал "сегодня", преобразуй в сегодняшнюю дату YYYY-MM-DD.
- Если пользователь сказал "вчера", преобразуй в дату на 1 день раньше сегодняшней.
- Если пользователь сказал "неделю назад", преобразуй примерно в дату на 7 дней раньше сегодняшней.
- Если пользователь сказал "месяц назад", преобразуй примерно в дату на 30 дней раньше сегодняшней.
- Если пользователь сказал "полгода назад", преобразуй примерно в дату на 180 дней раньше сегодняшней.
- Если пользователь сказал "год назад", преобразуй примерно в дату на 365 дней раньше сегодняшней.
- Если пользователь сказал "через 90 дней", service_interval_days = 90.
- Если пользователь сказал "раз в месяц", service_interval_days = 30.
- Если пользователь сказал "раз в полгода", service_interval_days = 180.
- Если пользователь сказал "раз в год", service_interval_days = 365.
- Если пользователь сказал "не знаю дату", last_service_date должен быть null.
- Если интервал обслуживания неизвестен, service_interval_days должен быть null.
- Если объект упомянут без даты, всё равно добавь его с null-датой.
- Если пользователь говорит, что заменил, почистил, проверил или обслужил объект, это тоже объект HouseMemory.

Сообщение пользователя:
{user_message}

Формат ответа:
{{
  "items": [
    {{
      "component_type": "pump",
      "component_name": "Насос",
      "last_service_date": "YYYY-MM-DD или null",
      "service_interval_days": 180,
      "comment": "комментарий или null"
    }}
  ],
  "confidence": 0.0,
  "need_clarification": false,
  "clarification_question": null
}}
"""


def extract_memory_items_with_gigachat(user_message: str) -> dict:
    prompt = build_memory_extraction_prompt(user_message)

    try:
        raw_answer = generate_answer(prompt)
        parsed = extract_json_from_text(raw_answer)
    except Exception as error:
        return {
            "items": [],
            "confidence": 0.0,
            "need_clarification": True,
            "clarification_question": None,
            "error": str(error),
        }

    raw_items = parsed.get("items") or []
    items = validate_memory_items(raw_items)

    if not items:
        items = extract_plain_component_items_from_text(user_message)

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "items": items,
        "confidence": confidence,
        "need_clarification": bool(parsed.get("need_clarification", False)),
        "clarification_question": parsed.get("clarification_question"),
    }