from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentSession, HouseMemory, HouseProfile
from app.schemas.agent import AgentAskResponse, AgentMemoryItem
from app.schemas.memory import HouseMemoryCreateItem
from app.services.memory_service import (
    create_or_update_memory_records,
    delete_memory_records_by_ids,
    sync_profile_components_to_memory,
    update_memory_by_component_type,
    update_memory_record_fields,
)
from app.services.profile_edit_service import (
    PROFILE_FIELD_LABELS,
    value_to_user_text,
)
from app.services.session_service import get_pending_action, reset_agent_session
from app.utils.date_utils import calculate_memory_status


def normalize_text(value: str | None) -> str:
    return str(value or "").lower().replace("ё", "е").strip()


def is_confirmation_no(message: str) -> bool:
    text = normalize_text(message)

    no_patterns = [
        "нет",
        "не надо",
        "не верно",
        "неверно",
        "отмена",
        "отмени",
        "стоп",
        "не сохраняй",
        "не добавляй",
        "не обновляй",
        "не подтверждаю",
    ]

    return any(pattern in text for pattern in no_patterns)


def is_confirmation_yes(message: str) -> bool:
    if is_confirmation_no(message):
        return False

    text = normalize_text(message)

    yes_patterns = [
        "да",
        "верно",
        "правильно",
        "подтверждаю",
        "сохрани",
        "сохранить",
        "добавь",
        "добавить",
        "обнови",
        "обновить",
        "ок",
        "окей",
        "хорошо",
        "можно",
        "согласен",
        "согласна",
    ]

    return any(pattern in text for pattern in yes_patterns)


def parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def convert_records_to_memory_context(
    records: list[HouseMemory],
) -> list[AgentMemoryItem]:
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


def _format_item_details(item: dict) -> list[str]:
    details = []

    if item.get("last_service_date"):
        details.append(f"дата последнего обслуживания: {item['last_service_date']}")
    else:
        details.append("дата последнего обслуживания не указана")

    if item.get("service_interval_days"):
        details.append(f"интервал обслуживания: {item['service_interval_days']} дней")
    else:
        details.append("интервал обслуживания не указан")

    if item.get("comment"):
        details.append(f"комментарий: {item['comment']}")

    return details


def build_memory_add_confirmation_answer(items: list[dict]) -> str:
    lines = [
        "Я понял так:",
        "",
        "Нужно добавить в память дома:",
    ]

    for item in items:
        name = item.get("component_name") or item.get("component_type") or "Объект"
        lines.append(f"- {name}")

        for detail in _format_item_details(item):
            lines.append(f"  • {detail}")

    lines.extend(["", "Добавить?"])

    return "\n".join(lines)


def build_memory_update_confirmation_answer(items: list[dict]) -> str:
    lines = [
        "Я понял так:",
        "",
        "Нужно обновить данные в памяти дома:",
    ]

    for item in items:
        name = item.get("component_name") or item.get("component_type") or "Объект"
        lines.append(f"- {name}")

        changes = []

        if item.get("last_service_date"):
            changes.append(f"дата последнего обслуживания: {item['last_service_date']}")

        if item.get("service_interval_days"):
            changes.append(f"интервал обслуживания: {item['service_interval_days']} дней")

        if item.get("comment"):
            changes.append(f"комментарий: {item['comment']}")

        if changes:
            for change in changes:
                lines.append(f"  • {change}")
        else:
            lines.append("  • детали изменения не указаны")

    lines.extend(["", "Сохранить?"])

    return "\n".join(lines)


def _apply_memory_add(
    db: Session,
    profile: HouseProfile,
    payload: dict,
) -> AgentAskResponse:
    items = payload.get("items") or []

    create_items = [
        HouseMemoryCreateItem(**item)
        for item in items
    ]

    records = create_or_update_memory_records(
        db=db,
        profile=profile,
        items=create_items,
    )

    lines = [
        f"- {record.component_name}: статус {record.status}"
        for record in records
    ]

    return AgentAskResponse(
        scenario="memory_created",
        answer=(
            "Готово, добавил в память дома:\n\n"
            + "\n".join(lines)
        ),
        memory_context=convert_records_to_memory_context(records),
    )


def _apply_memory_update(
    db: Session,
    profile: HouseProfile,
    payload: dict,
) -> AgentAskResponse:
    items = payload.get("items") or []
    updated_records = []

    for item in items:
        component_type = item.get("component_type")
        last_service_date = parse_iso_date(item.get("last_service_date"))

        if not component_type or last_service_date is None:
            continue

        updated_record = update_memory_by_component_type(
            db=db,
            profile=profile,
            component_type=component_type,
            component_name=item.get("component_name"),
            last_service_date=last_service_date,
            service_interval_days=item.get("service_interval_days"),
            comment=item.get("comment"),
        )

        updated_records.append(updated_record)

    if not updated_records:
        return AgentAskResponse(
            scenario="memory_update",
            answer=(
                "Не смог применить изменение: не хватает объекта или даты обслуживания. "
                "Попробуйте написать ещё раз, например: «Я почистил септик сегодня»."
            ),
            action_required="provide_component_and_service_date",
        )

    lines = []

    for record in updated_records:
        if record.next_service_date:
            lines.append(
                f"- {record.component_name}: обслужено {record.last_service_date}, "
                f"следующий срок {record.next_service_date}, статус {record.status}"
            )
        else:
            lines.append(
                f"- {record.component_name}: обслужено {record.last_service_date}, "
                f"интервал обслуживания неизвестен, статус {record.status}"
            )

    return AgentAskResponse(
        scenario="memory_updated",
        answer=(
            "Готово, обновил память дома:\n\n"
            + "\n".join(lines)
        ),
        memory_context=convert_records_to_memory_context(updated_records),
    )

