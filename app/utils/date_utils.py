from datetime import date, timedelta


def calculate_next_service_date(
    last_service_date: date | None,
    service_interval_days: int | None
) -> date | None:
    if last_service_date is None or service_interval_days is None:
        return None

    return last_service_date + timedelta(days=service_interval_days)


def calculate_memory_status(
    next_service_date: date | None,
    today: date | None = None
) -> str:
    today = today or date.today()

    if next_service_date is None:
        return "no_data"

    if next_service_date < today:
        return "overdue"

    if next_service_date <= today + timedelta(days=14):
        return "soon"

    return "ok"


def get_season_by_month_number(month_number: int) -> str:
    if month_number in [12, 1, 2]:
        return "winter"

    if month_number in [3, 4, 5]:
        return "spring"

    if month_number in [6, 7, 8]:
        return "summer"

    return "autumn"


def get_current_season(today: date | None = None) -> str:
    today = today or date.today()

    return get_season_by_month_number(today.month)