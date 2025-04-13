from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class SensorSchema(BaseModel):
    id: int
    code: str
    station_code: str
    indicator_code: str
    indicator_name: str
    averaging_time: Optional[str]
    measurement_type: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]

    class Config:
        from_attributes = True


class StationSchema(BaseModel):
    id: int
    code: str
    name: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    station_type: Optional[str]
    area_type: Optional[str]
    station_kind: Optional[str]
    voivodeship: Optional[str]
    city: Optional[str]
    address: Optional[str]
    latitude: float
    longitude: float
    count_working_sensors: int = None

    class Config:
        from_attributes = True
