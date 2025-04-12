import requests
from sqlalchemy.orm import Session
from app.models import Station, Sensor
from datetime import datetime
from time import sleep


class GiosAPI:
    BASE_URL = "https://api.gios.gov.pl/pjp-api/v1/rest"

    @staticmethod
    def fetch_sensors_data():
        """Pobiera listę stanowisk pomiarowych z paginacją."""
        sensors_data_list = []
        page = 0
        max_page = 1

        print("zaczeto proces fetchowania")

        while page <= max_page:
            response = requests.get(
                f"{GiosAPI.BASE_URL}/metadata/sensors?size=500&page={page}"
            )
            response.raise_for_status()
            response_dict = response.json()

            max_page = response_dict.get("totalPages", 1) - 1
            print(f"maksymalna strona: {max_page}")
            sensors_data_list.extend(
                response_dict.get("Lista metadanych stanowisk pomiarowych", [])
            )
            print(f"Teraz pobralo strone nr {page}")
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

            max_page = response_dict.get("totalPages", 1) - 1
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

        for s in sensors_data:

            if db.query(Sensor).filter_by(id=int(s.get("Nr"))).first():
                print("powotrzylo sie")
                continue

            sensor = Sensor(
                id=int(s.get("Nr")),
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
            db.merge(sensor)  # Aktualizacja lub dodanie nowego wpisu

        db.commit()
