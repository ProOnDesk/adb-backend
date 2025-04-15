import requests
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
    def check_sensors_with_data(db: Session):
        """Sprawdza sensory od id 1 do 5000 i wypisuje te, które zwracają dane pomiarowe."""
        for sensor_id in range(1, 5000):
            try:
                sleep(0.05)
                response = requests.get(f"{GiosAPI.BASE_URL}/data/getData/{sensor_id}")
                response.raise_for_status()
                response_dict = response.json()

                if response_dict.get("Lista danych pomiarowych", None):
                    sensors = db.query(Sensor).filter_by(id=sensor_id).first()
                    if sensors:
                        sensors.is_active = True
                        db.commit()
                        print(f"dodano sensor o id {sensor_id} jako aktywny")
            except requests.exceptions.HTTPError as e:
                pass
            except Exception as e:
                print(f"[{sensor_id}] Unexpected error: {e}")

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