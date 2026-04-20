from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.base_repository import BaseRepository
from database.models import Profile, Student


class ProfileRepository(BaseRepository):
    def __init__(self, session_factory: Callable[[], Session]):
        super().__init__(session_factory)

    def get_by_student_id(self, student_id: int, period: Optional[str] = None) -> Optional[Profile]:
        period = period or datetime.now().strftime("%Y-%m")
        with self.session_scope() as session:
            stmt = select(Profile).where(Profile.student_id == student_id, Profile.period == period)
            return session.execute(stmt).scalars().first()

    def upsert_for_student(self, student_id: int, payload: dict[str, Any], period: Optional[str] = None) -> Optional[Profile]:
        period = period or payload.get("period") or datetime.now().strftime("%Y-%m")
        with self.session_scope() as session:
            student = session.get(Student, student_id)
            if not student:
                return None

            stmt = select(Profile).where(Profile.student_id == student_id, Profile.period == period)
            profile = session.execute(stmt).scalars().first()
            if not profile:
                profile = Profile(student_id=student_id, period=period)
                session.add(profile)

            for key in (
                "warning_score",
                "numeric_cluster_id",
                "text_cluster_id",
                "numeric_tags",
                "text_tags",
                "feature_summary",
                "warning_status",
                "warning_handler",
                "warning_note",
                "warning_handled_at",
            ):
                if key in payload:
                    setattr(profile, key, payload.get(key))

            session.flush()
            session.refresh(profile)
            return profile

