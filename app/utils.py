
from fastapi_mail import MessageSchema, MessageType, FastMail
from app.core.schemas import EmailSchema
from app.core.config import email_conf
from app


async def send_mail(email: EmailSchema):
    """
    Sends an email using the provided email schema.
    Args:
        email (EmailSchema): An instance of EmailSchema containing the email details such as subject, recipients, body, and template name.
    Returns:
        None
    Raises:
        Any exceptions raised by the FastMail send_message method.
    """

    message = MessageSchema(
        subject=email.subject,
        recipients=email.email,
        template_body=email.body,
        subtype=MessageType.html,
    )

    fm = FastMail(email_conf)
    await fm.send_message(message, template_name=f"{email.template_name}.html")

def fetch_data_periodically(sensor_ids, db):
    """Funkcja do cyklicznego pobierania danych."""
    while True:
        GiosAPI.fetch_measurement_data_for_sensors(sensor_ids=sensor_ids, db=db)
        time.sleep(15 * 60)  # 15 minut