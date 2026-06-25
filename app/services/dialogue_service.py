from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import AgentSession
from app.schemas.agent import AgentAskResponse
from app.schemas.profile import HouseProfileCreate
from app.services.profile_service import create_profile
from app.services.memory_service import sync_profile_components_to_memory
from app.services.session_service import update_agent_session
from app.services.gigachat_extraction_service import extract_profile_fields_with_gigachat


PROFILE_STEPS = [
    {
        "field": "house_type",
        "question": "Это дача или дом для постоянного проживания? Напишите: дача или ПМЖ.",
    },
    {
        "field": "region",
        "question": "В каком регионе находится дом?",
    },
    {
        "field": "climate_zone",
        "question": "Какая климатическая зона? Если не знаете, можно написать примерно: средняя полоса, северная, южная.",
    },
    {
        "field": "water_source",
        "question": "Какой источник воды: скважина, колодец или центральное водоснабжение?",
    },
    {
        "field": "heating_type",
        "question": "Какой тип отопления: газовое, электрическое или твёрдотопливное?",
    },
    {
        "field": "has_gas",
        "question": "Есть ли газ? Ответьте: да или нет.",
    },
    {
        "field": "has_generator",
        "question": "Есть ли генератор? Ответьте: да или нет.",
    },
    {
        "field": "has_pool",
        "question": "Есть ли бассейн? Ответьте: да или нет.",
    },
    {
        "field": "has_basement",
        "question": "Есть ли подвал? Ответьте: да или нет.",
    },
    {
        "field": "has_plot",
        "question": "Есть ли участок? Ответьте: да или нет.",
    },
    {
        "field": "has_fireplace",
        "question": "Есть ли камин? Ответьте: да или нет.",
    },
    {
        "field": "involvement_level",
        "question": (
            "Какой уровень вовлечённости вам удобен: "
            "низкий — хочу минимум деталей, средний — можно объяснять кратко, "
            "высокий — хочу разбираться сам?"
        ),
    },
]


def normalize_text(value: str) -> str:
    return value.lower().replace("ё", "е").strip()


def parse_bool_answer(message: str) -> bool | None:
    text = normalize_text(message)

    yes_words = ["да", "есть", "имеется", "ага", "конечно"]
    no_words = ["нет", "не", "отсутствует", "нету"]

    if any(word in text for word in yes_words):
        return True

    if any(word in text for word in no_words):
        return False

    return None


def parse_profile_field(field: str, message: str):
    text = normalize_text(message)

    if field == "house_type":
        if "дач" in text:
            return "dacha"
        if "пмж" in text or "постоян" in text:
            return "pmzh"
        return None

    if field == "water_source":
        if "скваж" in text:
            return "well"
        if "колод" in text:
            return "kolodec"
        if "централ" in text or "водопровод" in text:
            return "central"
        return None

    if field == "heating_type":
        if "газ" in text:
            return "gas"
        if "элект" in text:
            return "electric"
        if "тверд" in text or "дров" in text or "уголь" in text:
            return "solid_fuel"
        return None

    if field in [
        "has_gas",
        "has_generator",
        "has_pool",
        "has_basement",
        "has_plot",
        "has_fireplace",
    ]:
        return parse_bool_answer(message)

    if field == "involvement_level":
        if "низ" in text or "миним" in text:
            return "low"
        if "сред" in text or "крат" in text:
            return "medium"
        if "выс" in text or "сам" in text or "подроб" in text:
            return "high"
        return None

    if field in ["region", "climate_zone"]:
        if len(message.strip()) < 2:
            return None
        return message.strip()

    return None


def get_step_by_field(field: str) -> dict | None:
    for step in PROFILE_STEPS:
        if step["field"] == field:
            return step

    return None


def get_first_missing_step(draft_data: dict) -> dict | None:
    for step in PROFILE_STEPS:
        if step["field"] not in draft_data:
            return step

    return None

PROFILE_FIELD_LABELS = {
    "house_type": "Тип дома",
    "region": "Регион",
    "climate_zone": "Климатическая зона",
    "water_source": "Источник воды",
    "heating_type": "Тип отопления",
    "has_gas": "Газ",
    "has_generator": "Генератор",
    "has_pool": "Бассейн",
    "has_basement": "Подвал",
    "has_plot": "Участок",
    "has_fireplace": "Камин",
    "involvement_level": "Уровень вовлечённости",
}

PROFILE_VALUE_LABELS = {
    "dacha": "дача",
    "pmzh": "дом для постоянного проживания",
    "well": "скважина",
    "kolodec": "колодец",
    "central": "центральное водоснабжение",
    "gas": "газовое",
    "electric": "электрическое",
    "solid_fuel": "твёрдотопливное",
    "north": "северная",
    "middle": "средняя",
    "south": "южная",
    "low": "низкий",
    "medium": "средний",
    "high": "высокий",
    True: "да",
    False: "нет",
}


def format_profile_summary(draft_data: dict) -> str:
    lines = []

    for step in PROFILE_STEPS:
        field = step["field"]
        value = draft_data.get(field)

        label = PROFILE_FIELD_LABELS.get(field, field)
        value_label = PROFILE_VALUE_LABELS.get(value, value)

        lines.append(f"- {label}: {value_label}")

    return "\n".join(lines)

def format_autosynced_memory_summary(records) -> str:
    if not records:
        return ""

    lines = [
        "",
        "Я также добавил в память дома базовые объекты из профиля:",
    ]

    for record in records:
        lines.append(f"- {record.component_name}")

    lines.extend(
        [
            "",
            "Пока у них нет дат обслуживания и интервалов — это нормально.",
            "Эти данные можно будет заполнить позже.",
        ]
    )

    return "\n".join(lines)

