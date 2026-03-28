# schemas/telegram_user.py
from pydantic import BaseModel, ConfigDict

class TelegramUserBase(BaseModel):
    chat_id: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: str | None = None

class TelegramUserCreate(TelegramUserBase):
    pass

class TelegramUserOut(TelegramUserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
