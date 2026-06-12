from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/efisien_cs"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    # Gmail SMTP (Slice A)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Google Calendar (Slice B)
    google_calendar_id: str = ""
    google_service_account_file: str = ""

    # WhatsApp via WAHA (Slice C)
    waha_base_url: str = ""
    waha_session: str = "default"
    waha_api_key: str = ""


settings = Settings()
