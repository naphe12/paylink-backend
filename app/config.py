from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # -------------------------------------------------
    # JWT (compatibility for existing auth dependencies)
    # -------------------------------------------------
    SECRET_KEY: str = "secret-paylink-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240

    # -------------------------------------------------
    # ENVIRONNEMENT
    # -------------------------------------------------
    APP_ENV: str = "dev"  # dev | staging | prod

    # -------------------------------------------------
    # SANDBOX
    # -------------------------------------------------
    SANDBOX_ENABLED: bool = True
    SANDBOX_ADMIN_ONLY: bool = True

    # -------------------------------------------------
    # WEBHOOK SECURITY
    # -------------------------------------------------
    ESCROW_WEBHOOK_SECRET: str 
    REDIS_URL: str | None = None
    RATE_LIMIT_ENABLED: bool = True

    # Blockchain
    ESCROW_NETWORK: str = "polygon_mumbai"
    POLYGON_RPC_URL: str
    POLYGON_CHAIN_ID: int
    USDC_CONTRACT_ADDRESS: str
    # -------------------------------------------------
    # ALERTING / NOTIFICATIONS
    # -------------------------------------------------
    ADMIN_ALERT_EMAIL: str | None = None
    ADMIN_ALERT_PHONE: str | None = None
    SLACK_WEBHOOK_URL: str | None = None

    # -------------------------------------------------
    # EMAIL SMTP
    # -------------------------------------------------
    MAIL_FROM: str = "noreply@paylink.com"
    MAIL_FROM_NAME: str = "PayLink"
    SMTP_HOST: str = "smtp.mailgun.org"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    # Compatibility alias for legacy mail helper expecting SMTP_PASS.
    SMTP_PASS: str | None = None

    # -------------------------------------------------
    # TWILIO WHATSAPP
    # -------------------------------------------------
    TWILIO_SID: str | None = None
    TWILIO_TOKEN: str | None = None
    TWILIO_WHATSAPP_NUMBER: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if settings.SMTP_PASS is None and settings.SMTP_PASSWORD is not None:
    settings.SMTP_PASS = settings.SMTP_PASSWORD

if settings.APP_ENV == "prod" and settings.SANDBOX_ENABLED:
    raise RuntimeError("SANDBOX_ENABLED cannot be True in production environment")
