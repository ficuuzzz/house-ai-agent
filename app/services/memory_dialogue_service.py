from sqlalchemy.orm import Session

from app.db.models import AgentSession, HouseProfile
from app.schemas.agent import AgentAskResponse, AgentMemoryItem
from app.schemas.memory import HouseMemoryCreateItem
from app.services.gigachat_memory_extraction_service import extract_memory_items_with_gigachat
from app.services.memory_service import (
    create_or_update_memory_records,
    update_memory_by_component_type,
)
from app.services.session_service import (
    reset_agent_session,
    set_pending_action,
    update_agent_session,
)
from app.utils.date_utils import calculate_memory_status
from app.services.confirmation_service import (
    build_memory_add_confirmation_answer,
    build_memory_update_confirmation_answer,
)

from datetime import date


def normalize_text(value: str) -> str:
    return value.lower().replace("ё", "е").strip()


def is_yes(message: str) -> bool:
    text = normalize_text(message)

    # Сначала защищаемся от отрицаний.
    if is_no(message):
        return False

    yes_patterns = [
        "да",
        "хочу добавить",
        "давай",
        "можно",
        "конечно",
        "ок",
        "согласен",
        "согласна",
        "добавим",
        "да, хочу",
    ]

    return any(pattern in text for pattern in yes_patterns)


def is_no(message: str) -> bool:
    text = normalize_text(message)

    no_patterns = [
        "нет",
        "не хочу",
        "не надо",
        "не сейчас",
        "потом",
        "позже",
        "пропустить",
        "пропусти",
        "давай позже",
        "сейчас не хочу",
    ]

    return any(pattern in text for pattern in no_patterns)

def is_cancel_current_dialogue_request(message: str) -> bool:
    text = normalize_text(message)

    cancel_patterns = [
        "выйти",
        "выход",
        "отмена",
        "отмени",
        "стоп",
        "закончить",
        "завершить",
        "назад",
        "хватит",
        "не добавлять",
        "не хочу добавлять",
        "не надо добавлять",
        "прекратить",
        "прекрати",
    ]

    return any(pattern in text for pattern in cancel_patterns)

def start_memory_dialogue(
    db: Session,
    session: AgentSession
) -> AgentAskResponse:
    update_agent_session(
        db=db,
        session=session,
        current_scenario="memory_creation",
        current_step="collect_memory_items",
        draft_data={},
        is_active=True,
    )

    return AgentAskResponse(
        scenario="memory_creation",
        answer=(
            "Хорошо. Напишите, какие дополнительные объекты нужно добавить "
            "или по каким объектам хотите указать данные обслуживания.\n\n"
            "Можно одной фразой, например: "
            "«Добавь насос и септик. Насос проверяли месяц назад, "
            "септик чистили весной»."
        ),
        action_required="provide_memory_items",
    )


def handle_memory_offer(
    db: Session,
    session: AgentSession,
    message: str
) -> AgentAskResponse:
    if is_no(message):
        reset_agent_session(db, session)

        return AgentAskResponse(
            scenario="memory_skipped",
            answer=(
                "Хорошо, пропустим заполнение памяти дома. "
                "Вы сможете добавить обслуживаемые объекты позже."
            ),
        )

    if is_yes(message):
        return start_memory_dialogue(db, session)

    return AgentAskResponse(
        scenario="memory_offer",
        answer=(
            "Хотите сейчас добавить дополнительные объекты "
            "или уточнить данные обслуживания? Ответьте «да» или «нет»."
        ),
        action_required="confirm_memory_creation",
    )


def convert_records_to_memory_context(records) -> list[AgentMemoryItem]:
    result = []

    for record in records:
        actual_status = calculate_memory_status(record.next_service_date)

        result.append(
            AgentMemoryItem(
                memory_id=record.memory_id,
                component_type=record.component_type,
                component_name=record.component_name,
                status=actual_status,
                last_service_date=record.last_service_date,
                service_interval_days=record.service_interval_days,
                next_service_date=record.next_service_date,
                comment=record.comment,
            )
        )

    return result


