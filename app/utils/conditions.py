from app.db.models import HouseProfile


def profile_to_conditions(profile: HouseProfile) -> set[str]:
    conditions = {
        f"house_type={profile.house_type}",
        f"water_source={profile.water_source}",
        f"heating_type={profile.heating_type}",
        f"involvement_level={profile.involvement_level}",
    }

    if profile.has_gas:
        conditions.add("has_gas=true")

    if profile.has_generator:
        conditions.add("has_generator=true")

    if profile.has_pool:
        conditions.add("has_pool=true")

    if profile.has_basement:
        conditions.add("has_basement=true")

    if profile.has_plot:
        conditions.add("has_plot=true")

    if profile.has_fireplace:
        conditions.add("has_fireplace=true")

    return conditions


def is_kb_item_relevant(
    kb_conditions: list[str],
    profile: HouseProfile
) -> bool:
    if not kb_conditions:
        return True

    profile_conditions = profile_to_conditions(profile)

    return all(condition in profile_conditions for condition in kb_conditions)