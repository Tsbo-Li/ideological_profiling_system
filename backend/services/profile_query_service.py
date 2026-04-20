from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import Profile, Student


class ProfileQueryService:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def list_profiles(self, *, period: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            stmt = (
                select(Profile, Student)
                .join(Student, Student.id == Profile.student_id)
                .order_by(Profile.student_id.asc())
                .limit(limit)
                .offset(offset)
            )
            if period:
                stmt = stmt.where(Profile.period == period)
            rows = session.execute(stmt).all()

        items: list[dict[str, Any]] = []
        for profile, student in rows:
            item = profile.to_dict()
            item["student"] = {
                "id": student.id,
                "student_no": student.student_no,
                "name": student.name,
                "major": student.major,
                "grade": student.grade,
            }
            items.append(item)
        return items

    def clustering_summary(self, *, period: str | None) -> dict[str, Any]:
        with self._session_factory() as session:
            numeric_stmt = (
                select(Profile.numeric_cluster_id, func.count(Profile.id))
                .group_by(Profile.numeric_cluster_id)
                .order_by(Profile.numeric_cluster_id.asc())
            )
            text_stmt = (
                select(Profile.text_cluster_id, func.count(Profile.id))
                .group_by(Profile.text_cluster_id)
                .order_by(Profile.text_cluster_id.asc())
            )
            if period:
                numeric_stmt = numeric_stmt.where(Profile.period == period)
                text_stmt = text_stmt.where(Profile.period == period)

            numeric_rows = session.execute(numeric_stmt).all()
            text_rows = session.execute(text_stmt).all()

        return {
            "numeric": [{"cluster_id": cid, "count": cnt} for cid, cnt in numeric_rows],
            "text": [{"topic_id": tid, "count": cnt} for tid, cnt in text_rows],
        }