def continue_memory_creation(
    db: Session,
    session: AgentSession,
    profile: HouseProfile,
    message: str
) -> AgentAskResponse:
    if is_cancel_current_dialogue_request(message):
        reset_agent_session(db, session)

        return AgentAskResponse(
            scenario="memory_creation_cancelled",
            answer=(
                "Хорошо, вышел из заполнения памяти дома. "
                "Ничего не добавляю и не меняю."
            ),
        )

    extraction = extract_memory_items_with_gigachat(message)
    items = extraction.get("items", [])

    if not items:
        clarification = extraction.get("clarification_question")

        return AgentAskResponse(
            scenario="memory_creation",
            answer=(
                clarification
                or "Я не смог уверенно понять, какие обслуживаемые объекты нужно добавить. "
                   "Напишите, например: «насос, фильтр воды и септик»."
            ),
            action_required="provide_memory_items",
        )

    set_pending_action(
        db=db,
        session=session,
        action_type="memory_add",
        payload={"items": items},
    )

    return AgentAskResponse(
        scenario="awaiting_confirmation",
        answer=build_memory_add_confirmation_answer(items),
        action_required="confirm_action",
    )

def parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def continue_memory_update(
    db: Session,
    session: AgentSession,
    profile: HouseProfile,
    message: str,
    component_type_hint: str | None = None,
) -> AgentAskResponse:
    if is_cancel_current_dialogue_request(message):
        reset_agent_session(db, session)

        return AgentAskResponse(
            scenario="memory_update_cancelled",
            answer=(
                "Хорошо, вышел из обновления памяти дома. "
                "Ничего не добавляю и не меняю."
            ),
        )

    draft_data = dict(session.draft_data or {})
    if component_type_hint:
        draft_data["component_type"] = component_type_hint

    extraction = extract_memory_items_with_gigachat(message)
    items = extraction.get("items", [])

    if not items and "component_type" in draft_data:
        items = [
            {
                "component_type": draft_data["component_type"],
                "component_name": None,
                "last_service_date": None,
                "service_interval_days": None,
                "comment": None,
            }
        ]

    if not items:
        update_agent_session(
            db=db,
            session=session,
            current_scenario="memory_update",
            current_step="wait_component_and_service_date",
            draft_data=draft_data,
            is_active=True,
        )

        return AgentAskResponse(
            scenario="memory_update",
            answer=(
                "Я понял, что вы хотите обновить память дома, "
                "но не смог определить компонент. Напишите, например: "
                "«Я заменил фильтр воды сегодня» или «Я почистил септик вчера»."
            ),
            action_required="provide_component_and_service_date",
        )

    pending_items = []
    missing_date_components = []

    for item in items:
        component_type = item.get("component_type") or draft_data.get("component_type")
        component_name = item.get("component_name")
        last_service_date = parse_iso_date(item.get("last_service_date"))

        if component_type:
            draft_data["component_type"] = component_type

        if last_service_date is None:
            missing_date_components.append(component_name or component_type)
            continue

        pending_items.append(
            {
                "component_type": component_type,
                "component_name": component_name,
                "last_service_date": last_service_date.isoformat(),
                "service_interval_days": item.get("service_interval_days"),
                "comment": item.get("comment"),
            }
        )

    if not pending_items:
        update_agent_session(
            db=db,
            session=session,
            current_scenario="memory_update",
            current_step="wait_service_date",
            draft_data=draft_data,
            is_active=True,
        )

        component_text = ", ".join(str(item) for item in missing_date_components)

        return AgentAskResponse(
            scenario="memory_update",
            answer=(
                f"Я понял компонент: {component_text}. "
                "Но мне нужна дата обслуживания. "
                "Напишите, например: «сегодня», «вчера», "
                "«10 мая» или «сегодня, следующий раз через 90 дней»."
            ),
            action_required="provide_service_date",
        )

    set_pending_action(
        db=db,
        session=session,
        action_type="memory_update",
        payload={"items": pending_items},
    )

    return AgentAskResponse(
        scenario="awaiting_confirmation",
        answer=build_memory_update_confirmation_answer(pending_items),
        action_required="confirm_action",
    )