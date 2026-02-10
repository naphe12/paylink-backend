from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # =====================
    # 🔐 JWT Configuration
    # =====================
    SECRET_KEY: str   
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240  # 24h

    # =====================
    # 🗄️ Base de données
    # =====================
    DATABASE_URL: str 

    # =====================
    # 📡 Redis (optionnel)
    # =====================
    REDIS_URL: str | None = None
    VITE_API_URL: str | None = None
    ESCROW_WEBHOOK_SECRET:str
    
    TZ:str
# --- Backend ---   
    FASTAPI_ENV:str= "development"
    LOG_LEVEL:str

    class Config:
        env_file = ".env"  # chargera les variables depuis .env si présentes
        extra = "ignore"  # ⬅️ cette ligne dit à Pydantic d’ignorer les variables non définies


# Instance globale accessible partout
settings = Settings()