def _apply_memory_delete(
    db: Session,
    profile: HouseProfile,
    payload: dict,
) -> AgentAskResponse:
    memory_ids = payload.get("memory_ids") or []

    deleted_records = delete_memory_records_by_ids(
        db=db,
        profile=profile,
        memory_ids=memory_ids,
    )

    if not deleted_records:
        return AgentAskResponse(
            scenario="memory_delete",
            answer="Не нашёл объекты для удаления. Ничего не меняю.",
        )

    lines = [
        "Готово, удалил из памяти дома:",
        "",
    ]

    for record in deleted_records:
        lines.append(f"- {record.component_name}")

    return AgentAskResponse(
        scenario="memory_deleted",
        answer="\n".join(lines),
    )

def _apply_memory_edit(
    db: Session,
    profile: HouseProfile,
    payload: dict,
) -> AgentAskResponse:
    memory_id = payload.get("memory_id")
    updates = payload.get("updates") or {}

    if not memory_id or not updates:
        return AgentAskResponse(
            scenario="memory_edit",
            answer="Не нашёл изменения для сохранения. Ничего не меняю.",
        )

    parsed_updates = dict(updates)

    if "last_service_date" in parsed_updates:
        parsed_updates["last_service_date"] = parse_iso_date(
            parsed_updates["last_service_date"]
        )

        if parsed_updates["last_service_date"] is None:
            parsed_updates.pop("last_service_date", None)

    updated_record = update_memory_record_fields(
        db=db,
        profile=profile,
        memory_id=memory_id,
        updates=parsed_updates,
    )

    lines = [
        "Готово, обновил объект в памяти дома:",
        "",
        f"- {updated_record.component_name}",
        f"  Статус: {updated_record.status}",
    ]

    if updated_record.last_service_date:
        lines.append(f"  Последнее обслуживание: {updated_record.last_service_date}")

    if updated_record.service_interval_days:
        lines.append(f"  Интервал обслуживания: {updated_record.service_interval_days} дней")

    if updated_record.next_service_date:
        lines.append(f"  Следующее обслуживание: {updated_record.next_service_date}")

    if updated_record.comment:
        lines.append(f"  Комментарий: {updated_record.comment}")

    return AgentAskResponse(
        scenario="memory_edited",
        answer="\n".join(lines),
        memory_context=convert_records_to_memory_context([updated_record]),
    )

def format_autosynced_memory_records(records: list[HouseMemory]) -> str:
    if not records:
        return ""

    lines = [
        "",
        "Также я добавил в память дома новые базовые объекты из профиля:",
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


def _apply_profile_edit(
    db: Session,
    profile: HouseProfile,
    payload: dict,
) -> AgentAskResponse:
    changes = payload.get("changes") or {}

    if not changes:
        return AgentAskResponse(
            scenario="profile_edit",
            answer="Не нашёл изменений профиля для сохранения. Ничего не меняю.",
        )

    lines = [
        "Готово, я обновил профиль дома:",
    ]

    for field, new_value in changes.items():
        if not hasattr(profile, field):
            continue

        setattr(profile, field, new_value)

        label = PROFILE_FIELD_LABELS.get(field, field)
        lines.append(f"- {label}: {value_to_user_text(field, new_value)}")

    db.commit()
    db.refresh(profile)

    autosynced_records = sync_profile_components_to_memory(
        db=db,
        profile=profile,
    )

    answer = "\n".join(lines) + format_autosynced_memory_records(autosynced_records)

    return AgentAskResponse(
        scenario="profile_updated",
        answer=answer,
    )

def handle_pending_confirmation(
    db: Session,
    session: AgentSession,
    profile: HouseProfile,
    message: str,
) -> AgentAskResponse:
    pending_action = get_pending_action(session)

    if not pending_action:
        reset_agent_session(db, session)

        return AgentAskResponse(
            scenario="confirmation_error",
            answer="Не нашёл действие для подтверждения. Напишите запрос ещё раз.",
        )

    if is_confirmation_no(message):
        reset_agent_session(db, session)

        return AgentAskResponse(
            scenario="action_cancelled",
            answer="Хорошо, ничего не меняю.",
        )

    if not is_confirmation_yes(message):
        return AgentAskResponse(
            scenario="awaiting_confirmation",
            answer=(
                "Подтвердите действие: ответьте «да», чтобы сохранить, "
                "или «нет», чтобы отменить."
            ),
            action_required="confirm_action",
        )

    action_type = pending_action.get("type")
    payload = pending_action.get("payload") or {}

    if action_type == "memory_add":
        response = _apply_memory_add(
            db=db,
            profile=profile,
            payload=payload,
        )
    elif action_type == "memory_update":
        response = _apply_memory_update(
            db=db,
            profile=profile,
            payload=payload,
        )
    elif action_type == "memory_edit":
        response = _apply_memory_edit(
            db=db,
            profile=profile,
            payload=payload,
        )
    elif action_type == "memory_delete":
        response = _apply_memory_delete(
            db=db,
            profile=profile,
            payload=payload,
        )
    elif action_type == "profile_edit":
        response = _apply_profile_edit(
            db=db,
            profile=profile,
            payload=payload,
        )
    else:
        reset_agent_session(db, session)

        return AgentAskResponse(
            scenario="confirmation_error",
            answer="Неизвестное действие для подтверждения. Ничего не меняю.",
        )

    reset_agent_session(db, session)

    return response