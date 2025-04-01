from pydantic_settings import BaseSettings
from pydantic import EmailStr
from fastapi_mail import ConnectionConfig


# General settings
class Settings(BaseSettings):
    # Use ConfigDict directly without using model_config
    class Config:
        env_file = "../.env"
        env_ignore_empty = False
        extra = "ignore"

    API_V1_STR: str = "/api/v1"

    # FROM ENV
    FRONTED_URL: str
    BACKEND_URL: str
    
    SQLALCHEMY_DATABASE_URL: str

    SECRET_KEY: str
    
    EMAIL_EMAIL: EmailStr
    EMAIL_PASSWORD: str



settings = Settings()

# EMAIL CONFIGURATION
email_conf = ConnectionConfig(
    MAIL_USERNAME=settings.EMAIL_EMAIL,
    MAIL_PASSWORD=settings.EMAIL_PASSWORD,
    MAIL_FROM=settings.EMAIL_EMAIL,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_FROM_NAME="AssetFlow",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    TEMPLATE_FOLDER="app/templates/email",
    MAIL_PORT=587,
    VALIDATE_CERTS=True,
)
