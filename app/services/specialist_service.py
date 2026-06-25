from typing import Optional


RISK_WORDS = [
    "газ",
    "запах газа",
    "искрит",
    "коротит",
    "дым",
    "горит",
    "перегрев",
    "течь",
    "затопление",
    "подтопление",
    "канализация",
    "септик",
    "насос не работает",
    "нет воды",
    "давление падает",
    "вода идет рывками",
    "вода идёт рывками",
]


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""

    return str(value).lower().replace("ё", "е")


def has_risk_words(query: str, item: dict) -> bool:
    searchable_text = " ".join(
        [
            query,
            str(item.get("title") or ""),
            str(item.get("task_description") or ""),
            str(item.get("instructions") or ""),
            str(item.get("purpose") or ""),
        ]
    )

    normalized = normalize_text(searchable_text)

    return any(risk_word in normalized for risk_word in RISK_WORDS)


def analyze_specialist_recommendation(
    query: str,
    items: list[dict]
) -> dict:
    if not items:
        return {
            "recommend_specialist": True,
            "specialist_reason": (
                "В базе знаний не найдено достаточно релевантных записей. "
                "Лучше обратиться к профильному специалисту или уточнить проблему."
            )
        }

    top_item = items[0]

    top_score = float(top_item.get("score") or 0)
    can_do_self = normalize_text(top_item.get("can_do_self"))
    priority = normalize_text(top_item.get("priority"))

    if top_score < 0.45:
        return {
            "recommend_specialist": True,
            "specialist_reason": (
                "Найденные записи слабо похожи на вопрос пользователя. "
                "Недостаточно данных для уверенной самостоятельной рекомендации."
            )
        }

    if can_do_self == "нет":
        return {
            "recommend_specialist": True,
            "specialist_reason": (
                "В базе знаний указано, что эту задачу не рекомендуется выполнять самостоятельно."
            )
        }

    risk_detected = has_risk_words(query, top_item)

    if can_do_self == "частично" and (risk_detected or priority == "высокий"):
        return {
            "recommend_specialist": True,
            "specialist_reason": (
                "Задача допускает только частичное самостоятельное выполнение "
                "и связана с риском или высоким приоритетом. "
                "Можно выполнить базовую визуальную проверку, но если проблема сохраняется, "
                "лучше обратиться к специалисту."
            )
        }

    return {
        "recommend_specialist": False,
        "specialist_reason": None
    }