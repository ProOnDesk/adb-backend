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
def get_all_sensors(db: Session = Depends(get_db)) -> list[schemes.SensorSchema]:
    return db.query(models.Sensor).all()

@router.get("/stations")
def get_all_stations(
    voivodeship: Annotated[Literal[
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
    ] | None, Query()] = None,
     include_inactive: Annotated[bool, Query(description="Include inactive stations")] = False,
    db: Session = Depends(get_db)
) -> Page[schemes.StationSchema]:
    query = db.query(models.Station)

    if voivodeship:
        query = query.filter(models.Station.voivodeship == voivodeship)

    if not include_inactive:
        query = query.filter(models.Station.end_date.is_(None))

    return paginate(query)
