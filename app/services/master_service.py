from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.adapters.llm.base import PriceListParser
from app.db import models as orm


@dataclass
class MasterOnboardingResult:
    master_id: int
    slug: str


class MasterOnboardingService:
    def __init__(self, db: Session, price_list_parser: PriceListParser) -> None:
        self._db = db
        self._parser = price_list_parser

    def ensure_master_user(self, tg_user_id: int, username: Optional[str]) -> orm.UserORM:
        user = self._db.query(orm.UserORM).filter_by(id=tg_user_id).one_or_none()
        if user is None:
            user = orm.UserORM(id=tg_user_id, username=username, is_master=True)
            self._db.add(user)
            self._db.commit()
        return user

    async def create_master_profile(
        self, tg_user_id: int, display_name: str, timezone: str
    ) -> MasterOnboardingResult:
        user = self.ensure_master_user(tg_user_id, None)

        profile = (
            self._db.query(orm.MasterProfileORM).filter_by(user_id=user.id).one_or_none()
        )
        if profile is not None:
            profile.display_name = display_name
            profile.timezone = timezone
            self._db.commit()
            self._db.refresh(profile)
            return MasterOnboardingResult(master_id=profile.id, slug=profile.slug)

        slug = f"m{tg_user_id}"
        profile = orm.MasterProfileORM(
            user_id=user.id,
            display_name=display_name,
            timezone=timezone,
            slug=slug,
            onboarded=False,
        )
        self._db.add(profile)
        self._db.commit()
        self._db.refresh(profile)
        return MasterOnboardingResult(master_id=profile.id, slug=profile.slug)

