from app.db.models import HouseProfile
from app.schemas.checklist import ChecklistResponse
from app.services.checklist_service import get_month_user_name
from app.services.gigachat_service import generate_answer


PRIORITY_USER_NAMES = {
    "высокий": "высокий",
    "средний": "средний",
    "низкий": "низкий",
    "high": "высокий",
    "medium": "средний",
    "low": "низкий",
}


def priority_to_user_text(priority: str | None) -> str:
    if not priority:
        return "не указан"

    return PRIORITY_USER_NAMES.get(str(priority).lower(), str(priority))


def build_checklist_fallback_answer(checklist: ChecklistResponse) -> str:
    month_name = get_month_user_name(checklist.month)

    if not checklist.items:
        return (
            f"На {month_name} я не нашёл подходящих задач для вашего профиля дома.\n\n"
            "Это может быть нормально: возможно, в базе знаний пока нет задач "
            "под ваши условия."
        )

    high = []
    medium = []
    low = []
    other = []

    for item in checklist.items:
        priority = str(item.priority or "").lower()

        line = f"- {item.title}"

        if item.task_description:
            line += f": {item.task_description}"

        if priority in {"высокий", "high"}:
            high.append(line)
        elif priority in {"средний", "medium"}:
            medium.append(line)
        elif priority in {"низкий", "low"}:
            low.append(line)
        else:
            other.append(line)

    blocks = [
        f"Чек-лист по дому на {month_name}:",
    ]

    if high:
        blocks.append("\nВ первую очередь:")
        blocks.extend(high)

    if medium:
        blocks.append("\nПланово:")
        blocks.extend(medium)

    if low:
        blocks.append("\nЕсли останется время:")
        blocks.extend(low)

    if other:
        blocks.append("\nДополнительно:")
        blocks.extend(other)

    return "\n".join(blocks)


def build_checklist_prompt(
    checklist: ChecklistResponse,
    profile: HouseProfile,
) -> str:
    month_name = get_month_user_name(checklist.month)

    task_blocks = []

    for index, item in enumerate(checklist.items, start=1):
        task_blocks.append(
            f"""
ЗАДАЧА {index}
Название: {item.title}
Приоритет: {priority_to_user_text(item.priority)}
Категория: {item.category}
Подкатегория: {item.subcategory}
Описание: {item.task_description}
Инструкция: {item.instructions}
Зачем это нужно: {item.purpose}
Можно сделать самостоятельно: {item.can_do_self}
"""
        )

    tasks_text = "\n".join(task_blocks)

    return f"""
Ты AI-агент по обслуживанию дома.

Сформируй понятный чек-лист по дому на месяц: {month_name}.

Профиль дома:
- Тип дома: {profile.house_type}
- Регион: {profile.region}
- Климатическая зона: {profile.climate_zone}
- Источник воды: {profile.water_source}
- Тип отопления: {profile.heating_type}
- Газ: {profile.has_gas}
- Генератор: {profile.has_generator}
- Бассейн: {profile.has_pool}
- Подвал: {profile.has_basement}
- Участок: {profile.has_plot}
- Камин: {profile.has_fireplace}
- Уровень вовлечённости: {profile.involvement_level}

Отфильтрованные backend-задачи:
{tasks_text}

Правила:
- Используй только задачи из списка.
- Не добавляй новые задачи от себя.
- Не советуй подготовку к другому сезону, если этого нет в списке задач.
- Сгруппируй задачи по важности: сначала срочное/важное, потом плановое, потом дополнительное.
- Пиши легко и понятно.
- Не упоминай KnowledgeBase, backend, фильтрацию, RAG.
- Если задач нет, честно скажи, что подходящих задач на этот месяц не найдено.
- Для каждой задачи дай короткое объяснение, зачем она нужна.
- Если can_do_self = "нет", напиши, что лучше обратиться к специалисту.

Ответ должен быть на русском языке.
"""


def build_checklist_answer_with_gigachat(
    checklist: ChecklistResponse,
    profile: HouseProfile,
) -> str:
    if not checklist.items:
        return build_checklist_fallback_answer(checklist)

    prompt = build_checklist_prompt(
        checklist=checklist,
        profile=profile,
    )

    try:
        answer = generate_answer(prompt)

        if answer and answer.strip():
            return answer.strip()
    except Exception:
        pass

    return build_checklist_fallback_answer(checklist)