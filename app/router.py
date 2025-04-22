from sqlalchemy import func, and_, desc

from typing import Annotated, Literal
from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.config import settings
from app.gios_api import GiosAPI
from fastapi import APIRouter, HTTPException, status, Depends, Request
from sqlalchemy import MetaData, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database import engine, Base, get_db
from app import models, schemes
from fastapi_pagination.ext.sqlalchemy import paginate, create_page
from fastapi_pagination import Page, Params
import requests
from datetime import datetime
import threading
import time
from fastapi import BackgroundTasks

router = APIRouter(prefix=settings.API_V1_STR)


@router.post("/load_stations/")
def load_stations(db: Session = Depends(get_db)):
    """Endpoint do pobierania i zapisywania stacji w bazie danych."""
    try:
        GiosAPI.load_stations_to_db(db)
        return {"message": "Stacje zostały załadowane do bazy danych."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load_sensors/")
def load_sensors(db: Session = Depends(get_db)):
    """Endpoint do pobierania i zapisywania danych o czujnikach w bazie danych."""
    try:
        GiosAPI.load_sensors_to_db(db)
        return {"message": "Czujniki zostały załadowane do bazy danych."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


## DLA WYGODY I DEBUGOWANIA ENDPOINTY DO CZYSZCZENIA BAZY


@router.delete("/clear-database")
def clear_data(request: Request, db: Session = Depends(get_db)):
    try:
        metadata = MetaData()
        metadata.reflect(bind=engine)

        with engine.connect() as conn:

            for table in reversed(metadata.sorted_tables):
                conn.execute(table.delete())
            conn.commit()

        return {"message": "All data cleared successfully"}

    except SQLAlchemyError as e:
        db.rollback()  # Ensure the session is rolled back on error
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/drop-database-tables")
def drop_all_tables(request: Request, db: Session = Depends(get_db)):
    try:
        metadata = MetaData()
        metadata.reflect(bind=engine)

        with engine.connect() as conn:
            with conn.begin():
                for table in reversed(metadata.sorted_tables):
                    drop_table_sql = f"DROP TABLE IF EXISTS {table.name} CASCADE"
                    conn.execute(text(drop_table_sql))

        return {"message": "All tables dropped successfully"}

    except SQLAlchemyError as e:
        db.rollback()  # Roll back the transaction in case of error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR500, detail=str(e)
        )


@router.get("/sensors")
def get_all_sensors_by_station_id(
    station_code: Annotated[str, Query(description="Station Code")],
    include_inactive: Annotated[
        bool, Query(description="Include inactive sensors")
    ] = False,
    measurement_type: Annotated[
        Literal["automatyczny", "manualny"],
        Query(description="The type of measurement the sensor performs."),
    ] = None,
    params: Params = Depends(),
    db: Session = Depends(get_db),
) -> Page[schemes.SensorSchema]:
    query = db.query(models.Sensor).filter(models.Sensor.station_code == station_code)

    if not include_inactive:
        query = query.filter(models.Sensor.is_active == True)

    if measurement_type:
        query = query.filter(models.Sensor.measurement_type == measurement_type)

    # Paginate query
    page = paginate(query, params)
    sensors = page.items

    # Get latest measurements for paginated sensors only
    sensor_ids = [s.id for s in sensors]
    latest_measurements = (
        db.query(models.Measurement)
        .filter(models.Measurement.sensor_id.in_(sensor_ids))
        .order_by(models.Measurement.sensor_id, desc(models.Measurement.timestamp))
        .distinct(models.Measurement.sensor_id)
        .all()
    )
    measurement_map = {m.sensor_id: m for m in latest_measurements}

    for sensor in sensors:
        if sensor.id in measurement_map:
            sensor.latest_measurement = measurement_map[sensor.id]

    return page

@router.get("/stations")
def get_all_stations(
    voivodeship: Annotated[
        Literal[
            "PODKARPACKIE",
            "MAZOWIECKIE",
            "POMORSKIE",
            "WIELKOPOLSKIE",
            "ZACHODNIOPOMORSKIE",
            "LUBUSKIE",
            "DOLNOŚLĄSKIE",
            "OPOLSKIE",
            "ŁÓDZKIE",
            "ŚWIĘTOKRZYSKIE",
            "MAŁOPOLSKIE",
            "ŚLĄSKIE",
            "LUBUSKIE",
            "KUJAWSKO-POMORSKIE",
            "WARMINSKO-MAZURSKIE",
        ]
        | None,
        Query(),
    ] = None,
    include_inactive: Annotated[
        bool, Query(description="Include inactive stations")
    ] = False,
    only_with_active_sensors: Annotated[
        bool, Query(description="Include stations with active sensors")
    ] = False,
    db: Session = Depends(get_db),
) -> Page[schemes.StationSchema]:
    query = db.query(models.Station)

    if voivodeship:
        query = query.filter(models.Station.voivodeship == voivodeship)

    if not include_inactive:
        query = query.filter(models.Station.end_date.is_(None))

    if only_with_active_sensors:
         query = (
             query.join(models.Station.sensors)
             .filter(
                 and_(
                     models.Sensor.is_active == True,
                     models.Sensor.measurement_type == "automatyczny"
                 )
             )
             .group_by(models.Station.id)
             .having(func.count(models.Sensor.id) > 0)
         )

    return paginate(query)

@router.get("/stations/{station_code}")
def get_station_by_code(
    station_code: str,
    db: Session = Depends(get_db),
):
    station = db.query(models.Station).filter(models.Station.code == station_code).first()

    if not station:
        raise HTTPException(status_code=404, detail="Stacja nie znaleziona")

    return station


@router.get("/check_sensors_with_data")
async def check_sensors_with_data(
    db: Session = Depends(get_db),
):
    db.query(models.Sensor).update({models.Sensor.is_active: False})
    db.commit()
    await GiosAPI.check_sensors_with_data(db=db)
    return "ok"


@router.get("/stations/by-active-sensors")
def get_stations_by_active_sensors(db: Session = Depends(get_db)):
    stations = db.query(models.Station).all()
    stations_sorted = sorted(
        stations, key=lambda station: station.count_working_sensors, reverse=True
    )
    return [
        {
            "station_id": station.id,
            "station_code": station.code,
            "station_name": station.name,
            "active_sensors_count": station.count_working_sensors,
        }
        for station in [
            station for station in stations_sorted if station.count_working_sensors > 0
        ]
    ]


@router.get("/sensors/active")
def get_sensors_from_top_stations(
    db: Session = Depends(get_db),
):
    # Podzapytanie: zlicz ile aktywnych sensorów ma każda stacja
    station_sensor_counts = (
        db.query(
            models.Sensor.station_code,
            func.count(models.Sensor.id).label("active_sensor_count"),
        )
        .filter(
            models.Sensor.is_active == True,
            models.Sensor.measurement_type == "automatyczny",
        )
        .group_by(models.Sensor.station_code)
        .order_by(desc("active_sensor_count"))
        .subquery()
    )

    # Główne zapytanie: pobierz ID sensorów tylko z tych stacji
    sensor_ids = (
        db.query(models.Sensor.id)
        .join(
            station_sensor_counts,
            models.Sensor.station_code == station_sensor_counts.c.station_code,
        )
        .filter(
            models.Sensor.is_active == True,
            models.Sensor.measurement_type == "automatyczny",
        )
        .all()
    )

    return {"sensor_ids": [s.id for s in sensor_ids]}


def fetch_data_periodically(sensor_ids, db):
    """Funkcja do cyklicznego pobierania danych."""
    while True:
        GiosAPI.fetch_measurement_data_for_sensors(sensor_ids=sensor_ids, db=db)
        time.sleep(15 * 60)  # 15 minut

@router.post("/fetch-sensors-measurements/")
def start_fetching(
    sensor_ids: schemes.SensorIds, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """Endpoint do uruchamiania cyklicznego pobierania danych o pomiarow z czujnikow z podanymi id."""
    background_tasks.add_task(fetch_data_periodically, sensor_ids.model_dump().get('sensor_ids', []), db)
    return {"message": "Rozpoczęto cykliczne pobieranie danych dla podanych czujników."}

@router.get("/measurements/{sensor_id}")
def get_all_measurements_sorted_by_date(
    sensor_id: int,
    db: Session = Depends(get_db),
) -> Page[schemes.MeasurementSchema]:
    """Endpoint do pobrania wszystkich pomiarów posortowanych według daty."""
    query = db.query(models.Measurement).filter(models.Measurement.sensor_id == sensor_id).order_by(desc(models.Measurement.timestamp))
    return paginate(query)


@router.get("/measurements/latest/{sensor_id}")
def get_latest_measurement_by_sensor_id(
    sensor_id: int,
    db: Session = Depends(get_db),
) -> schemes.MeasurementSchema:
    """Endpoint do pobrania najnowszego pomiaru dla podanego ID czujnika."""
    latest_measurement = (
        db.query(models.Measurement)
        .filter(models.Measurement.sensor_id == sensor_id)
        .order_by(desc(models.Measurement.timestamp))
        .first()
    )
    if not latest_measurement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nie znaleziono żadnego pomiaru dla czujnika o id: {sensor_id}",
        )
    return latest_measurement

