from sqlalchemy.orm import Session

from app.services.checklist_service import (
    get_month_checklist,
    get_month_user_name,
    get_season_for_month,
    normalize_month,
)
from app.services.checklist_answer_service import build_checklist_answer_with_gigachat
from app.services.scenario_router import detect_scenario, extract_month
from app.db.models import HouseMemory, HouseProfile
from app.schemas.agent import AgentAskResponse, AgentMemoryItem
from app.schemas.rag import RagSearchItem
from app.services.qdrant_service import search_relevant_knowledge_base
from app.services.specialist_service import analyze_specialist_recommendation
from app.utils.date_utils import calculate_memory_status
from app.services.gigachat_service import generate_answer
from app.services.dialogue_service import handle_profile_onboarding
from app.services.session_service import (
    get_or_create_agent_session,
    set_pending_action,
)
from app.services.profile_edit_service import (
    build_profile_edit_confirmation_answer,
    extract_profile_changes_with_gigachat,
)
from app.services.memory_edit_service import (
    build_memory_edit_ambiguous_answer,
    build_memory_edit_confirmation_answer,
    build_memory_edit_not_found_answer,
    extract_memory_edit_with_gigachat,
    find_memory_records_for_edit,
)
from app.services.confirmation_service import handle_pending_confirmation
from app.services.gigachat_intent_service import classify_intent_with_gigachat
from app.services.memory_dialogue_service import (
    continue_memory_creation,
    continue_memory_update,
    handle_memory_offer,
    start_memory_dialogue,
)
from app.services.memory_service import get_memory_by_house_id
from app.services.memory_delete_service import (
    build_memory_delete_ambiguous_answer,
    build_memory_delete_confirmation_answer,
    build_memory_delete_not_found_answer,
    extract_memory_delete_target,
    find_memory_records_for_delete,
)

COMPONENT_QUERY_KEYWORDS = {
    "generator": [
        "генератор",
        "электричество",
        "свет",
        "резервное питание",
    ],
    "pump": [
        "насос",
        "напор",
        "давление",
        "вода идет рывками",
        "вода идёт рывками",
        "нет воды",
    ],
    "water_filter": [
        "фильтр",
        "вода",
        "грязная вода",
        "мутная вода",
        "запах воды",
    ],
    "septic": [
        "септик",
        "канализация",
        "запах",
        "стоки",
    ],
    "pool": [
        "бассейн",
        "вода в бассейне",
    ],
    "basement": [
        "подвал",
        "сырость",
        "влажность",
        "плесень",
    ],
    "fireplace": [
        "камин",
        "дым",
        "дымоход",
    ],
    "chimney": [
        "дымоход",
        "тяга",
        "дым",
    ],
    "roof": [
        "крыша",
        "кровля",
        "протечка",
    ],
    "gutter": [
        "водосток",
        "желоб",
        "ливневка",
        "ливнёвка",
    ],
    "drainage": [
        "дренаж",
        "лужи",
        "подтопление",
        "вода на участке",
    ],
}
READ_ONLY_PRIORITY_SCENARIOS = {
    "profile_view",
    "memory_list",
}

def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    return str(value).lower().replace("ё", "е")

def get_message_date_context(message: str) -> dict:
    explicit_month = extract_month(message)
    target_month = normalize_month(explicit_month)
    target_season = get_season_for_month(target_month)

    return {
        "explicit_month": explicit_month,
        "target_month": target_month,
        "target_month_user": get_month_user_name(target_month),
        "target_season": target_season,
    }

def get_relevant_memory_records(
    db: Session,
    profile: HouseProfile,
    message: str
) -> list[HouseMemory]:
    normalized_message = normalize_text(message)

    all_memory = (
        db.query(HouseMemory)
        .filter(HouseMemory.house_id == profile.house_id)
        .all()
    )

    matched_component_types = set()

    for component_type, keywords in COMPONENT_QUERY_KEYWORDS.items():
        for keyword in keywords:
            if normalize_text(keyword) in normalized_message:
                matched_component_types.add(component_type)

    relevant_memory = [
        record for record in all_memory
        if record.component_type in matched_component_types
    ]


    if matched_component_types and not relevant_memory:
        return []

    # Если вопрос общий, тогда можно показать проблемные записи памяти.
    if not relevant_memory:
        for record in all_memory:
            actual_status = calculate_memory_status(record.next_service_date)

            if actual_status in ["overdue", "soon", "no_data"]:
                record.status = actual_status
                relevant_memory.append(record)

    return relevant_memory


