from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import HouseMemory, HouseProfile
from app.schemas.memory import HouseMemoryCreateItem, HouseMemoryServiceUpdate
from app.utils.date_utils import calculate_memory_status, calculate_next_service_date

from datetime import date


COMPONENT_NAMES = {
    "generator": "Генератор",
    "boiler": "Котёл",
    "pump": "Насос",
    "water_filter": "Фильтр воды",
    "septic": "Септик",
    "electrical_panel": "Электрощит",
    "ventilation": "Вентиляция",
    "roof": "Крыша",
    "gutter": "Водостоки",
    "basement": "Подвал",
    "drainage": "Дренаж",
    "pool": "Бассейн",
    "fireplace": "Камин",
    "chimney": "Дымоход",
}

PROFILE_AUTOSYNC_COMMENT = (
    "Добавлено автоматически из профиля дома. "
    "Данные обслуживания пока не указаны."
)


def normalize_profile_value(value) -> str | None:
    if value is None:
        return None

    if hasattr(value, "value"):
        return value.value

    return str(value)


def build_profile_memory_candidates(profile: HouseProfile) -> list[dict[str, str]]:
    candidates = []

    water_source = normalize_profile_value(profile.water_source)
    heating_type = normalize_profile_value(profile.heating_type)

    if profile.has_generator:
        candidates.append(
            {
                "component_type": "generator",
                "component_name": "Генератор",
            }
        )

    if profile.has_pool:
        candidates.append(
            {
                "component_type": "pool",
                "component_name": "Бассейн",
            }
        )

    if profile.has_basement:
        candidates.append(
            {
                "component_type": "basement",
                "component_name": "Подвал",
            }
        )

    if profile.has_fireplace:
        candidates.append(
            {
                "component_type": "fireplace",
                "component_name": "Камин",
            }
        )

    if heating_type == "gas":
        candidates.append(
            {
                "component_type": "gas_heating_system",
                "component_name": "Газовое отопление",
            }
        )

    if heating_type == "electric":
        candidates.append(
            {
                "component_type": "electric_heating_system",
                "component_name": "Электрическое отопление",
            }
        )

    if heating_type == "solid_fuel":
        candidates.append(
            {
                "component_type": "solid_fuel_heating_system",
                "component_name": "Твердотопливное отопление",
            }
        )

    if water_source == "well":
        candidates.append(
            {
                "component_type": "well_water_system",
                "component_name": "Скважина / система водоснабжения",
            }
        )

    if water_source == "kolodec":
        candidates.append(
            {
                "component_type": "kolodec_water_system",
                "component_name": "Колодец / система водоснабжения",
            }
        )

    if water_source == "central":
        candidates.append(
            {
                "component_type": "central_water_system",
                "component_name": "Центральное водоснабжение",
            }
        )

    return candidates


def sync_profile_components_to_memory(
    db: Session,
    profile: HouseProfile,
) -> list[HouseMemory]:
    """
    Добавляет в HouseMemory базовые объекты, которые уже следуют из HouseProfile.

    Важно:
    - не перезаписывает существующие записи;
    - не ставит даты обслуживания;
    - не придумывает интервалы;
    - создаёт записи со статусом no_data.
    """
    candidates = build_profile_memory_candidates(profile)
    created_records = []

    for candidate in candidates:
        existing_record = (
            db.query(HouseMemory)
            .filter(
                HouseMemory.house_id == profile.house_id,
                HouseMemory.component_type == candidate["component_type"],
            )
            .first()
        )

        if existing_record:
            continue

        memory_record = HouseMemory(
            house_id=profile.house_id,
            component_type=candidate["component_type"],
            component_name=candidate["component_name"],
            last_service_date=None,
            service_interval_days=None,
            next_service_date=None,
            status="no_data",
            last_check_result=None,
            comment=PROFILE_AUTOSYNC_COMMENT,
        )

        db.add(memory_record)
        created_records.append(memory_record)

    if created_records:
        db.commit()

        for record in created_records:
            db.refresh(record)

    return created_records

def get_memory_by_house_id(db: Session, house_id: str):
    return (
        db.query(HouseMemory)
        .filter(HouseMemory.house_id == house_id)
        .all()
    )


def create_or_update_memory_records(
    db: Session,
    profile: HouseProfile | None,
    items: list[HouseMemoryCreateItem]
):
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="HouseProfile not found"
        )

    result_records = []

    for item in items:
        component_type = item.component_type

        next_service_date = calculate_next_service_date(
            last_service_date=item.last_service_date,
            service_interval_days=item.service_interval_days
        )

        status = calculate_memory_status(next_service_date)

        component_name = (
            item.component_name
            or COMPONENT_NAMES.get(component_type, component_type)
        )

        existing_record = (
            db.query(HouseMemory)
            .filter(
                HouseMemory.house_id == profile.house_id,
                HouseMemory.component_type == component_type
            )
            .first()
        )

        if existing_record:
            existing_record.component_name = component_name
            existing_record.last_service_date = item.last_service_date
            existing_record.service_interval_days = item.service_interval_days
            existing_record.next_service_date = next_service_date
            existing_record.status = status
            existing_record.comment = item.comment
            result_records.append(existing_record)
        else:
            memory_record = HouseMemory(
                house_id=profile.house_id,
                component_type=component_type,
                component_name=component_name,
                last_service_date=item.last_service_date,
                service_interval_days=item.service_interval_days,
                next_service_date=next_service_date,
                status=status,
                last_check_result=None,
                comment=item.comment
            )

            db.add(memory_record)
            result_records.append(memory_record)

    db.commit()

    for record in result_records:
        db.refresh(record)

    return result_records

