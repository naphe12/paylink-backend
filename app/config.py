from functools import lru_cache

from pydantic import Field
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
    APP_ENV: str = Field(default="dev")  # dev|staging|prod

    # -------------------------------------------------
    # SANDBOX
    # -------------------------------------------------
    SANDBOX_ENABLED: bool = Field(default=False)
    SANDBOX_ADMIN_ONLY: bool = Field(default=True)

    # -------------------------------------------------
    # WEBHOOK SECURITY
    # -------------------------------------------------
    HMAC_SECRET: str = Field(default="")
    ESCROW_WEBHOOK_SECRET: str = Field(default="")
    REDIS_URL: str | None = Field(default=None)
    RATE_LIMIT_ENABLED: bool = True
    RL_AUTH_PER_MIN: int = 20
    RL_P2P_WRITE_PER_MIN: int = 30
    RL_WEBHOOK_PER_MIN: int = 120
    RL_ADMIN_PER_MIN: int = 120

    # Circuit breaker
    CB_FAIL_THRESHOLD: int = 5
    CB_OPEN_SECONDS: int = 60
    CB_HALFOPEN_MAX_CALLS: int = 3

    # Security headers
    ALLOWED_ORIGINS: str = Field(default="")

    # -------------------------------------------------
    # P2P MARKET MAKER / SYSTEM FLAGS
    # -------------------------------------------------
    P2P_MM_ENABLED: bool = True
    P2P_MM_MAX_DAILY_USD: float = 2000.0
    P2P_MM_SPREAD_BPS: int = 80  # 0.80%
    SYSTEM_TREASURY_USER_ID: str = ""  # user_id d'un compte admin/treasury
    ML_SCORING_ENABLED: bool = False
    ML_MODEL_PATH: str = "models/risk_model.pkl"

    # Blockchain
    ESCROW_NETWORK: str = "Polygon_Amoy"
    POLYGON_RPC_URL: str = ""
    POLYGON_CHAIN_ID: int = 137
    USDC_CONTRACT_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    USDT_CONTRACT_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    PAYLINK_USDC_DEPOSIT_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    PAYLINK_USDT_DEPOSIT_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    # -------------------------------------------------
    # ALERTING / NOTIFICATIONS
    # -------------------------------------------------
    ADMIN_ALERT_EMAIL: str | None = None
    ADMIN_ALERT_PHONE: str | None = None
    SLACK_WEBHOOK_URL: str | None = None
    AML_AUTO_FREEZE_THRESHOLD: int = 90
    AML_AUTO_FREEZE_ENABLED: bool = True

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