def convert_memory_to_response_items(
    memory_records: list[HouseMemory]
) -> list[AgentMemoryItem]:
    result = []

    for record in memory_records:
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


def build_llm_prompt(
    message,
    profile,
    memory_context,
    rag_items,
    recommend_specialist,
    specialist_reason,
    date_context: dict | None = None,
):
    context_blocks = []

    for item in rag_items:
        context_blocks.append(
            f"""
ЗАГОЛОВОК: {item.get('title')}
МЕСЯЦ: {item.get('month')}
СЕЗОН: {item.get('season')}
ОПИСАНИЕ ЗАДАЧИ: {item.get('task_description')}ИНСТРУКЦИИ: {item.get('instructions')}
НАЗНАЧЕНИЕ: {item.get('purpose')}
УСЛОВИЯ ПРИМЕНЕНИЯ: {item.get('conditions')}
ПРИОРИТЕТ: {item.get('priority')}
"""
        )

    context_text = "\n\n".join(context_blocks)
    date_context = date_context or {}
    target_month_user = date_context.get("target_month_user") or "текущий месяц"
    target_season = date_context.get("target_season") or "текущий сезон"

    specialist_context = (
        "да" if recommend_specialist else "нет"
    )

    specialist_reason_text = (
        specialist_reason
        if specialist_reason
        else "причина не указана"
    )

    prompt = f"""
Ты AI-агент по обслуживанию дома.

Профиль дома:
- Тип: {profile.house_type}
- Регион: {profile.region}
- Климат: {profile.climate_zone}
- Вода: {profile.water_source}
- Отопление: {profile.heating_type}
- Газ: {profile.has_gas}
- Генератор: {profile.has_generator}
- Бассейн: {profile.has_pool}
- Подвал: {profile.has_basement}
- Участок: {profile.has_plot}
- Камин: {profile.has_fireplace}

Текущий временной контекст:
- Месяц: {target_month_user}
- Сезон: {target_season}

Внутреннее решение по специалисту:
- Нужно рекомендовать специалиста: {specialist_context}
- Причина: {specialist_reason_text}

Память дома:
{memory_context}

Найденные знания:
{context_text}

Вопрос:
{message}

Правила ответа:
- отвечай на русском языке
- используй Markdown-разметку
- не используй JSON
- не упоминай слова: RAG, KnowledgeBase, backend, payload, metadata
- не показывай технические поля, id, score, component_type
- не пиши длинное вступление
- сначала дай практический ответ, потом пояснение
- используй короткие абзацы
- если есть список действий, делай его нумерованным
- не давай больше 5–7 действий за раз
- учитывай текущий месяц и сезон
- если вопрос сезонный, не советуй действия для противоположного сезона без явной причины
- если пользователь спрашивает про конкретную проблему, сначала отвечай по проблеме, а месяц используй как дополнительный контекст
- если найденные знания относятся к другому сезону, используй их осторожно и явно объясняй, что это общая рекомендация
- если данных недостаточно, честно скажи об этом
- если "Нужно рекомендовать специалиста: да", всё равно дай пользователю полезные безопасные шаги
- если "Нужно рекомендовать специалиста: да", объясняй задачу через безопасный подход: что можно проверить визуально, что отключить, что не трогать, какие признаки опасности искать
- если "Нужно рекомендовать специалиста: да", не представляй самостоятельный ремонт как гарантированно безопасный
- если "Нужно рекомендовать специалиста: да", отделяй безопасные действия от действий, которые лучше доверить специалисту
- если "Нужно рекомендовать специалиста: да", не давай инструкции, которые требуют квалификации, специнструмента или работы с опасными системами без предупреждения о риске
- если "Нужно рекомендовать специалиста: да", объясни, почему лучше обратиться к специалисту
- если "Нужно рекомендовать специалиста: да", раздел "Когда лучше вызвать специалиста" обязателен
- если "Нужно рекомендовать специалиста: нет", раздел про специалиста можно не добавлять, если в вопросе нет явного риска


Формат ответа выбирай по смыслу вопроса:

1. Если пользователь задаёт простой вопрос
Например:
- можно ли разжигать камин весной?
- как часто менять фильтр?
- что значит no_data?

Ответь коротко:
- 1–2 абзаца
- при необходимости 2–3 пункта
- без обязательных разделов "Коротко", "Что сделать сейчас", "Почему это важно"

2. Если пользователь просит инструкцию
Например:
- как безопасно разжечь камин?
- как проверить генератор?
- как подготовить бассейн?

Используй структуру:
### Коротко
### Что сделать сейчас
### На что обратить внимание

Раздел "Когда лучше вызвать специалиста" добавляй только если есть риск или внутреннее решение требует специалиста.

3. Если пользователь описывает проблему
Например:
- течёт вода, что делать?
- насос шумит
- пахнет из септика
- камин дымит

Используй структуру:
### Коротко
### Что проверить сначала
### Что можно сделать безопасно
### Когда лучше вызвать специалиста

4. Если пользователь спрашивает сезонную рекомендацию
Например:
- что делать с генератором летом?
- как подготовить дом к зиме?
- что проверить весной?

Используй структуру:
### Коротко
### Что актуально сейчас
### Что можно запланировать

5. Если "Нужно рекомендовать специалиста: да"
- всё равно дай полезные безопасные шаги
- объясняй через безопасный подход: что можно проверить визуально, что отключить, что не трогать
- не представляй самостоятельный ремонт как гарантированно безопасный
- отделяй безопасные действия от того, что лучше доверить специалисту
- раздел "Когда лучше вызвать специалиста" обязателен

Не используй один и тот же шаблон для всех ответов.
Если вопрос простой — отвечай просто.
Если вопрос практический или рискованный — структурируй ответ.
"""

    return prompt
    
    


