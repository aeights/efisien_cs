from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/efisien_cs"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"


settings = Settings()
