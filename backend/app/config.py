from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    database_url: str
    postgres_user: str = "laborlaw"
    postgres_password: str = "laborlaw"
    postgres_db: str = "laborlaw"

    class Config:
        env_file = ".env"


settings = Settings()
