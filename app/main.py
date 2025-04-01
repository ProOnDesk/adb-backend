from fastapi import FastAPI
from fastapi_pagination import add_pagination
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine
from app.router import router as router_api
from app.admin import create_admin
from app.database import Base


def create_db() -> None:
    """
    Function responsible for creating the database.
    """

    # Create the database
    Base.metadata.create_all(bind=engine)


def get_configured_server_app() -> FastAPI:
    app = FastAPI(swagger_ui_parameters={"syntaxHighlight.theme": "obsidian"})

    add_pagination(app)

    app.include_router(router_api)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    create_db()
    create_admin(app=app, engine=engine)

    return app


server_app = get_configured_server_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:server_app", host="0.0.0.0", port=8000, reload=True, workers=2)
