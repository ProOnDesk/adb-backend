from sqlalchemy import Column, String, Integer, Date, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, unique=True, index=True)
    code = Column(String, nullable=False, unique=True)

    name = Column(String, index=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    station_type = Column(String, nullable=True)  #
    area_type = Column(String, nullable=True)  #
    station_kind = Column(String, nullable=True)
    voivodeship = Column(String, nullable=True)
    city = Column(String, nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    sensors = relationship(
        "Sensor", back_populates="station", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"Station({self.id}, {self.name}, {self.code}, {self.voivodeship}, {self.city})"


class Sensor(Base):
    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, unique=True, index=True)
    code = Column(String, nullable=False, unique=True)
    station_code = Column(String, ForeignKey("stations.code"))
    indicator_code = Column(String, nullable=False)
    indicator_name = Column(String, nullable=False)
    averaging_time = Column(String, nullable=True)
    measurement_type = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    station = relationship("Station", back_populates="sensors")

    def __repr__(self):
        return f"Sensor({self.code}, {self.indicator_code}, {self.averaging_time}, {self.station_code})"
        