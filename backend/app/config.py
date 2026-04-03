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

    # Environment mode
    env: str = "development"  # "development" | "production"

    # Auth feature flags
    skip_otp_verification: bool = True   # dev: skip OTP, instant login. prod: require OTP
    skip_otp_email: bool = True          # dev: don't send email. prod: send real email

    # Emails that ALWAYS go through the full auth flow, even in dev
    # (comma-separated string from env var, parsed to list)
    full_auth_emails: str = "cwchen2000@gmail.com"

    @property
    def full_auth_email_list(self) -> list[str]:
        return [e.strip() for e in self.full_auth_emails.split(",") if e.strip()]


settings = Settings()
