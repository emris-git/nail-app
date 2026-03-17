from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

from app.domain.models import BookingStatus

Base = declarative_base()


class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    is_master = Column(Boolean, default=False, nullable=False)

    master_profile = relationship("MasterProfileORM", back_populates="user", uselist=False)


class MasterProfileORM(Base):
    __tablename__ = "master_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    timezone = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    onboarded = Column(Boolean, default=False, nullable=False)

    user = relationship("UserORM", back_populates="master_profile")
    services = relationship("ServiceORM", back_populates="master")


class ServiceORM(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    master_id = Column(Integer, ForeignKey("master_profiles.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    master = relationship("MasterProfileORM", back_populates="services")


class WorkingWindowORM(Base):
    __tablename__ = "working_windows"

    id = Column(Integer, primary_key=True)
    master_id = Column(Integer, ForeignKey("master_profiles.id"), nullable=False)
    weekday = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)


class AvailabilitySlotORM(Base):
    """Слоты по конкретным датам и времени (формат: 20/02 в 10:00, 12:00, 16:00)."""

    __tablename__ = "availability_slots"

    id = Column(Integer, primary_key=True)
    master_id = Column(Integer, ForeignKey("master_profiles.id"), nullable=False)
    slot_date = Column(Date, nullable=False)
    slot_time = Column(Time, nullable=False)

    __table_args__ = (
        UniqueConstraint("master_id", "slot_date", "slot_time", name="uq_availability_slot"),
    )


class DailyBookingLimitORM(Base):
    __tablename__ = "daily_booking_limits"

    id = Column(Integer, primary_key=True)
    master_id = Column(Integer, ForeignKey("master_profiles.id"), nullable=False)
    weekday = Column(Integer, nullable=False)
    max_bookings = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("master_id", "weekday", name="uq_daily_limit_master_day"),)


class ClientProfileORM(Base):
    __tablename__ = "client_profiles"

    id = Column(Integer, primary_key=True)
    tg_user_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    username = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    last_visit_at = Column(DateTime(timezone=True), nullable=True)


class BookingORM(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    master_id = Column(Integer, ForeignKey("master_profiles.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.CONFIRMED)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "master_id",
            "client_id",
            "service_id",
            "start_at",
            name="uq_booking_idempotent",
        ),
    )

