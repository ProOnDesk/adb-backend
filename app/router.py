from sqlalchemy import func, and_, desc
import matplotlib.pyplot as plt
import numpy as np
from statistics import mean, median
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import PageBreak


from io import BytesIO, StringIO
import csv
from fastapi.responses import StreamingResponse
from typing import Annotated, Literal
from fastapi import APIRouter, Query, Response
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
from datetime import datetime, date
import time
from fastapi import BackgroundTasks


router = APIRouter(prefix=settings.API_V1_STR)

from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors

    
def generate_histogram(measurements, label):
    values = [m.value for m in measurements]

    fig, ax = plt.subplots()
    ax.hist(values, bins=10, color="green", edgecolor="black")
    ax.set_title(f"{label} - Histogram wartości")
    ax.set_xlabel("Wartość")
    ax.set_ylabel("Liczba wystąpień")
    plt.tight_layout()

    img_bytes = BytesIO()
    plt.savefig(img_bytes, format="png")
    plt.close(fig)
    img_bytes.seek(0)
    return img_bytes

def add_metadata(canvas: Canvas, doc):
    canvas.setTitle("Raport stacji pomiarowej")
    canvas.setAuthor("System Monitoringu Powietrza")
    canvas.setSubject("Automatyczny raport PDF")
    canvas.setFont("Helvetica", 8)
    canvas.drawString(30, 20, f"Data wygenerowania: {datetime.now().strftime('%Y-%m-%d %H:00')}")

def generate_plot(measurements, sensor_name: str) -> BytesIO:
    times = [m.timestamp for m in measurements]
    values = [m.value for m in measurements]

    fig, ax = plt.subplots()
    ax.plot(times, values, marker='o')
    ax.set_title(f'Pomiar: {sensor_name}')
    ax.set_xlabel("Czas")
    ax.set_ylabel("Wartość")
    ax.grid(True)
    fig.autofmt_xdate()

    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='PNG')
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer

@router.post("/load_stations/", tags=['Fetch data from GIOS'])
def load_stations(db: Session = Depends(get_db)):
    """Endpoint do pobierania i zapisywania stacji w bazie danych."""
    try:
        GiosAPI.load_stations_to_db(db)
        return {"message": "Stacje zostały załadowane do bazy danych."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load_sensors/", tags=['Fetch data from GIOS'])
def load_sensors(db: Session = Depends(get_db)):
    """Endpoint do pobierania i zapisywania danych o czujnikach w bazie danych."""
    try:
        GiosAPI.load_sensors_to_db(db)
        return {"message": "Czujniki zostały załadowane do bazy danych."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


## DLA WYGODY I DEBUGOWANIA ENDPOINTY DO CZYSZCZENIA BAZY


@router.delete("/clear-database", tags=['Database'])
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


@router.delete("/drop-database-tables", tags=['Database'])
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
)-> schemes.StationSchema:
    station = db.query(models.Station).filter(models.Station.code == station_code).first()

    if not station:
        raise HTTPException(status_code=404, detail="Stacja nie znaleziona")

    return station


@router.get("/check_sensors_with_data", tags=['Fetch data from GIOS'])
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

@router.post("/fetch-sensors-measurements/", tags=['Fetch data from GIOS'])
def start_fetching(
    sensor_ids: schemes.SensorIds, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """Endpoint do uruchamiania cyklicznego pobierania danych o pomiarow z czujnikow z podanymi id."""
    background_tasks.add_task(fetch_data_periodically, sensor_ids.model_dump().get('sensor_ids', []), db)
    return {"message": "Rozpoczęto cykliczne pobieranie danych dla podanych czujników."}


@router.get("/measurements/{sensor_id}")
def get_measurements_by_date(
    sensor_id: int,
    date_filter: date = Query(None, description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> Page[schemes.MeasurementSchema]:
    """Endpoint do pobierania pomiarów z danego dnia."""
    query = db.query(models.Measurement).filter(models.Measurement.sensor_id == sensor_id)
    
    if date_filter:
        start = datetime.combine(date_filter, datetime.min.time())
        end = datetime.combine(date_filter, datetime.max.time())
        query = query.filter(models.Measurement.timestamp.between(start, end))

    query = query.order_by(desc(models.Measurement.timestamp))
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

@router.post("/station/generate-pdf-report/{station_id}", tags=["Generate report"])
def generate_pdf_station_report_by_station_id(
    station_id: int,
    report: schemes.ReportSchema,
    db: Session = Depends(get_db)
):
    pdfmetrics.registerFont(TTFont("DejaVuSans", "./DejaVuSans.ttf"))

    station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not station:
        return {"error": "Station not found"}

    sensors = db.query(models.Sensor).filter(models.Sensor.id.in_(report.sensor_ids)).all()

    sensor_data = {}
    for sensor in sensors:
        measurements = db.query(models.Measurement).filter(
            models.Measurement.sensor_id == sensor.id,
            models.Measurement.timestamp >= report.start_time,
            models.Measurement.timestamp <= report.end_time
        ).order_by(models.Measurement.timestamp).all()
        sensor_data[sensor] = measurements

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    # Definicja przykładowego stylu tabeli
    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ])

    # Zastosujemy też lepsze odstępy i wyraźniejsze tytuły stron:
    title_style = ParagraphStyle(
        "Tytul",
        parent=styles["Title"],
        fontName="DejaVuSans",
        fontSize=20,
        alignment=1,  # center
        spaceAfter=20,
    )

    section_title = ParagraphStyle(
        "Sekcja",
        parent=styles["Heading2"],
        fontName="DejaVuSans",
        fontSize=14,
        textColor=colors.darkblue,
        spaceAfter=10,
        spaceBefore=20,
    )

    text_style = ParagraphStyle(
        "Normalny",
        parent=styles["Normal"],
        fontName="DejaVuSans",
        fontSize=10,
        spaceAfter=6,
    )

    italic_style = ParagraphStyle(
        "Italic",
        parent=styles["Italic"],
        fontName="DejaVuSans",
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=6,
    )
    # Dodane własne style
    for style in styles.byName.values():
        style.fontName = "DejaVuSans"

    title_style = ParagraphStyle("Tytul", parent=styles["Title"], fontSize=24, alignment=1, spaceAfter=20)
    section_style = ParagraphStyle("Sekcja", parent=styles["Heading1"], fontSize=18, textColor=colors.black, spaceBefore=10, spaceAfter=10)
    normal_style = ParagraphStyle("Normalny", parent=styles["Normal"], fontSize=11, spaceAfter=6)
    italic_style = ParagraphStyle("Italic", parent=styles["Italic"], fontSize=11, textColor=colors.grey, spaceAfter=6)

    elements = []

    # ✅ STRONA TYTUŁOWA – ROZBUDOWANA I CZYTELNA
    elements.append(Spacer(1, 50))
    elements.append(Paragraph("Raport ze stacji pomiarowej", title_style))
    elements.append(Spacer(1, 30))

    elements.append(Paragraph(
        f"Raport obejmuje dane pomiarowe zarejestrowane przez stację <b>{station.name}</b> "
        f"(kod: {station.code}), zlokalizowaną w miejscowości {station.city}, województwie {station.voivodeship}, "
        f"pod adresem: {station.address}. W momencie generowania raportu stacja posiada "
        f"{station.count_working_sensors} aktywnych czujników automatycznych, spośród wszystkich {len(station.sensors)} zainstalowanych czujników. "
        f"Łącznie zgromadzono {sum(len(sensor.measurements) for sensor in station.sensors)} pomiarów. "
        f"Zakres czasowy raportu obejmuje okres od {report.start_time.strftime('%Y-%m-%d %H:%M')} do {report.end_time.strftime('%Y-%m-%d %H:%M')}. "
        f"Dokument zawiera szczegółowe informacje o czujnikach, statystyki wyników (min, max, średnia, mediana) oraz wykresy pomiarów. "
        f"Dane wykorzystywane w raporcie pochodzą z publicznego interfejsu API Głównego Inspektoratu Ochrony Środowiska, "
        f"dostępnego pod adresem: <a href='https://api.gios.gov.pl/pjp-api/swagger-ui/#/'>https://api.gios.gov.pl/pjp-api/swagger-ui/#/</a>. "
        f"Źródło to stanowi oficjalne i wiarygodne repozytorium danych o jakości powietrza w Polsce.",
        normal_style
    ))

    # ✅ STRONY Z CZUJNIKAMI
    for sensor, measurements in sensor_data.items():
        elements.append(Paragraph(f"Czujnik: {sensor.indicator_name}", section_style))
        elements.append(Paragraph(f"Uśrednianie: {sensor.averaging_time}", normal_style))
        elements.append(Paragraph(f"Aktywny: {'Tak' if sensor.is_active else 'Nie'}", normal_style))
        elements.append(Paragraph(f"Liczba pomiarów: {len(measurements)}", normal_style))

        if measurements:
            values = [m.value for m in measurements]

            stats = {
                "Min": round(min(values), 2),
                "Max": round(max(values), 2),
                "Średnia": round(mean(values), 2),
                "Mediana": round(median(values), 2)
            }

            # Średni odstęp czasu
            if len(measurements) > 1:
                deltas = [
                    (measurements[i + 1].timestamp - measurements[i].timestamp).total_seconds() / 3600
                    for i in range(len(measurements) - 1)
                ]
                avg_interval = round(mean(deltas), 2)
                elements.append(Paragraph(f"Średni odstęp pomiarów: {avg_interval} godz.", normal_style))

            stats_text = ", ".join([f"{k}: {v}" for k, v in stats.items()])
            elements.append(Paragraph(f"Statystyki: {stats_text}", normal_style))

            chart = generate_plot(measurements, sensor.indicator_name)
            hist = generate_histogram(measurements, sensor.indicator_name)

            elements.append(Image(chart, width=400, height=200))
            elements.append(Spacer(1, 10))
            elements.append(Image(hist, width=400, height=200))
        else:
            elements.append(Paragraph("Brak danych pomiarowych w podanym okresie.", italic_style))

        elements.append(PageBreak())


    doc.build(elements, onFirstPage=add_metadata)
    buffer.seek(0)

    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=raport_stacji_{station.code}.pdf"}
    )

@router.post("/station/generate-csv-report/{station_id}", tags=['Generate report'])
def generate_csv_station_report_by_station_id(
    station_id: int,
    report: schemes.ReportSchema,
    db: Session = Depends(get_db)
):
    station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not station:
        return {"error": "Station not found"}

    sensors = db.query(models.Sensor).filter(
        models.Sensor.id.in_(report.sensor_ids),
        models.Sensor.station_code == station.code
    ).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "station_name", "sensor_name", "sensor_code", "value"])

    for sensor in sensors:
        measurements = db.query(models.Measurement).filter(
            models.Measurement.sensor_id == sensor.id,
            models.Measurement.timestamp >= report.start_time,
            models.Measurement.timestamp <= report.end_time
        ).order_by(models.Measurement.timestamp).all()

        for m in measurements:
            writer.writerow([
                m.timestamp.isoformat(),
                station.name,
                sensor.indicator_name,
                sensor.code,
                m.value
            ])

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=raport_stacji_{station_id}.csv"}
    )