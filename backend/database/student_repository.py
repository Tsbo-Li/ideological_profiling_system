from __future__ import annotations

from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.base_repository import BaseRepository
from database.models import Student


class StudentRepository(BaseRepository):
    def __init__(self, session_factory: Callable[[], Session]):
        super().__init__(session_factory)

    def list(self, *, limit: int = 50, offset: int = 0) -> list[Student]:
        with self.session_scope() as session:
            stmt = select(Student).order_by(Student.id.asc()).limit(limit).offset(offset)
            return list(session.execute(stmt).scalars().all())

    def get_by_id(self, student_id: int) -> Optional[Student]:
        with self.session_scope() as session:
            return session.get(Student, student_id)

    def create(self, payload: dict[str, Any]) -> Student:
        with self.session_scope() as session:
            student = Student(
                student_no=payload.get("student_no"),
                name=payload.get("name") or "",
                gender=payload.get("gender"),
                grade=payload.get("grade"),
                major=payload.get("major"),
            )
            session.add(student)
            session.flush()
            session.refresh(student)
            return student

    def update(self, student_id: int, payload: dict[str, Any]) -> Optional[Student]:
        with self.session_scope() as session:
            student = session.get(Student, student_id)
            if not student:
                return None
            for key in ("student_no", "name", "gender", "grade", "major"):
                if key in payload:
                    setattr(student, key, payload.get(key))
            session.flush()
            session.refresh(student)
            return student

    def delete(self, student_id: int) -> bool:
        with self.session_scope() as session:
            student = session.get(Student, student_id)
            if not student:
                return False
            session.delete(student)
            return True