def is_confirmation_yes(message: str) -> bool:
    text = normalize_text(message)

    yes_words = [
        "да",
        "верно",
        "правильно",
        "все верно",
        "всё верно",
        "подтверждаю",
        "ок",
        "okay",
    ]

    return any(word in text for word in yes_words)


def is_confirmation_no(message: str) -> bool:
    text = normalize_text(message)

    no_words = [
        "нет",
        "неверно",
        "не правильно",
        "неправильно",
        "ошибка",
        "надо исправить",
        "хочу исправить",
    ]

    return any(word in text for word in no_words)

def start_profile_dialogue(
    db: Session,
    session: AgentSession
) -> AgentAskResponse:
    first_step = PROFILE_STEPS[0]

    update_agent_session(
        db=db,
        session=session,
        current_scenario="profile_creation",
        current_step=first_step["field"],
        draft_data={},
        is_active=True,
    )

    return AgentAskResponse(
        scenario="profile_creation",
        answer=(
            "Давайте сначала заполним профиль дома. "
            "Без него я не смогу давать персональные рекомендации.\n\n"
            + first_step["question"]
        ),
        action_required="answer_profile_question",
    )


def continue_profile_dialogue(
    db: Session,
    session: AgentSession,
    user_id: str,
    message: str
) -> AgentAskResponse:
    current_step = session.current_step
    draft_data = dict(session.draft_data or {})

    if not current_step:
        return start_profile_dialogue(db, session)

    if current_step == "confirm_profile":
        if is_confirmation_yes(message):
            try:
                profile_data = HouseProfileCreate(**draft_data)

                profile = create_profile(
                    db=db,
                    profile_data=profile_data,
                    user_id=user_id
                )

                autosynced_records = sync_profile_components_to_memory(
                    db=db,
                    profile=profile,
                )

            except HTTPException as error:
                return AgentAskResponse(
                    scenario="profile_creation",
                    answer=f"Не удалось создать профиль дома: {error.detail}",
                    action_required="check_profile_data",
                )

            update_agent_session(
                db=db,
                session=session,
                current_scenario="memory_offer",
                current_step="ask_memory_details",
                draft_data={},
                is_active=True,
            )

            return AgentAskResponse(
                scenario="profile_created",
                answer=(
                        "Профиль дома создан. Теперь я могу давать персональные рекомендации."
                        + format_autosynced_memory_summary(autosynced_records)
                        + "\n\nХотите сейчас добавить дополнительные объекты или уточнить данные обслуживания?"
                ),
                action_required="confirm_memory_creation",
            )

        if is_confirmation_no(message):
            first_step = PROFILE_STEPS[0]

            update_agent_session(
                db=db,
                session=session,
                current_scenario="profile_creation",
                current_step=first_step["field"],
                draft_data={},
                is_active=True,
            )

            return AgentAskResponse(
                scenario="profile_creation",
                answer=(
                    "Хорошо, давайте заполним профиль заново.\n\n"
                    + first_step["question"]
                ),
                action_required="answer_profile_question",
            )

        return AgentAskResponse(
            scenario="profile_creation",
            answer=(
                "Пожалуйста, подтвердите профиль: всё верно? Ответьте «да» или «нет».\n\n"
                + format_profile_summary(draft_data)
            ),
            action_required="confirm_profile",
        )

    extraction = extract_profile_fields_with_gigachat(
        current_step=current_step,
        user_message=message,
        draft_data=draft_data
    )

    extracted_fields = extraction.get("fields", {})

    for field, value in extracted_fields.items():
        draft_data[field] = value

    # Fallback: если GigaChat ничего не понял, пробуем старый простой парсер
    # только для текущего шага, чтобы не ломать демо при проблемах с API.
    if current_step not in draft_data:
        parsed_value = parse_profile_field(current_step, message)

        if parsed_value is not None:
            draft_data[current_step] = parsed_value

    if draft_data.get("heating_type") == "gas":
        draft_data["has_gas"] = True

    if current_step not in draft_data:
        step = get_step_by_field(current_step)

        clarification = extraction.get("clarification_question")

        return AgentAskResponse(
            scenario="profile_creation",
            answer=(
                clarification
                or "Я не смог уверенно распознать ответ.\n\n"
                + step["question"]
            ),
            action_required="answer_profile_question",
        )

    next_step = get_first_missing_step(draft_data)

    if next_step:
        update_agent_session(
            db=db,
            session=session,
            current_scenario="profile_creation",
            current_step=next_step["field"],
            draft_data=draft_data,
            is_active=True,
        )

        return AgentAskResponse(
            scenario="profile_creation",
            answer=next_step["question"],
            action_required="answer_profile_question",
        )

    update_agent_session(
        db=db,
        session=session,
        current_scenario="profile_creation",
        current_step="confirm_profile",
        draft_data=draft_data,
        is_active=True,
    )

    return AgentAskResponse(
        scenario="profile_confirmation",
        answer=(
            "Я собрал профиль дома. Проверьте, всё ли верно:\n\n"
            + format_profile_summary(draft_data)
            + "\n\nЕсли всё верно, ответьте «да». Если есть ошибка, ответьте «нет»."
        ),
        action_required="confirm_profile",
    )

def handle_profile_onboarding(
    db: Session,
    session: AgentSession,
    user_id: str,
    message: str
) -> AgentAskResponse:
    if session.current_scenario != "profile_creation":
        return start_profile_dialogue(db, session)

    return continue_profile_dialogue(
        db=db,
        session=session,
        user_id=user_id,
        message=message
    )