def ask_agent(
    db: Session,
    profile: HouseProfile | None,
    message: str,
    user_id: str
) -> AgentAskResponse:
    session = get_or_create_agent_session(
        db=db,
        user_id=user_id
    )

    if not profile:
        return handle_profile_onboarding(
            db=db,
            session=session,
            user_id=user_id,
            message=message
        )

    if session.current_scenario == "awaiting_confirmation":
        return handle_pending_confirmation(
            db=db,
            session=session,
            profile=profile,
            message=message,
        )

    if session.current_scenario == "memory_offer":
        return handle_memory_offer(
            db=db,
            session=session,
            message=message
        )

    if session.current_scenario == "memory_creation":
        return continue_memory_creation(
            db=db,
            session=session,
            profile=profile,
            message=message
        )

    if session.current_scenario == "memory_update":
        return continue_memory_update(
            db=db,
            session=session,
            profile=profile,
            message=message
        )

    backend_detected = detect_scenario(message)

    # Простые read-only сценарии определяем backend-логикой до GigaChat.
    # Это защищает от ситуации, когда фразу "покажи что есть в доме"
    # LLM ошибочно воспринимает как добавление объектов в HouseMemory.
    if backend_detected.scenario in READ_ONLY_PRIORITY_SCENARIOS:
        detected = backend_detected
    else:
        llm_detected = classify_intent_with_gigachat(
            message=message,
            has_profile=profile is not None,
            current_scenario=session.current_scenario,
            current_step=session.current_step,
        )

        detected = llm_detected or backend_detected
    if detected.scenario == "memory_list":
        memory_records = get_memory_by_house_id(
            db=db,
            house_id=profile.house_id,
        )

        return AgentAskResponse(
            scenario="memory_list",
            answer=build_memory_list_answer(memory_records),
            memory_context=convert_memory_to_response_items(memory_records),
        )

    if detected.scenario in {"memory_edit", "memory_update"}:
        edit_data = extract_memory_edit_with_gigachat(message)

        target = edit_data.get("target")
        updates = edit_data.get("updates") or {}

        if not target or not updates:
            return AgentAskResponse(
                scenario="memory_edit",
                answer=(
                    "Я понял, что нужно изменить объект в памяти дома, "
                    "но не смог уверенно определить объект или поле изменения. "
                    "Напишите, например: «поставь генератору интервал 365 дней» "
                    "или «добавь комментарий к септику: чистить весной»."
                ),
                action_required="provide_memory_edit_details",
            )

        records_to_edit = find_memory_records_for_edit(
            db=db,
            profile=profile,
            target=target,
        )

        if not records_to_edit:
            return AgentAskResponse(
                scenario="memory_edit",
                answer=build_memory_edit_not_found_answer(target),
            )

        if len(records_to_edit) > 1:
            return AgentAskResponse(
                scenario="memory_edit",
                answer=build_memory_edit_ambiguous_answer(records_to_edit),
                action_required="clarify_memory_edit_target",
            )

        record_to_edit = records_to_edit[0]

        set_pending_action(
            db=db,
            session=session,
            action_type="memory_edit",
            payload={
                "memory_id": record_to_edit.memory_id,
                "updates": updates,
            },
        )

        return AgentAskResponse(
            scenario="awaiting_confirmation",
            answer=build_memory_edit_confirmation_answer(
                record=record_to_edit,
                updates=updates,
            ),
            action_required="confirm_action",
        )

    if detected.scenario == "memory_delete":
        target = extract_memory_delete_target(message)

        if not target:
            return AgentAskResponse(
                scenario="memory_delete",
                answer=(
                    "Я понял, что нужно удалить объект из памяти дома, "
                    "но не понял какой именно. Напишите, например: "
                    "«удали холодильник из памяти»."
                ),
                action_required="provide_memory_delete_target",
            )

        records_to_delete = find_memory_records_for_delete(
            db=db,
            profile=profile,
            target=target,
        )

        if not records_to_delete:
            return AgentAskResponse(
                scenario="memory_delete",
                answer=build_memory_delete_not_found_answer(target),
            )

        if len(records_to_delete) > 1:
            return AgentAskResponse(
                scenario="memory_delete",
                answer=build_memory_delete_ambiguous_answer(records_to_delete),
                action_required="clarify_memory_delete_target",
            )

        set_pending_action(
            db=db,
            session=session,
            action_type="memory_delete",
            payload={
                "memory_ids": [
                    record.memory_id
                    for record in records_to_delete
                ]
            },
        )

        return AgentAskResponse(
            scenario="awaiting_confirmation",
            answer=build_memory_delete_confirmation_answer(records_to_delete),
            action_required="confirm_action",
        )

    if detected.scenario == "profile_view":
        return AgentAskResponse(
            scenario="profile_view",
            answer=build_profile_answer(profile),
            profile=build_profile_dict(profile),
        )

    if detected.scenario == "profile_edit":
        changes = extract_profile_changes_with_gigachat(
            message=message,
            profile=profile,
        )

        if not changes:
            return AgentAskResponse(
                scenario="profile_edit",
                answer=(
                    "Я понял, что вы хотите изменить профиль дома, "
                    "но не смог уверенно определить, что именно поменять. "
                    "Напишите, например: «измени отопление на электрическое» "
                    "или «добавь, что у меня есть генератор»."
                ),
                action_required="provide_profile_changes",
            )

        set_pending_action(
            db=db,
            session=session,
            action_type="profile_edit",
            payload={"changes": changes},
        )

        return AgentAskResponse(
            scenario="awaiting_confirmation",
            answer=build_profile_edit_confirmation_answer(
                profile=profile,
                changes=changes,
            ),
            action_required="confirm_action",
        )

    if detected.scenario == "checklist_month":
        checklist = get_month_checklist(
            db=db,
            profile=profile,
            month=detected.month,
        )

        answer = build_checklist_answer_with_gigachat(
            checklist=checklist,
            profile=profile,
        )

        return AgentAskResponse(
            scenario="checklist_month",
            answer=answer,
            checklist=checklist.model_dump(),
        )

    if detected.scenario == "memory_creation":
        return continue_memory_creation(
            db=db,
            session=session,
            profile=profile,
            message=message
        )

    if detected.scenario == "memory_update":
        return continue_memory_update(
            db=db,
            session=session,
            profile=profile,
            message=message,
            component_type_hint=detected.component_type,
        )

    date_context = get_message_date_context(message)

    rag_items = search_relevant_knowledge_base(
        query=message,
        profile=profile,
        limit=5,
        month=date_context["target_month"],
        season=date_context["target_season"],
    )

    specialist_decision = analyze_specialist_recommendation(
        query=message,
        items=rag_items
    )

    memory_records = get_relevant_memory_records(
        db=db,
        profile=profile,
        message=message
    )

    memory_context = convert_memory_to_response_items(memory_records)

    db.commit()

    prompt = build_llm_prompt(
        message=message,
        profile=profile,
        memory_context=memory_context,
        rag_items=rag_items,
        recommend_specialist=specialist_decision["recommend_specialist"],
        specialist_reason=specialist_decision["specialist_reason"],
        date_context=date_context,
    )

    answer = generate_answer(prompt)

    return AgentAskResponse(
        scenario="rag_answer",
        answer=answer,
        recommend_specialist=specialist_decision["recommend_specialist"],
        specialist_reason=specialist_decision["specialist_reason"],
        memory_context=memory_context,
        rag_items=[
            RagSearchItem(**item)
            for item in rag_items
        ],
    )
