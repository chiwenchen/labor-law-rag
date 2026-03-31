from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str
    database_url: str
    postgres_user: str = "laborlaw"
    postgres_password: str = "laborlaw"
    postgres_db: str = "laborlaw"
    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"
    frontend_url: str = "http://localhost:3000"


settings = Settings()
