from sqladmin import ModelView

from app.models import Station, Sensor, Measurement


class StationAdminView(ModelView, model=Station):
    column_list = "__all__"


class SensorAdminView(ModelView, model=Sensor):
    column_list = "__all__"


class MeasurementAdminView(ModelView, model=Measurement):
    column_list = "__all__"