def build_profile_dict(profile: HouseProfile) -> dict:
    return {
        "house_id": profile.house_id,
        "user_id": profile.user_id,
        "house_type": profile.house_type,
        "region": profile.region,
        "climate_zone": profile.climate_zone,
        "water_source": profile.water_source,
        "heating_type": profile.heating_type,
        "has_gas": profile.has_gas,
        "has_generator": profile.has_generator,
        "has_pool": profile.has_pool,
        "has_basement": profile.has_basement,
        "has_plot": profile.has_plot,
        "has_fireplace": profile.has_fireplace,
        "involvement_level": profile.involvement_level,
    }


def bool_to_text(value: bool) -> str:
    return "есть" if value else "нет"


def build_profile_lines(profile: HouseProfile) -> list[str]:
    return [
        f"Тип дома: {profile.house_type}",
        f"Регион: {profile.region}",
        f"Климатическая зона: {profile.climate_zone}",
        f"Источник воды: {profile.water_source}",
        f"Тип отопления: {profile.heating_type}",
        f"Газ: {bool_to_text(profile.has_gas)}",
        f"Генератор: {bool_to_text(profile.has_generator)}",
        f"Бассейн: {bool_to_text(profile.has_pool)}",
        f"Подвал: {bool_to_text(profile.has_basement)}",
        f"Участок: {bool_to_text(profile.has_plot)}",
        f"Камин: {bool_to_text(profile.has_fireplace)}",
        f"Уровень вовлечённости: {profile.involvement_level}",
    ]


