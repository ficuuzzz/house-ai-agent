from enum import Enum

from pydantic import BaseModel, ConfigDict


class HouseType(str, Enum):
    dacha = "dacha"
    pmzh = "pmzh"


class WaterSource(str, Enum):
    well = "well"
    kolodec = "kolodec"
    central = "central"


class HeatingType(str, Enum):
    gas = "gas"
    electric = "electric"
    solid_fuel = "solid_fuel"


class InvolvementLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class HouseProfileCreate(BaseModel):
    house_type: HouseType
    region: str
    climate_zone: str
    water_source: WaterSource
    heating_type: HeatingType

    has_gas: bool
    has_generator: bool
    has_pool: bool
    has_basement: bool
    has_plot: bool
    has_fireplace: bool

    involvement_level: InvolvementLevel


class HouseProfileResponse(HouseProfileCreate):
    house_id: str
    user_id: str

    model_config = ConfigDict(from_attributes=True)