# models/telegram_user.py
from sqlalchemy import Column, Integer, String
from app.core.database import Base

class TelegramUser(Base):
    __tablename__ = "telegram_users"
    __table_args__ = {"schema": "telegram"}

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    is_bot = Column(String, nullable=True)  # 'true' or 'false' as string