def update_memory_service(
    db: Session,
    memory_id: str,
    update_data: HouseMemoryServiceUpdate
):
    memory_record = (
        db.query(HouseMemory)
        .filter(HouseMemory.memory_id == memory_id)
        .first()
    )

    if not memory_record:
        raise HTTPException(
            status_code=404,
            detail="HouseMemory record not found"
        )

    service_interval_days = (
        update_data.service_interval_days
        if update_data.service_interval_days is not None
        else memory_record.service_interval_days
    )

    next_service_date = calculate_next_service_date(
        last_service_date=update_data.last_service_date,
        service_interval_days=service_interval_days
    )

    status = calculate_memory_status(next_service_date)

    memory_record.last_service_date = update_data.last_service_date
    memory_record.service_interval_days = service_interval_days
    memory_record.next_service_date = next_service_date
    memory_record.status = status

    if update_data.comment is not None:
        memory_record.comment = update_data.comment

    db.commit()
    db.refresh(memory_record)

    return memory_record

def update_memory_by_component_type(
    db: Session,
    profile: HouseProfile | None,
    component_type: str,
    last_service_date: date,
    service_interval_days: int | None = None,
    comment: str | None = None,
    component_name: str | None = None,
) -> HouseMemory:
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="HouseProfile not found"
        )

    existing_record = (
        db.query(HouseMemory)
        .filter(
            HouseMemory.house_id == profile.house_id,
            HouseMemory.component_type == component_type
        )
        .first()
    )

    effective_interval = service_interval_days

    if effective_interval is None and existing_record:
        effective_interval = existing_record.service_interval_days

    next_service_date = calculate_next_service_date(
        last_service_date=last_service_date,
        service_interval_days=effective_interval
    )

    status = calculate_memory_status(next_service_date)

    final_component_name = (
        component_name
        or COMPONENT_NAMES.get(component_type, component_type)
    )

    if existing_record:
        existing_record.component_name = final_component_name
        existing_record.last_service_date = last_service_date
        existing_record.service_interval_days = effective_interval
        existing_record.next_service_date = next_service_date
        existing_record.status = status

        if comment is not None:
            existing_record.comment = comment

        db.commit()
        db.refresh(existing_record)

        return existing_record

    memory_record = HouseMemory(
        house_id=profile.house_id,
        component_type=component_type,
        component_name=final_component_name,
        last_service_date=last_service_date,
        service_interval_days=effective_interval,
        next_service_date=next_service_date,
        status=status,
        last_check_result=None,
        comment=comment,
    )

    db.add(memory_record)
    db.commit()
    db.refresh(memory_record)

    return memory_record

def delete_memory_records_by_ids(
    db: Session,
    profile: HouseProfile,
    memory_ids: list[str],
) -> list[HouseMemory]:
    if not memory_ids:
        return []

    records = (
        db.query(HouseMemory)
        .filter(
            HouseMemory.house_id == profile.house_id,
            HouseMemory.memory_id.in_(memory_ids),
        )
        .all()
    )

    if not records:
        return []

    deleted_records = list(records)

    for record in records:
        db.delete(record)

    db.commit()

    return deleted_records

def update_memory_record_fields(
    db: Session,
    profile: HouseProfile,
    memory_id: str,
    updates: dict,
) -> HouseMemory:
    memory_record = (
        db.query(HouseMemory)
        .filter(
            HouseMemory.house_id == profile.house_id,
            HouseMemory.memory_id == memory_id,
        )
        .first()
    )

    if not memory_record:
        raise HTTPException(
            status_code=404,
            detail="HouseMemory record not found",
        )

    if "component_name" in updates:
        memory_record.component_name = updates["component_name"]

    if "last_service_date" in updates:
        memory_record.last_service_date = updates["last_service_date"]

    if "service_interval_days" in updates:
        memory_record.service_interval_days = updates["service_interval_days"]

    if updates.get("clear_comment"):
        memory_record.comment = None
    elif "comment" in updates:
        memory_record.comment = updates["comment"]

    memory_record.next_service_date = calculate_next_service_date(
        last_service_date=memory_record.last_service_date,
        service_interval_days=memory_record.service_interval_days,
    )

    memory_record.status = calculate_memory_status(
        memory_record.next_service_date,
    )

    db.commit()
    db.refresh(memory_record)

    return memory_record