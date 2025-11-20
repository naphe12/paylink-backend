import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecret")
    ALGORITHM: str = "HS256"

    # Config email
    MAIL_FROM: str = "no-reply@paylink.app"
    SMTP_HOST: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    SMTP_USER: str = os.getenv("MAIL_USERNAME", "")
    SMTP_PASS: str = os.getenv("MAIL_PASSWORD", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    LEDGER_ACCOUNT_CASH_IN: str = os.getenv("LEDGER_ACCOUNT_CASH_IN", "LEDGER::CASH_IN")
    LEDGER_ACCOUNT_CASH_OUT: str = os.getenv("LEDGER_ACCOUNT_CASH_OUT", "LEDGER::CASH_OUT")
    LEDGER_ACCOUNT_CREDIT_LINE: str = os.getenv("LEDGER_ACCOUNT_CREDIT_LINE", "LEDGER::CREDIT_LINE")

settings = Settings()
