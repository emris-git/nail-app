from __future__ import annotations

import hmac
import json
import time as time_mod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import (
    AvailabilitySlotORM,
    BookingORM,
    ClientProfileORM,
    ClientSavedMasterORM,
    MasterProfileORM,
    ServiceORM,
    WorkingWindowORM,
)
from nail_app_core.domain.booking_rules import generate_slots_for_service
from nail_app_core.domain.models import Booking, BookingStatus, Service, WorkingWindow
from nail_app_core.services import BookingService, CreateBookingParams, SlotAlreadyBookedError

router = APIRouter(prefix="/client", tags=["client"])


def _require_db() -> Session:
    return get_session_maker()()


@dataclass(frozen=True)
class ClientAuth:
    tg_user_id: int


async def _require_client_auth(request: Request) -> ClientAuth:
    settings = get_settings()
    secret = settings.client_api_hmac_secret
    if not secret:
        raise HTTPException(status_code=500, detail="CLIENT_API_HMAC_SECRET is not set")

    ts = request.headers.get("X-Client-Bot-Timestamp")
    sig = request.headers.get("X-Client-Bot-Signature")
    user_id = request.headers.get("X-Tg-User-Id")
    if not ts or not sig or not user_id:
        raise HTTPException(status_code=401, detail="Missing auth headers")

    try:
        ts_i = int(ts)
        user_id_i = int(user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Bad auth headers")

    now = int(time_mod.time())
    if abs(now - ts_i) > 60:
        raise HTTPException(status_code=401, detail="Auth timestamp expired")

    body_bytes = await request.body()
    body = body_bytes.decode("utf-8") if body_bytes else ""
    msg = f"{ts_i}.{request.method}.{request.url.path}.{body}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), msg, sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="Bad signature")

    return ClientAuth(tg_user_id=user_id_i)


class MasterOut(BaseModel):
    id: int
    display_name: str
    slug: str
    timezone: str


class ServiceOut(BaseModel):
    id: int
    name: str
    price: float
    duration_minutes: int


class AvailabilityResponse(BaseModel):
    master_slug: str
    from_date: date
    to_date: date
    slots: list[dict[str, str]] = Field(
        ..., description="List of {date:'YYYY-MM-DD', time:'HH:MM'} in master's timezone"
    )


class CreateBookingIn(BaseModel):
    master_slug: str
    service_id: int
    start_at: datetime = Field(..., description="Timezone-aware datetime in master's timezone")


class BookingOut(BaseModel):
    id: int
    master_id: int
    service_id: int
    start_at: datetime
    end_at: datetime
    status: str


def _orm_booking_to_domain(b: BookingORM) -> Booking:
    return Booking(
        id=b.id,
        master_id=b.master_id,
        client_id=b.client_id,
        service_id=b.service_id,
        start_at=b.start_at,
        end_at=b.end_at,
        status=BookingStatus(str(b.status)),
        created_at=b.created_at,
    )


def _orm_service_to_domain(s: ServiceORM) -> Service:
    return Service(
        id=s.id,
        master_id=s.master_id,
        name=s.name,
        price=float(s.price),
        duration_minutes=int(s.duration_minutes),
        is_active=bool(s.is_active),
    )


def _orm_windows_to_domain(windows: Iterable[WorkingWindowORM]) -> list[WorkingWindow]:
    out: list[WorkingWindow] = []
    for w in windows:
        out.append(
            WorkingWindow(
                id=w.id,
                master_id=w.master_id,
                weekday=int(w.weekday),
                start_time=w.start_time,
                end_time=w.end_time,
            )
        )
    return out


@router.get("/masters", response_model=list[MasterOut])
def list_masters(db: Session = Depends(_require_db), _: ClientAuth = Depends(_require_client_auth)):
    masters = db.query(MasterProfileORM).order_by(MasterProfileORM.display_name).all()
    return [
        MasterOut(id=m.id, display_name=m.display_name, slug=m.slug, timezone=m.timezone) for m in masters
    ]


@router.get("/masters/{slug}", response_model=MasterOut)
def get_master(slug: str, db: Session = Depends(_require_db), _: ClientAuth = Depends(_require_client_auth)):
    master = db.query(MasterProfileORM).filter(MasterProfileORM.slug == slug).one_or_none()
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    return MasterOut(id=master.id, display_name=master.display_name, slug=master.slug, timezone=master.timezone)


@router.get("/masters/{slug}/services", response_model=list[ServiceOut])
def list_services(slug: str, db: Session = Depends(_require_db), _: ClientAuth = Depends(_require_client_auth)):
    master = db.query(MasterProfileORM).filter(MasterProfileORM.slug == slug).one_or_none()
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    services = (
        db.query(ServiceORM)
        .filter(ServiceORM.master_id == master.id, ServiceORM.is_active.is_(True))
        .order_by(ServiceORM.id)
        .all()
    )
    return [ServiceOut(id=s.id, name=s.name, price=float(s.price), duration_minutes=s.duration_minutes) for s in services]


@router.get("/masters/{slug}/availability", response_model=AvailabilityResponse)
def get_availability(
    slug: str,
    service_id: int,
    days: int = 14,
    db: Session = Depends(_require_db),
    _: ClientAuth = Depends(_require_client_auth),
):
    if days < 1 or days > 31:
        raise HTTPException(status_code=400, detail="days must be 1..31")

    master = db.query(MasterProfileORM).filter(MasterProfileORM.slug == slug).one_or_none()
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    service = db.get(ServiceORM, service_id)
    if service is None or service.master_id != master.id or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found")

    tz = ZoneInfo(master.timezone)
    today_local = datetime.now(tz).date()
    to_date = today_local + timedelta(days=days - 1)

    # Bookings in range
    range_start = datetime.combine(today_local, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    range_end = datetime.combine(to_date, time(23, 59), tzinfo=tz).astimezone(timezone.utc)
    bookings_orm = (
        db.query(BookingORM)
        .filter(BookingORM.master_id == master.id)
        .filter(BookingORM.start_at < range_end)
        .filter(BookingORM.end_at > range_start)
        .all()
    )
    bookings = [_orm_booking_to_domain(b) for b in bookings_orm]

    # Prefer explicit availability slots if master uses them
    any_slots = db.query(AvailabilitySlotORM.id).filter(AvailabilitySlotORM.master_id == master.id).limit(1).first()
    slots_out: list[dict[str, str]] = []
    if any_slots:
        all_slots = (
            db.query(AvailabilitySlotORM)
            .filter(AvailabilitySlotORM.master_id == master.id)
            .filter(AvailabilitySlotORM.slot_date >= today_local)
            .filter(AvailabilitySlotORM.slot_date <= to_date)
            .order_by(AvailabilitySlotORM.slot_date, AvailabilitySlotORM.slot_time)
            .all()
        )
        booked_set: set[tuple[date, time]] = set()
        for b in bookings_orm:
            local = b.start_at.astimezone(tz)
            booked_set.add((local.date(), time(local.hour, local.minute)))

        now_local = datetime.now(tz)
        for s in all_slots:
            if (s.slot_date, s.slot_time) in booked_set:
                continue
            dt_local = datetime(
                s.slot_date.year,
                s.slot_date.month,
                s.slot_date.day,
                s.slot_time.hour,
                s.slot_time.minute,
                tzinfo=tz,
            )
            if dt_local < now_local:
                continue
            slots_out.append({"date": s.slot_date.isoformat(), "time": s.slot_time.strftime("%H:%M")})
    else:
        # Generate from weekly windows
        windows = (
            db.query(WorkingWindowORM)
            .filter(WorkingWindowORM.master_id == master.id)
            .order_by(WorkingWindowORM.weekday, WorkingWindowORM.start_time)
            .all()
        )
        windows_d = _orm_windows_to_domain(windows)
        service_d = _orm_service_to_domain(service)

        windows_by_weekday: dict[int, list[WorkingWindow]] = {}
        for w in windows_d:
            windows_by_weekday.setdefault(w.weekday, []).append(w)

        now_local = datetime.now(tz)
        cur = today_local
        while cur <= to_date:
            ww = windows_by_weekday.get(cur.weekday(), [])
            if ww:
                generated = generate_slots_for_service(
                    target_date=cur,
                    service=service_d,
                    working_windows=ww,
                    existing_bookings=bookings,
                    tz=tz,
                )
                for g in generated:
                    if g.start_at < now_local:
                        continue
                    slots_out.append({"date": cur.isoformat(), "time": g.start_at.strftime("%H:%M")})
            cur += timedelta(days=1)

    return AvailabilityResponse(master_slug=slug, from_date=today_local, to_date=to_date, slots=slots_out)


@router.get("/clients/me")
def get_me(db: Session = Depends(_require_db), auth: ClientAuth = Depends(_require_client_auth)):
    client = db.query(ClientProfileORM).filter(ClientProfileORM.tg_user_id == auth.tg_user_id).one_or_none()
    if client is None:
        return {"tg_user_id": auth.tg_user_id, "exists": False}
    return {
        "exists": True,
        "id": client.id,
        "tg_user_id": client.tg_user_id,
        "name": client.name,
        "username": client.username,
        "phone": client.phone,
    }


@router.get("/clients/me/favorites")
def list_favorites(db: Session = Depends(_require_db), auth: ClientAuth = Depends(_require_client_auth)):
    rows = (
        db.query(ClientSavedMasterORM, MasterProfileORM)
        .join(MasterProfileORM, MasterProfileORM.id == ClientSavedMasterORM.master_id)
        .filter(ClientSavedMasterORM.tg_user_id == auth.tg_user_id)
        .order_by(MasterProfileORM.display_name)
        .all()
    )
    return [{"master_id": m.id, "slug": m.slug, "display_name": m.display_name} for _, m in rows]


class FavoriteIn(BaseModel):
    master_slug: str


@router.post("/clients/me/favorites", status_code=status.HTTP_204_NO_CONTENT)
def add_favorite(payload: FavoriteIn, db: Session = Depends(_require_db), auth: ClientAuth = Depends(_require_client_auth)):
    master = db.query(MasterProfileORM).filter(MasterProfileORM.slug == payload.master_slug).one_or_none()
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    exists = (
        db.query(ClientSavedMasterORM)
        .filter(ClientSavedMasterORM.tg_user_id == auth.tg_user_id, ClientSavedMasterORM.master_id == master.id)
        .first()
    )
    if not exists:
        db.add(ClientSavedMasterORM(tg_user_id=auth.tg_user_id, master_id=master.id))
        db.commit()
    return None


@router.delete("/clients/me/favorites/{master_slug}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(master_slug: str, db: Session = Depends(_require_db), auth: ClientAuth = Depends(_require_client_auth)):
    master = db.query(MasterProfileORM).filter(MasterProfileORM.slug == master_slug).one_or_none()
    if master is None:
        return None
    (
        db.query(ClientSavedMasterORM)
        .filter(ClientSavedMasterORM.tg_user_id == auth.tg_user_id, ClientSavedMasterORM.master_id == master.id)
        .delete()
    )
    db.commit()
    return None


@router.get("/clients/me/bookings")
def list_my_bookings(db: Session = Depends(_require_db), auth: ClientAuth = Depends(_require_client_auth)):
    client = db.query(ClientProfileORM).filter(ClientProfileORM.tg_user_id == auth.tg_user_id).one_or_none()
    if client is None:
        return {"items": []}
    items = (
        db.query(BookingORM, MasterProfileORM, ServiceORM)
        .join(MasterProfileORM, MasterProfileORM.id == BookingORM.master_id)
        .join(ServiceORM, ServiceORM.id == BookingORM.service_id)
        .filter(BookingORM.client_id == client.id)
        .order_by(BookingORM.start_at.desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for b, m, s in items:
        out.append(
            {
                "id": b.id,
                "status": str(b.status),
                "start_at": b.start_at,
                "end_at": b.end_at,
                "master": {"id": m.id, "slug": m.slug, "display_name": m.display_name, "timezone": m.timezone},
                "service": {"id": s.id, "name": s.name, "price": float(s.price), "duration_minutes": s.duration_minutes},
            }
        )
    return {"items": out}


@router.post("/bookings", response_model=BookingOut)
def create_booking(
    payload: CreateBookingIn,
    db: Session = Depends(_require_db),
    auth: ClientAuth = Depends(_require_client_auth),
):
    master = db.query(MasterProfileORM).filter(MasterProfileORM.slug == payload.master_slug).one_or_none()
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    service = db.get(ServiceORM, payload.service_id)
    if service is None or service.master_id != master.id or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found")

    if payload.start_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="start_at must be timezone-aware")

    # Ensure we treat the timestamp in master's timezone
    master_tz = ZoneInfo(master.timezone)
    start_local = payload.start_at.astimezone(master_tz)
    end_local = start_local + timedelta(minutes=int(service.duration_minutes))

    # If explicit availability slots exist, enforce it
    any_slots = db.query(AvailabilitySlotORM.id).filter(AvailabilitySlotORM.master_id == master.id).limit(1).first()
    if any_slots:
        slot_exists = (
            db.query(AvailabilitySlotORM)
            .filter(
                AvailabilitySlotORM.master_id == master.id,
                AvailabilitySlotORM.slot_date == start_local.date(),
                AvailabilitySlotORM.slot_time == time(start_local.hour, start_local.minute),
            )
            .first()
        )
        if not slot_exists:
            raise HTTPException(status_code=409, detail="Slot not available")

    client = db.query(ClientProfileORM).filter(ClientProfileORM.tg_user_id == auth.tg_user_id).one_or_none()
    if client is None:
        client = ClientProfileORM(tg_user_id=auth.tg_user_id, name="Клиент")
        db.add(client)
        db.flush()

    booking_service = BookingService(db=db)
    try:
        booking = booking_service.create_booking_atomic(
            CreateBookingParams(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at_utc=start_local.astimezone(timezone.utc),
                end_at_utc=end_local.astimezone(timezone.utc),
            )
        )
        db.commit()
    except SlotAlreadyBookedError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Slot already booked")

    return BookingOut(
        id=booking.id,
        master_id=booking.master_id,
        service_id=booking.service_id,
        start_at=booking.start_at,
        end_at=booking.end_at,
        status=str(booking.status),
    )


@router.post("/bookings/{booking_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(_require_db),
    auth: ClientAuth = Depends(_require_client_auth),
):
    client = db.query(ClientProfileORM).filter(ClientProfileORM.tg_user_id == auth.tg_user_id).one_or_none()
    if client is None:
        return None
    booking = (
        db.query(BookingORM)
        .filter(BookingORM.id == booking_id, BookingORM.client_id == client.id)
        .one_or_none()
    )
    if booking is None:
        return None
    booking.status = "CANCELLED"
    db.commit()
    return None

