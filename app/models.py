from sqlalchemy import (
    Column,
    String,
    Integer,
    Date,
    ForeignKey,
    Float,
    Boolean,
    DateTime,
)
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

    @property
    def count_working_sensors(self) -> int:
        return sum(
            1
            for sensor in self.sensors
            if (sensor.is_active and sensor.measurement_type == "automatyczny")
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
    is_active = Column(Boolean, default=False, nullable=True)

    station = relationship("Station", back_populates="sensors")

    measurements = relationship(
        "Measurement", back_populates="sensor", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"Sensor({self.code}, {self.indicator_code}, {self.averaging_time}, {self.station_code})"


class Measurement(Base):
    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    value = Column(Float, nullable=False)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)

    sensor = relationship("Sensor", back_populates="measurements")

    def __repr__(self):
        return f"Measurement({self.sensor_code}, {self.timestamp}, {self.value})"
