from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # -------------------------------------------------
    # JWT (compatibility for existing auth dependencies)
    # -------------------------------------------------
    SECRET_KEY: str = "secret-paylink-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    AUTH_COOKIE_DOMAIN: str | None = None
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_REFRESH_COOKIE_NAME: str = "refresh_token"
    AUTH_REFRESH_COOKIE_PATH: str = "/auth"
    AUTH_CSRF_HEADER_NAME: str = "X-CSRF-Token"

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
    P2P_ESCROW_ADDRESS_PROVIDER: str = "simulated"  # simulated|configured
    P2P_ESCROW_NETWORK: str = "POLYGON"
    P2P_CHAIN_AUTO_ASSIGN_MIN_SCORE: int = 90
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
    LEDGER_HEALTH_CHECK_ENABLED: bool = True
    LEDGER_HEALTH_CHECK_INTERVAL_SECONDS: int = 120
    LEDGER_HEALTH_ALERT_DELTA: int = 1
    LEDGER_DAILY_CHECK_ENABLED: bool = True
    LEDGER_DAILY_CHECK_UTC_HOUR: int = 7
    LEDGER_DAILY_ALERT_ON_OK: bool = False
    TELEGRAM_NOTIFY_CHAT_IDS: str = ""
    IDEMPOTENCY_CLEANUP_ENABLED: bool = True
    IDEMPOTENCY_CLEANUP_INTERVAL_SECONDS: int = 1800
    IDEMPOTENCY_RETENTION_HOURS: int = 72
    REQUEST_METRICS_ENABLED: bool = True

    # -------------------------------------------------
    # EMAIL SMTP
    # -------------------------------------------------
    MAIL_FROM: str = "noreply@pesapaid.com"
    MAIL_FROM_NAME: str = "PesaPaid"
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
    OPENEXCHANGERATES_APP_ID: str = ""

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
