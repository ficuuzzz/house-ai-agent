import json
import re
from typing import Optional

from app.services.gigachat_service import generate_answer
from app.services.scenario_router import ScenarioDetectionResult


ALLOWED_SCENARIOS = {
    "profile_view",
    "profile_edit",
    "memory_list",
    "memory_creation",
    "memory_update",
    "memory_edit",
    "memory_delete",
    "checklist_month",
    "rag_answer",
    "unknown",
}

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


def build_intent_prompt(
    message: str,
    has_profile: bool,
    current_scenario: Optional[str],
    current_step: Optional[str],
) -> str:
    return f"""
Ты классифицируешь сообщение пользователя для backend AI-агента загородного дома.

Важно:
- Верни только JSON.
- Не отвечай пользователю текстом.
- Не придумывай данные.
- Твоя задача — определить сценарий.

Доступные сценарии:

1. profile_view
Пользователь просит показать только базовый профиль дома: тип дома, регион, воду, отопление, наличие газа, генератора, бассейна и т.д.
Это НЕ список обслуживаемых объектов.
Примеры:
- покажи профиль дома
- какой мой профиль дома?
- какие параметры дома сохранены?
- какой у меня дом?
- что ты знаешь о моём доме?
- покажи данные по дому
- покажи информацию о доме

2. profile_edit
Пользователь хочет изменить или дополнить данные профиля дома.
Примеры:
- измени источник воды
- у меня теперь не скважина, а центральная вода
- поменяй отопление
- добавь, что у меня есть газ

3. memory_list
Пользователь просит показать память дома, обслуживаемые объекты или состояние обслуживания.
Это список объектов, за которыми нужно следить: генератор, септик, фильтр, бассейн и т.д.
Сюда же относятся вопросы “что требует внимания”, “что просрочено”, “всё ли в порядке по дому”.
Примеры:
- покажи память дома
- какие обслуживаемые объекты есть?
- что в HouseMemory?
- покажи компоненты в памяти
- что у меня есть в доме?
- какие объекты есть в доме?
- что нужно обслуживать?
- что требует внимания?
- что просрочено?
- всё ли в порядке по дому?
- какое состояние дома?

4. memory_creation
Пользователь хочет добавить обслуживаемые объекты дома.
Примеры:
- хочу добавить насос
- добавь фильтр воды
- давай заполним память дома

5. memory_update
Пользователь сообщает, что обслужил объект или хочет изменить данные объекта в памяти.
Примеры:
- я заменил фильтр воды
- я почистил септик
- я проверил насос
- поставь генератору интервал обслуживания 365 дней

6. memory_edit
Пользователь хочет изменить данные уже существующего объекта в памяти дома:
интервал обслуживания, дату последнего обслуживания, комментарий или название.
Примеры:
- поставь генератору интервал обслуживания 365 дней
- добавь комментарий к септику: чистить только весной
- убери комментарий у холодильника
- переименуй холодильник в кухонный холодильник
- укажи, что фильтр обслуживали вчера

7. memory_delete
Пользователь хочет удалить объект из памяти дома, а не изменить базовый профиль дома.
Примеры:
- удали холодильник из памяти
- убери бассейн из HouseMemory
- удали насос из обслуживаемых объектов
- сотри септик из памяти дома

8. checklist_month
Пользователь просит план, задачи или чек-лист по дому на месяц/сезон.
Важно:
- Если пользователь описывает проблему: “течёт вода, что делать?”, “пахнет септик”, “не работает насос” — это rag_answer, НЕ checklist_month.
- Если пользователь спрашивает общий план: “что сделать по дому?”, “что мне делать в этом месяце?”, “какие задачи по дому?” — это checklist_month.
Примеры:
- что сделать в мае?
- чек-лист на октябрь
- какие работы весной?
- что сделать по дому?
- какие задачи сейчас?

9. rag_answer
Пользователь задаёт свободный вопрос по проблеме или уходу.
Примеры:
- вода идет рывками
- как подготовить генератор к зиме?
- почему пахнет из септика?

Контекст:
has_profile = {has_profile}
current_scenario = {current_scenario}
current_step = {current_step}

Сообщение пользователя:
{message}

Верни JSON строго такого формата:
{{
  "scenario": "profile_view | profile_edit | memory_list | memory_creation | memory_update | memory_edit | memory_delete | checklist_month | rag_answer | unknown",
  "confidence": 0.0,
  "month": null,
  "component_type": null
}}

component_type может быть:
generator, boiler, pump, water_filter, septic, electrical_panel, ventilation, roof, gutter, basement, drainage, pool, fireplace, chimney

month может быть:
january, february, march, april, may, june, july, august, september, october, november, december
"""


def classify_intent_with_gigachat(
    message: str,
    has_profile: bool,
    current_scenario: Optional[str] = None,
    current_step: Optional[str] = None,
) -> Optional[ScenarioDetectionResult]:
    prompt = build_intent_prompt(
        message=message,
        has_profile=has_profile,
        current_scenario=current_scenario,
        current_step=current_step,
    )

    try:
        raw_answer = generate_answer(prompt)
        parsed = extract_json_from_text(raw_answer)
    except Exception:
        return None

    scenario = parsed.get("scenario")
    confidence = parsed.get("confidence", 0)

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if scenario not in ALLOWED_SCENARIOS:
        return None

    if scenario == "unknown":
        return None

    # Если уверенность совсем низкая, лучше не доверять LLM.
    if confidence < 0.55:
        return None

    return ScenarioDetectionResult(
        scenario=scenario,
        month=parsed.get("month"),
        component_type=parsed.get("component_type"),
    )