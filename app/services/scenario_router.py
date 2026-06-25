import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScenarioDetectionResult:
    scenario: str
    month: Optional[str] = None
    component_type: Optional[str] = None


MONTH_PATTERNS = {
    "january": ["январ", "january", "jan"],
    "february": ["феврал", "february", "feb"],
    "march": ["март", "march", "mar"],
    "april": ["апрел", "april", "apr"],
    "may": ["май", "мая", "may"],
    "june": ["июн", "june", "jun"],
    "july": ["июл", "july", "jul"],
    "august": ["август", "august", "aug"],
    "september": ["сентябр", "september", "sep"],
    "october": ["октябр", "october", "oct"],
    "november": ["ноябр", "november", "nov"],
    "december": ["декабр", "december", "dec"],
}


COMPONENT_PATTERNS = {
    "generator": ["генератор"],
    "boiler": ["котел", "котёл", "бойлер"],
    "pump": ["насос"],
    "water_filter": ["фильтр", "фильтр воды"],
    "septic": ["септик"],
    "electrical_panel": ["электрощит", "щиток", "электрический щит"],
    "ventilation": ["вентиляц"],
    "roof": ["крыша", "кровл"],
    "gutter": ["водосток", "желоб"],
    "basement": ["подвал"],
    "drainage": ["дренаж"],
    "pool": ["бассейн"],
    "fireplace": ["камин"],
    "chimney": ["дымоход"],
}


def normalize_text(value: str) -> str:
    return value.lower().replace("ё", "е").strip()


def contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def extract_month(message: str) -> Optional[str]:
    normalized = normalize_text(message)

    for month_value, patterns in MONTH_PATTERNS.items():
        if contains_any(normalized, patterns):
            return month_value

    return None


def extract_component_type(message: str) -> Optional[str]:
    normalized = normalize_text(message)

    for component_type, patterns in COMPONENT_PATTERNS.items():
        if contains_any(normalized, [normalize_text(pattern) for pattern in patterns]):
            return component_type

    return None

def is_problem_question(message: str) -> bool:
    normalized = normalize_text(message)

    problem_patterns = [
        "что делать если",
        "что сделать если",
        "почему",
        "проблема",
        "авария",
        "ошибка",

        "не работает",
        "не включается",
        "не запускается",
        "не греет",
        "не качает",
        "не набирает",
        "не сливает",
        "не держит",
        "не тянет",
        "перестал",
        "перестала",
        "перестало",

        "сломал",
        "сломалась",
        "сломалось",
        "сломался",
        "поломка",

        "течет",
        "течёт",
        "потек",
        "потёк",
        "протекает",
        "капает",
        "затопило",
        "подтопило",
        "лужа",
        "вода идет рывками",
        "вода идёт рывками",
        "рывками",
        "нет воды",
        "слабый напор",
        "нет напора",

        "пахнет",
        "запах",
        "воняет",
        "сырость",
        "плесень",

        "шумит",
        "гудит",
        "трещит",
        "стучит",
        "вибрирует",

        "искрит",
        "дымит",
        "дым",
        "запах гари",
        "гарь",
        "выбивает автомат",
        "выбило автомат",
        "короткое замыкание",
    ]

    return contains_any(normalized, problem_patterns)


def is_checklist_request(message: str) -> bool:
    normalized = normalize_text(message)

    if is_problem_question(message):
        return False

    explicit_checklist_patterns = [
        "чек-лист",
        "чеклист",
        "список задач",
        "задачи по дому",
        "работы по дому",
        "план работ",
        "план обслуживания",
        "план по дому",
        "что проверить",
        "что нужно проверить",
        "что надо проверить",
        "что обслужить",
        "что нужно обслужить",
        "что надо обслужить",
    ]

    month_action_patterns = [
        "что сделать",
        "что нужно сделать",
        "что надо сделать",
        "что проверить",
        "что обслужить",
        "какие задачи",
        "какие работы",
        "план",
        "чек-лист",
        "чеклист",
    ]

    house_context_patterns = [
        "по дому",
        "для дома",
        "дома",
        "дом",
        "участок",
        "на участке",
        "по участку",
        "в этом месяце",
        "на этот месяц",
        "сейчас",
        "сезон",
        "сезонные",
    ]

    short_general_checklist_phrases = {
        "что мне делать",
        "что мне надо делать",
        "что мне нужно делать",
        "что делать",
        "что надо делать",
        "что нужно делать",
        "какие планы",
        "какие задачи",
        "какие дела",
        "чем заняться",
    }

    has_month = extract_month(message) is not None

    if contains_any(normalized, explicit_checklist_patterns):
        return True

    # Если указан месяц, то фраза “что сделать в мае” — это чек-лист.
    if has_month and contains_any(normalized, month_action_patterns):
        return True

    # Если есть контекст дома/участка, то “что сделать по дому” — чек-лист.
    if (
        contains_any(normalized, month_action_patterns)
        and contains_any(normalized, house_context_patterns)
    ):
        return True

    # Очень короткая общая фраза без признаков проблемы.
    # “течет вода, что делать” сюда не попадёт, потому что это не точное совпадение
    # и выше уже сработает is_problem_question.
    if normalized.strip(" ?!.") in short_general_checklist_phrases:
        return True

    return False


