from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse
from fastapi import FastAPI
from sqlalchemy.engine.base import Engine
from app.config import settings
from app.views import StationAdminView, SensorAdminView


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]

        # Validate username/password credentials
        # And update session
        request.session.update({"token": "..."})

        return True

    async def logout(self, request: Request) -> bool:
        # Usually you'd want to just clear the session
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")

        if not token:
            return False

        # Check the token in depth
        return True


def create_admin(app: FastAPI, engine: Engine) -> None:
    authentication_backend = AdminAuth(secret_key="secreasdddddddddddddddasdadadt")
    admin = Admin(app=app, engine=engine, authentication_backend=authentication_backend)

    admin.add_view(StationAdminView)
    admin.add_view(SensorAdminView)