def build_profile_answer(profile: HouseProfile) -> str:
    return (
        "Вот сохранённый профиль вашего дома:\n\n"
        + "\n".join(build_profile_lines(profile))
    )


def format_date_for_user(value) -> str:
    if value is None:
        return "не указана"

    return str(value)


def status_to_user_text(status: str) -> str:
    mapping = {
        "ok": "в порядке",
        "soon": "скоро обслуживать",
        "overdue": "просрочено",
        "no_data": "нет данных",
    }

    return mapping.get(status, status)


def split_memory_records_by_status(
    memory_records: list[HouseMemory],
) -> dict[str, list[HouseMemory]]:
    groups = {
        "overdue": [],
        "soon": [],
        "no_data": [],
        "ok": [],
    }

    for record in memory_records:
        actual_status = calculate_memory_status(record.next_service_date)
        groups.setdefault(actual_status, []).append(record)

    return groups


def format_memory_record_short(record: HouseMemory) -> str:
    actual_status = calculate_memory_status(record.next_service_date)

    if actual_status == "overdue":
        if record.next_service_date:
            return (
                f"- {record.component_name} — срок обслуживания уже прошёл "
                f"({record.next_service_date})"
            )

        return f"- {record.component_name} — обслуживание просрочено"

    if actual_status == "soon":
        if record.next_service_date:
            return (
                f"- {record.component_name} — скоро нужно обслужить "
                f"(до {record.next_service_date})"
            )

        return f"- {record.component_name} — скоро нужно обслужить"

    if actual_status == "no_data":
        return (
            f"- {record.component_name} — нет данных об обслуживании. "
            "Лучше указать дату последнего обслуживания и интервал."
        )

    if record.next_service_date:
        return (
            f"- {record.component_name} — всё в порядке, "
            f"следующее обслуживание {record.next_service_date}"
        )

    return f"- {record.component_name} — всё в порядке"


