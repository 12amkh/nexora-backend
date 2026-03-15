from typing import Literal
from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    plan: str
    theme: Literal["dark", "light"]
    created_at: datetime

    class Config:
        from_attributes = True


class UserThemeUpdate(BaseModel):
    theme: Literal["dark", "light"]
