# app/schemas.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    id_token: str | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    include_history: bool = True


class ChatResponse(BaseModel):
    response: str


class ChatHistoryItem(BaseModel):
    id: int
    message: str
    response: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleCreate(BaseModel):
    niche: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    target_time_str: str | None = None  # Aceita 'HH:MM'
    scheduled_datetime: datetime | None = None  # Aceita ISO 8601 ex: '2026-10-25T15:30:00'


class ScheduleUpdate(BaseModel):
    niche: str | None = None
    title: str | None = None
    status: str | None = None  # 'pending', 'sent', 'cancelled'
    target_time_str: str | None = None
    scheduled_datetime: datetime | None = None


class ScheduleResponse(BaseModel):
    id: int
    user_id: int
    title: str | None = None
    niche: str
    scheduled_time: datetime
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrendItem(BaseModel):
    id: int | None = None
    niche: str
    title: str
    description: str | None = None
    category: str | None = None
    growth_score: int = 85
    suggested_hook: str | None = None
    suggested_tags: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TrendGenerateRequest(BaseModel):
    niche: str = Field(min_length=2, max_length=100)
    count: int = Field(default=5, ge=1, le=10)
