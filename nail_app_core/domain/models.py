from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    id: int
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_master: bool = False


class MasterProfile(BaseModel):
    id: int
    user_id: int
    display_name: str
    timezone: str
    slug: str
    onboarded: bool = False


class Service(BaseModel):
    id: int
    master_id: int
    name: str
    price: float
    duration_minutes: int = Field(gt=0)
    is_active: bool = True


class WorkingWindow(BaseModel):
    id: int
    master_id: int
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class DailyBookingLimit(BaseModel):
    id: int
    master_id: int
    weekday: int = Field(ge=0, le=6)
    max_bookings: int = Field(ge=0)


class ClientProfile(BaseModel):
    id: int
    tg_user_id: int
    name: str
    username: Optional[str] = None
    phone: Optional[str] = None
    last_visit_at: Optional[datetime] = None


class BookingStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Booking(BaseModel):
    id: int
    master_id: int
    client_id: int
    service_id: int
    start_at: datetime
    end_at: datetime
    status: BookingStatus = BookingStatus.CONFIRMED
    created_at: datetime