def is_summary_request(message: str) -> bool:
    normalized = normalize_text(message)

    summary_patterns = [
        "сводк",
        "состояни",
        "статус",
        "статусы",
        "что по дому",
        "как дом",
        "как мой дом",
        "как там дом",
        "как там мой дом",
        "что требует внимания",
        "что просрочено",
        "что скоро обслуживать",
        "все ли нормально",
        "все ли в порядке",
        "проблемы по дому",
        "критич",
    ]

    house_words = [
        "дом",
        "дома",
        "дому",
        "объект",
        "объекты",
    ]

    has_summary_intent = contains_any(normalized, summary_patterns)
    has_house_context = contains_any(normalized, house_words)

    # Явные вопросы про состояние дома
    if has_summary_intent and has_house_context:
        return True

    # Иногда пользователь может спросить коротко:
    # "Что требует внимания?"
    # Это тоже сводка, даже без слова "дом".
    if contains_any(
        normalized,
        [
            "что требует внимания",
            "что просрочено",
            "что скоро обслуживать",
            "все ли нормально",
            "все ли в порядке",
        ]
    ):
        return True

    return False


def is_memory_update_request(message: str) -> bool:
    normalized = normalize_text(message)

    update_patterns = [
        "почист",
        "обслуж",
        "замен",
        "провер",
        "сделал",
        "сделала",
        "прочист",
        "отремонт",
        "починил",
        "починила",
    ]

    has_update_word = contains_any(normalized, update_patterns)
    has_component = extract_component_type(message) is not None

    return has_update_word and has_component

