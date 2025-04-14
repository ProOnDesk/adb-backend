from sqlalchemy import func, and_

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
from fastapi_pagination.ext.sqlalchemy import paginate
from fastapi_pagination import Page
import requests
from datetime import datetime

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
    """Endpoint do pobierania i zapisywania sensorów w bazie danych."""
    try:
        GiosAPI.load_sensors_to_db(db)
        return {"message": "Sensory zostały załadowane do bazy danych."}
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
        bool, Query(description="Include inactive stations")
    ] = False,
    measurement_type: Annotated[
        Literal["automatyczny", "manualny"],
        Query(description="The type of measurement the sensor performs."),
    ] = None,
    db: Session = Depends(get_db),
) -> Page[schemes.SensorSchema]:
    query = db.query(models.Sensor).filter(models.Sensor.station_code == station_code)

    if not include_inactive:
        query = query.filter(models.Sensor.end_date.is_(None))

    if measurement_type:
        query = query.filter(models.Sensor.measurement_type == measurement_type)

    return paginate(query)


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


@router.get("/check_sensors_with_data")
def check_sensors_with_data(
    db: Session = Depends(get_db),
):

    GiosAPI.check_sensors_with_data(db=db)
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


@router.get("/sensors/from-top-stations")
def get_sensors_from_top_stations(
    top_n: Annotated[int, Query(description="Number of top stations to include")] = 5,
    db: Session = Depends(get_db),
):
    """Endpoint to get a list of all sensor IDs from the top stations with the most active sensors."""
    stations = db.query(models.Station).all()
    stations_sorted = sorted(
        stations, key=lambda station: station.count_working_sensors, reverse=True
    )
    top_stations = stations_sorted[:top_n]

    sensor_ids = []
    for station in top_stations:
        active_sensors = (
            db.query(models.Sensor)
            .filter(
                models.Sensor.station_code == station.code,
                models.Sensor.is_active == True,
                models.Sensor.measurement_type == "automatyczny",
            )
            .all()
        )
        sensor_ids.extend(sensor.id for sensor in active_sensors)

    return {"sensor_ids": sensor_ids}


sensor_ids = [
    2654,
    2656,
    2657,
    2659,
    2658,
    4768,
    4769,
    4770,
    4774,
    4772,
    1058,
    1060,
    1061,
    1062,
    1625,
    1630,
    1634,
    1638,
    2503,
    2504,
    2505,
    2506,
    2787,
    2788,
    2789,
    2794,
    4191,
    4192,
    4194,
    4193,
    4704,
    4706,
    4707,
    4709,
    4757,
    4758,
    4759,
    4760,
    221,
    222,
    220,
    397,
    398,
    400,
    1402,
    1403,
    1405,
    1414,
    1416,
    1417,
    1581,
    1582,
    1583,
    2519,
    2522,
    2523,
]


def fetch_data_periodically(db: Session):
    """Funkcja do cyklicznego pobierania danych dla listy sensorów."""
    url = "https://api.gios.gov.pl/pjp-api/v1/rest/data/getData/"
    for sensor_id in sensor_ids:
        response = requests.get(f"{url}{sensor_id}")
        data = response.json()

        measurement_list = data.get("Lista danych pomiarowych", [])
        for item in measurement_list:
            sensor_code = item.get("Kod stanowiska")
            timestamp_str = item.get("Data")
            value = item.get("Wartość")

            if value is None:
                continue  # pomiń brakujące dane

            timestamp = datetime.fromisoformat(timestamp_str)

            # Sprawdź, czy już istnieje taki pomiar
            existing = (
                db.query(models.Measurement)
                .filter_by(timestamp=timestamp, id=sensor_id)
                .first()
            )

            if existing:
                continue  # już mamy ten pomiar

            # Dodaj nowy pomiar
            measurement = models.Measurement(
                timestamp=timestamp,
                value=value,
                sensor_id=sensor_id,
            )
            db.add(measurement)

        db.commit()


@router.post("/fetch/")
def start_fetching(db: Session = Depends(get_db)):
    """Endpoint do uruchamiania cyklicznego pobierania danych."""
    fetch_data_periodically(db=db)
    return {"message": "Rozpoczęto cykliczne pobieranie danych dla podanych sensorów."}
