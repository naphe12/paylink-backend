import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecret")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))
    AUTH_COOKIE_DOMAIN: str | None = os.getenv("AUTH_COOKIE_DOMAIN")
    AUTH_COOKIE_SAMESITE: str = os.getenv("AUTH_COOKIE_SAMESITE", "lax")
    AUTH_COOKIE_SECURE: bool = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
    AUTH_REFRESH_COOKIE_NAME: str = os.getenv("AUTH_REFRESH_COOKIE_NAME", "refresh_token")
    AUTH_REFRESH_COOKIE_PATH: str = os.getenv("AUTH_REFRESH_COOKIE_PATH", "/auth")
    AUTH_CSRF_HEADER_NAME: str = os.getenv("AUTH_CSRF_HEADER_NAME", "X-CSRF-Token")
    APP_ENV: str = os.getenv("APP_ENV", "dev")

    # Config email
    MAIL_FROM: str = "no-reply@pesapaid.com"
    SMTP_HOST: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    SMTP_USER: str = os.getenv("MAIL_USERNAME", "")
    SMTP_PASS: str = os.getenv("MAIL_PASSWORD", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "")
    LEDGER_ACCOUNT_CASH_IN: str = os.getenv("LEDGER_ACCOUNT_CASH_IN", "LEDGER::CASH_IN")
    LEDGER_ACCOUNT_CASH_OUT: str = os.getenv("LEDGER_ACCOUNT_CASH_OUT", "LEDGER::CASH_OUT")
    LEDGER_ACCOUNT_CREDIT_LINE: str = os.getenv("LEDGER_ACCOUNT_CREDIT_LINE", "LEDGER::CREDIT_LINE")
    MAILJET_API_KEY: str = os.getenv("MAILJET_API_KEY", "")
    MAILJET_SECRET_KEY: str = os.getenv("MAILJET_SECRET_KEY", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "no-reply@pesapaid.com")
    MAIL_FROM_NAME: str = os.getenv("MAIL_FROM_NAME", "PesaPaid App")
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    MAIL_PROVIDER: str = os.getenv("MAIL_PROVIDER", "resend")
    OPENEXCHANGERATES_APP_ID: str = os.getenv("OPENEXCHANGERATES_APP_ID", "")
    STRIPE_WEBHOOK_SECRET:str= os.getenv("STRIPE_WEBHOOK_SECRET", "")
    AGENT_EMAIL: str = os.getenv("AGENT_EMAIL", "")
    TELEGRAM_NOTIFY_CHAT_IDS: str = os.getenv("TELEGRAM_NOTIFY_CHAT_IDS", "")
    BONUS_RATE_MULTIPLIER: str = os.getenv("BONUS_RATE_MULTIPLIER", "50")
    BONUS_MAX_PER_TRANSFER: str = os.getenv("BONUS_MAX_PER_TRANSFER", "1000000")
    

settings = Settings()
