from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import HouseMemory, HouseProfile
from app.schemas.summary import HouseSummaryResponse, SummaryItem
from app.utils.date_utils import calculate_memory_status


def get_house_summary(
    db: Session,
    profile: HouseProfile | None
) -> HouseSummaryResponse:
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="HouseProfile not found"
        )

    memory_records = (
        db.query(HouseMemory)
        .filter(HouseMemory.house_id == profile.house_id)
        .all()
    )

    status_counts = {
        "ok": 0,
        "soon": 0,
        "overdue": 0,
        "no_data": 0,
    }

    items = []

    for record in memory_records:
        # Пересчитываем статус на момент запроса.
        # Это важно: вчера объект мог быть ok, а сегодня уже overdue.
        actual_status = calculate_memory_status(record.next_service_date)

        if record.status != actual_status:
            record.status = actual_status

        status_counts[actual_status] += 1

        items.append(
            SummaryItem(
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

    db.commit()

    return HouseSummaryResponse(
        total_items=len(memory_records),
        status_counts=status_counts,
        items=items
    )