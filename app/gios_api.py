import requests
import httpx
import asyncio
from sqlalchemy.orm import Session
from app.models import Station, Sensor, Measurement
from datetime import datetime
from time import sleep
data = {}

class GiosAPI:
    BASE_URL: str = "https://api.gios.gov.pl/pjp-api/v1/rest"
        
    @staticmethod
    def fetch_sensors_data():
        """Pobiera listę stanowisk pomiarowych z paginacją."""
        sensors_data_list = []
        page = 0
        max_page = 1

        while page <= max_page:
            response = requests.get(
                f"{GiosAPI.BASE_URL}/metadata/sensors?size=500&page={page}"
            )
            response.raise_for_status()
            response_dict = response.json()

            max_page = response_dict.get("totalPages", 1)
            sensors_data_list.extend(
                response_dict.get("Lista metadanych stanowisk pomiarowych", [])
            )
            page += 1
            sleep(31)

        return sensors_data_list

    @staticmethod
    def fetch_stations_data():
        """Pobiera listę stacji z danymi z paginacją."""
        stations_data_list = []

        page = 0
        max_page = 1
        while page <= max_page:
            response = requests.get(
                f"{GiosAPI.BASE_URL}/metadata/stations?size=500&page={page}"
            )
            response.raise_for_status()
            response_dict = response.json()

            max_page = response_dict.get("totalPages", 1)
            stations_data_list.extend(
                response_dict.get("Lista metadanych stacji pomiarowych", [])
            )

            page += 1
            sleep(31)

        return stations_data_list

    @classmethod
    def load_stations_to_db(cls, db: Session):
        """Pobiera i zapisuje stacje do bazy danych."""
        stations_data = cls.fetch_stations_data()

        for s in stations_data:
            station = Station(
                id=int(s.get("Nr")),  # Identyfikator (opcjonalnie, można usunąć)
                code=s.get("Kod stacji"),
                name=s.get("Nazwa stacji"),
                start_date=(
                    datetime.strptime(s["Data uruchomienia"], "%Y-%m-%d").date()
                    if s.get("Data uruchomienia")
                    else None
                ),
                end_date=(
                    datetime.strptime(s["Data zamknięcia"], "%Y-%m-%d").date()
                    if s.get("Data zamknięcia")
                    else None
                ),
                station_type=s.get("Typ stacji"),
                area_type=s.get("Typ obszaru"),
                station_kind=s.get("Rodzaj stacji"),
                voivodeship=s.get("Województwo"),
                city=s.get("Miejscowość"),
                address=s.get("Adres"),
                latitude=float(s["WGS84 φ N"]) if s.get("WGS84 φ N") else None,
                longitude=float(s["WGS84 λ E"]) if s.get("WGS84 λ E") else None,
            )
            db.merge(station)
        db.commit()

    @classmethod
    def load_sensors_to_db(cls, db: Session):
        """Pobiera i zapisuje sensory do bazy danych."""
        sensors_data = cls.fetch_sensors_data()
        data = sensors_data
        for s in sensors_data:
            sensor_id = int(s.get("Nr"))

            # Sprawdzenie, czy sensor już istnieje
            if db.query(Sensor).filter_by(id=sensor_id).first():
                continue  # Pomijamy, jeśli już istnieje

            # Tworzenie nowego obiektu sensora
            sensor = Sensor(
                id=sensor_id,
                code=s.get("Kod stanowiska"),
                station_code=s.get("Kod stacji"),
                indicator_code=s.get("Wskaźnik - kod"),
                indicator_name=s.get("Wskaźnik"),
                averaging_time=s.get("Czas uśredniania"),
                measurement_type=s.get("Typ pomiaru"),
                start_date=(
                    datetime.strptime(s["Data uruchomienia"], "%Y-%m-%d").date()
                    if s.get("Data uruchomienia")
                    else None
                ),
                end_date=(
                    datetime.strptime(s["Data zamknięcia"], "%Y-%m-%d").date()
                    if s.get("Data zamknięcia")
                    else None
                ),
            )

            db.add(sensor)  # Dodajemy tylko jeśli nie istnieje

            db.commit()

    @staticmethod
    async def check_sensors_with_data(db: Session):
        """Sprawdza sensory od 1 do N i oznacza jako aktywne te, które mają dane."""
        sensor_count = db.query(Sensor).count()
        sensor_ids = range(1, sensor_count + 669)  # Można to później poprawić

        sem = asyncio.Semaphore(25)

        async with httpx.AsyncClient(timeout=10) as client:
            for i in range(0, len(sensor_ids), 25):
                batch = sensor_ids[i:i+25]
                tasks = [
                    GiosAPI.fetch_sensor_status(sensor_id, client, sem)
                    for sensor_id in batch
                ]
                results = await asyncio.gather(*tasks)
                active_sensor_ids = list(filter(None, results))

                for sensor_id in active_sensor_ids:
                    sensor = db.query(Sensor).filter_by(id=sensor_id).first()
                    if sensor:
                        sensor.is_active = True
                        sensor.measurement_type = "automatyczny"
                        sensor.end_date = None
                        sensor.averaging_time = "1-godzinny"
                        print(f"[✓] Sensor aktywny: {sensor_id}")
                db.commit()

                await asyncio.sleep(1)
                
    @staticmethod
    async def fetch_sensor_status(sensor_id: int, client: httpx.AsyncClient, sem: asyncio.Semaphore):
        """Sprawdza, czy sensor ma dane pomiarowe i zwraca jego ID jeśli tak."""
        url = f"{GiosAPI.BASE_URL}/data/getData/{sensor_id}"

        async with sem:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("Lista danych pomiarowych"):
                        return sensor_id  # Sensor aktywny
            except Exception as e:
                print(f"[{sensor_id}] Błąd: {e}")
        return None
    
    @classmethod
    def fetch_measurement_data_for_sensors(cls, sensor_ids: list[int], db: Session):
        """
        Pobiera dane pomiarowe dla listy sensorów i zapisuje je w bazie danych.
            sensor_ids (list[int]): Lista identyfikatorów sensorów.
            db (Session): Sesja bazy danych SQLAlchemy.
        Metoda iteruje przez podane identyfikatory sensorów, pobiera dane z API GIOS
        i zapisuje je w bazie danych, unikając duplikatów.
        """

        url = f"{cls.BASE_URL}/data/getData/"
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
                    db.query(Measurement)
                    .filter_by(timestamp=timestamp, sensor_id=sensor_id)
                    .first()
                )
                if existing:
                    continue  # już mamy ten pomiar

                # Dodaj nowy pomiar
                measurement = Measurement(
                    timestamp=timestamp,
                    value=value,
                    sensor_id=sensor_id,
                )
                db.add(measurement)

            db.commit()