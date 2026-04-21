import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecret")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))
    ACCESS_TOKEN_EXPIRE_MINUTES_CLIENT: int | None = (
        int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_CLIENT")) if os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_CLIENT") else None
    )
    ACCESS_TOKEN_EXPIRE_MINUTES_AGENT: int | None = (
        int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_AGENT")) if os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_AGENT") else None
    )
    ACCESS_TOKEN_EXPIRE_MINUTES_ADMIN: int | None = (
        int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_ADMIN")) if os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_ADMIN") else None
    )
    REFRESH_TOKEN_EXPIRE_DAYS_CLIENT: int | None = (
        int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_CLIENT")) if os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_CLIENT") else None
    )
    REFRESH_TOKEN_EXPIRE_DAYS_AGENT: int | None = (
        int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_AGENT")) if os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_AGENT") else None
    )
    REFRESH_TOKEN_EXPIRE_DAYS_ADMIN: int | None = (
        int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_ADMIN")) if os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_ADMIN") else None
    )
    ACCESS_TOKEN_EXPIRE_MINUTES_STAGING: int | None = (
        int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_STAGING", "60")) if os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_STAGING", "60") else None
    )
    REFRESH_TOKEN_EXPIRE_DAYS_STAGING: int | None = (
        int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_STAGING")) if os.getenv("REFRESH_TOKEN_EXPIRE_DAYS_STAGING") else None
    )
    AUTH_COOKIE_DOMAIN: str | None = os.getenv("AUTH_COOKIE_DOMAIN")
    AUTH_COOKIE_SAMESITE: str = os.getenv("AUTH_COOKIE_SAMESITE", "lax")
    AUTH_COOKIE_SECURE: bool = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
    AUTH_REFRESH_COOKIE_NAME: str = os.getenv("AUTH_REFRESH_COOKIE_NAME", "refresh_token")
    AUTH_REFRESH_COOKIE_PATH: str = os.getenv("AUTH_REFRESH_COOKIE_PATH", "/auth")
    AUTH_CSRF_HEADER_NAME: str = os.getenv("AUTH_CSRF_HEADER_NAME", "X-CSRF-Token")
    ADMIN_STEP_UP_ENABLED: bool = os.getenv("ADMIN_STEP_UP_ENABLED", "false").lower() == "true"
    ADMIN_STEP_UP_HEADER_NAME: str = os.getenv("ADMIN_STEP_UP_HEADER_NAME", "X-Admin-Confirm")
    ADMIN_STEP_UP_EXPECTED_VALUE: str = os.getenv("ADMIN_STEP_UP_EXPECTED_VALUE", "confirm")
    ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK: bool = os.getenv("ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", "false").lower() == "true"
    ADMIN_STEP_UP_TOKEN_HEADER_NAME: str = os.getenv("ADMIN_STEP_UP_TOKEN_HEADER_NAME", "X-Admin-Step-Up-Token")
    ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES", "5"))
    APP_ENV: str = os.getenv("APP_ENV", "dev")
    APP_VERSION: str = os.getenv("APP_VERSION", "dev")
    APP_COMMIT_SHA: str = os.getenv("APP_COMMIT_SHA", "")
    APP_BUILD_TIME: str = os.getenv("APP_BUILD_TIME", "")

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
    TELEGRAM_BOT_USERNAME: str = os.getenv("TELEGRAM_BOT_USERNAME", "")
    BONUS_RATE_MULTIPLIER: str = os.getenv("BONUS_RATE_MULTIPLIER", "50")
    BONUS_MAX_PER_TRANSFER: str = os.getenv("BONUS_MAX_PER_TRANSFER", "1000000")
    SYSTEM_ADMIN_USERNAME: str = os.getenv("SYSTEM_ADMIN_USERNAME", "system")
    EXTERNAL_TRANSFER_LIMIT_POLICY: str = os.getenv("EXTERNAL_TRANSFER_LIMIT_POLICY", "financial_capacity_only")
    EXTERNAL_TRANSFER_PROVIDER_DEFAULT: str = os.getenv("EXTERNAL_TRANSFER_PROVIDER_DEFAULT", "internal")
    EXTERNAL_TRANSFER_PROVIDER_RETRY_MAX: int = int(os.getenv("EXTERNAL_TRANSFER_PROVIDER_RETRY_MAX", "3"))
    EXTERNAL_TRANSFER_PROVIDER_BACKOFF_BASE_SECONDS: int = int(
        os.getenv("EXTERNAL_TRANSFER_PROVIDER_BACKOFF_BASE_SECONDS", "30")
    )
    EXTERNAL_TRANSFER_PROVIDER_RECONCILE_ENABLED: bool = (
        os.getenv("EXTERNAL_TRANSFER_PROVIDER_RECONCILE_ENABLED", "true").lower() == "true"
    )
    EXTERNAL_TRANSFER_PROVIDER_RECONCILE_INTERVAL_SECONDS: int = int(
        os.getenv("EXTERNAL_TRANSFER_PROVIDER_RECONCILE_INTERVAL_SECONDS", "60")
    )
    EXTERNAL_TRANSFER_PROVIDER_RECONCILE_BATCH_SIZE: int = int(
        os.getenv("EXTERNAL_TRANSFER_PROVIDER_RECONCILE_BATCH_SIZE", "100")
    )

    IHELA_ENABLED: bool = os.getenv("IHELA_ENABLED", "false").lower() == "true"
    IHELA_API_BASE_URL: str = os.getenv("IHELA_API_BASE_URL", "")
    IHELA_API_KEY: str = os.getenv("IHELA_API_KEY", "")
    IHELA_TIMEOUT_SECONDS: float = float(os.getenv("IHELA_TIMEOUT_SECONDS", "12"))
    IHELA_SEND_PATH: str = os.getenv("IHELA_SEND_PATH", "/transfers")
    IHELA_STATUS_PATH: str = os.getenv("IHELA_STATUS_PATH", "/transfers/{provider_ref}")
    IHELA_AUTH_SCHEME: str = os.getenv("IHELA_AUTH_SCHEME", "Bearer")
    IHELA_WEBHOOK_SECRET: str = os.getenv("IHELA_WEBHOOK_SECRET", "")
    IHELA_WEBHOOK_SIGNATURE_HEADER: str = os.getenv("IHELA_WEBHOOK_SIGNATURE_HEADER", "X-IHela-Signature")

    def _role_suffix(self, role: str | None) -> str | None:
        normalized = str(role or "").strip().lower()
        if normalized in {"client", "agent", "admin"}:
            return normalized
        return None

    def access_token_expire_minutes_for_role(self, role: str | None = None) -> int:
        role_suffix = self._role_suffix(role)
        if str(self.APP_ENV).strip().lower() == "staging" and self.ACCESS_TOKEN_EXPIRE_MINUTES_STAGING:
            return int(self.ACCESS_TOKEN_EXPIRE_MINUTES_STAGING)
        if role_suffix == "client" and self.ACCESS_TOKEN_EXPIRE_MINUTES_CLIENT is not None:
            return int(self.ACCESS_TOKEN_EXPIRE_MINUTES_CLIENT)
        if role_suffix == "agent" and self.ACCESS_TOKEN_EXPIRE_MINUTES_AGENT is not None:
            return int(self.ACCESS_TOKEN_EXPIRE_MINUTES_AGENT)
        if role_suffix == "admin" and self.ACCESS_TOKEN_EXPIRE_MINUTES_ADMIN is not None:
            return int(self.ACCESS_TOKEN_EXPIRE_MINUTES_ADMIN)
        return int(self.ACCESS_TOKEN_EXPIRE_MINUTES)

    def refresh_token_expire_days_for_role(self, role: str | None = None) -> int:
        role_suffix = self._role_suffix(role)
        if str(self.APP_ENV).strip().lower() == "staging" and self.REFRESH_TOKEN_EXPIRE_DAYS_STAGING is not None:
            return int(self.REFRESH_TOKEN_EXPIRE_DAYS_STAGING)
        if role_suffix == "client" and self.REFRESH_TOKEN_EXPIRE_DAYS_CLIENT is not None:
            return int(self.REFRESH_TOKEN_EXPIRE_DAYS_CLIENT)
        if role_suffix == "agent" and self.REFRESH_TOKEN_EXPIRE_DAYS_AGENT is not None:
            return int(self.REFRESH_TOKEN_EXPIRE_DAYS_AGENT)
        if role_suffix == "admin" and self.REFRESH_TOKEN_EXPIRE_DAYS_ADMIN is not None:
            return int(self.REFRESH_TOKEN_EXPIRE_DAYS_ADMIN)
        return int(self.REFRESH_TOKEN_EXPIRE_DAYS)

settings = Settings()
