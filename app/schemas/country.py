from pydantic import BaseModel


class CountryRead(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True