def is_memory_delete_request(message: str) -> bool:
    normalized = normalize_text(message)

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

    memory_patterns = [
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

    if "профил" in normalized:
        return False

    has_delete_intent = contains_any(normalized, delete_patterns)
    has_memory_context = contains_any(normalized, memory_patterns)

    return has_delete_intent and has_memory_context

def is_memory_edit_request(message: str) -> bool:
    normalized = normalize_text(message)

    if "профил" in normalized:
        return False

    edit_patterns = [
        "интервал",
        "периодичность",
        "комментарий",
        "комментар",
        "дату обслуживания",
        "дата обслуживания",
        "последнее обслуживание",
        "последний раз",
        "переименуй",
        "переименовать",
        "название",
    ]

    service_patterns = [
        "почистил",
        "почистила",
        "обслужил",
        "обслужила",
        "заменил",
        "заменила",
        "проверил",
        "проверила",
        "отремонтировал",
        "отремонтировала",
    ]

    mutation_patterns = [
        "поставь",
        "укажи",
        "задай",
        "измени",
        "изменить",
        "поменяй",
        "поменять",
        "обнови",
        "обновить",
        "добавь",
        "добавить",
        "убери",
        "убрать",
    ]

    has_edit_field = contains_any(normalized, edit_patterns)
    has_service_action = contains_any(normalized, service_patterns)
    has_mutation = contains_any(normalized, mutation_patterns)

    if has_edit_field and has_mutation:
        return True

    if has_service_action:
        return True

    return False

def is_profile_edit_request(message: str) -> bool:
    normalized = normalize_text(message)

    mutation_patterns = [
        "измени",
        "изменить",
        "поменяй",
        "поменять",
        "обнови",
        "обновить",
        "добавь",
        "добавить",
        "убери",
        "убрать",
        "больше нет",
        "теперь",
        "у меня теперь",
    ]

    profile_patterns = [
        "профиль",
        "дом",
        "дома",
        "тип дома",
        "регион",
        "климат",
        "климатическая зона",
        "источник воды",
        "вода",
        "скважина",
        "колодец",
        "центральная вода",
        "водопровод",
        "отопление",
        "газ",
        "генератор",
        "бассейн",
        "подвал",
        "участок",
        "камин",
        "вовлеченность",
        "вовлечённость",
    ]

    has_mutation = contains_any(normalized, mutation_patterns)
    has_profile_context = contains_any(normalized, profile_patterns)

    return has_mutation and has_profile_context

def is_memory_status_request(message: str) -> bool:
    normalized = normalize_text(message)

    if is_problem_question(message):
        return False

    status_patterns = [
        "сводк",
        "состояние дома",
        "статус дома",
        "статусы дома",
        "что по дому",
        "как дом",
        "как мой дом",
        "как там дом",
        "как там мой дом",
        "что требует внимания",
        "что просрочено",
        "что скоро обслуживать",
        "все ли нормально",
        "всё ли нормально",
        "все ли в порядке",
        "всё ли в порядке",
        "проблемы по дому",
        "что в порядке",
        "что не в порядке",
    ]

    return contains_any(normalized, status_patterns)


def detect_scenario(message: str) -> ScenarioDetectionResult:
    if is_memory_delete_request(message):
        return ScenarioDetectionResult(
            scenario="memory_delete"
        )

    if is_memory_edit_request(message):
        return ScenarioDetectionResult(
            scenario="memory_edit",
            component_type=extract_component_type(message),
        )

    if is_profile_edit_request(message):
        return ScenarioDetectionResult(
            scenario="profile_edit"
        )

    if is_memory_list_request(message) or is_memory_status_request(message):
        return ScenarioDetectionResult(
            scenario="memory_list"
        )

    if is_profile_view_request(message):
        return ScenarioDetectionResult(
            scenario="profile_view"
        )

    if is_checklist_request(message):
        return ScenarioDetectionResult(
            scenario="checklist_month",
            month=extract_month(message)
        )

    if is_memory_update_request(message):
        return ScenarioDetectionResult(
            scenario="memory_update",
            component_type=extract_component_type(message)
        )

    return ScenarioDetectionResult(
        scenario="rag_answer"
    )

def is_memory_list_request(message: str) -> bool:
    normalized = normalize_text(message)

    if is_problem_question(message):
        return False

    memory_patterns = [
        "память дома",
        "housememory",
        "house memory",
        "обслуживаемые объекты",
        "обслуживаемые компоненты",
        "объекты в памяти",
        "компоненты в памяти",
        "что в памяти",
        "покажи память",
        "покажи обслуживаемые объекты",
        "какие объекты обслуживать",

        # Более естественные фразы пользователя
        "что у меня есть в доме",
        "что у меня уже есть в доме",
        "покажи что у меня есть в доме",
        "покажи что у меня уже есть в доме",
        "какие объекты есть в доме",
        "какие компоненты есть в доме",
        "что есть из обслуживаемого",
        "что есть из обслуживаемых объектов",
        "что нужно обслуживать",
        "что мне нужно обслуживать",
        "что мне надо обслуживать",
    ]

    mutation_patterns = [
        "добав",
        "создай",
        "запиши",
        "измени",
        "обнови",
        "поменяй",
        "удали",
        "сотри",
        "обслужил",
        "почистил",
        "заменил",
        "проверил",
    ]

    if contains_any(normalized, mutation_patterns):
        return False

    return contains_any(normalized, memory_patterns)

def is_profile_view_request(message: str) -> bool:
    normalized = normalize_text(message)

    if is_problem_question(message):
        return False

    profile_patterns = [
        "мой профиль",
        "профиль дома",
        "какой профиль",
        "какой мой профиль",
        "покажи профиль",
        "покажи профиль дома",
        "покажи параметры дома",
        "параметры дома",
        "какой у меня дом",

        # То, что раньше могло уходить в house_overview
        "что ты знаешь о моем доме",
        "что ты знаешь о доме",
        "какие данные есть по дому",
        "покажи данные по дому",
        "покажи мой дом",
        "покажи информацию о доме",
        "информация о доме",
        "данные профиля",
        "что сохранено в профиле",
    ]

    mutation_patterns = [
        "добав",
        "измени",
        "поменяй",
        "обнови",
        "удали",
        "сотри",
        "замени",
        "убери",
    ]

    if contains_any(normalized, mutation_patterns):
        return False

    return contains_any(normalized, profile_patterns)