def format_memory_record_details(record: HouseMemory) -> list[str]:
    details = []

    if record.last_service_date:
        details.append(f"  Последнее обслуживание: {record.last_service_date}")

    if record.service_interval_days:
        details.append(f"  Интервал: {record.service_interval_days} дней")

    if record.next_service_date:
        details.append(f"  Следующее обслуживание: {record.next_service_date}")

    if record.comment:
        details.append(f"  Комментарий: {record.comment}")

    return details


def build_memory_list_answer(memory_records: list[HouseMemory]) -> str:
    if not memory_records:
        return (
            "В памяти дома пока нет обслуживаемых объектов.\n\n"
            "Можно добавить, например: генератор, септик, насос, фильтр воды, "
            "бассейн, камин или любой другой объект, за которым нужно следить."
        )

    groups = split_memory_records_by_status(memory_records)

    total_count = len(memory_records)
    overdue_count = len(groups["overdue"])
    soon_count = len(groups["soon"])
    no_data_count = len(groups["no_data"])
    ok_count = len(groups["ok"])

    lines = [
        "По памяти дома вижу такую картину.",
        "",
        f"Сейчас в памяти {total_count} объект(ов).",
    ]

    attention_count = overdue_count + soon_count + no_data_count

    if attention_count == 0:
        lines.append("Срочных проблем по обслуживанию не видно.")
    else:
        attention_parts = []

        if overdue_count:
            attention_parts.append(f"просрочено: {overdue_count}")

        if soon_count:
            attention_parts.append(f"скоро обслуживать: {soon_count}")

        if no_data_count:
            attention_parts.append(f"без данных: {no_data_count}")

        lines.append("Что требует внимания: " + ", ".join(attention_parts) + ".")

    if groups["overdue"]:
        lines.extend(["", "Просрочено:"])

        for record in groups["overdue"]:
            lines.append(format_memory_record_short(record))
            lines.extend(format_memory_record_details(record))

    if groups["soon"]:
        lines.extend(["", "Скоро обслуживать:"])

        for record in groups["soon"]:
            lines.append(format_memory_record_short(record))
            lines.extend(format_memory_record_details(record))

    if groups["no_data"]:
        lines.extend(["", "Не хватает данных:"])

        for record in groups["no_data"]:
            lines.append(format_memory_record_short(record))
            lines.extend(format_memory_record_details(record))

    if groups["ok"]:
        lines.extend(["", "Пока всё нормально:"])

        for record in groups["ok"]:
            lines.append(format_memory_record_short(record))
            lines.extend(format_memory_record_details(record))

    lines.extend(
        [
            "",
            "Лучше начать с просроченных объектов и тех, по которым нет данных.",
            "Данные можно обновить фразой вроде: «поставь генератору интервал 365 дней» "
            "или «я обслужил септик вчера».",
        ]
    )

    return "\n".join(lines)
