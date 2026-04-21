from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    major: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    gpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    numeric_data: Mapped[list["StudentNumericData"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )
    text_data: Mapped[list["StudentTextData"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )
    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "student_no": self.student_no,
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "grade": self.grade,
            "major": self.major,
            "gpa": self.gpa,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StudentNumericData(Base):
    __tablename__ = "student_numeric_data"
    __table_args__ = (UniqueConstraint("student_id", "period", name="uq_student_numeric_data_student_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM

    # Incremental monthly numeric indicators
    library_visits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    signin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    course_submit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    online_duration_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    correct_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    student: Mapped["Student"] = relationship(back_populates="numeric_data")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "period": self.period,
            "library_visits": self.library_visits,
            "signin_count": self.signin_count,
            "course_submit_count": self.course_submit_count,
            "online_duration_min": self.online_duration_min,
            "avg_score": self.avg_score,
            "correct_rate": self.correct_rate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StudentTextData(Base):
    __tablename__ = "student_text_data"

    text_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    period: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, index=True)  # YYYY-MM
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    text_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    student: Mapped["Student"] = relationship(back_populates="text_data")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_id": self.text_id,
            "student_id": self.student_id,
            "period": self.period,
            "source": self.source,
            "text_type": self.text_type,
            "content": self.content,
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Profile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint("student_id", "period", name="uq_student_profiles_student_period"),
        CheckConstraint(
            "warning_status IN ('pending','processing','resolved','ignored')",
            name="ck_student_profiles_warning_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM

    warning_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    numeric_cluster_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    text_cluster_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    numeric_tags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    text_tags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    feature_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    warning_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    warning_handler: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    warning_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warning_handled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    student: Mapped["Student"] = relationship(back_populates="profiles")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "period": self.period,
            "warning_score": self.warning_score,
            "numeric_cluster_id": self.numeric_cluster_id,
            "text_cluster_id": self.text_cluster_id,
            "numeric_tags": self.numeric_tags,
            "text_tags": self.text_tags,
            "feature_summary": self.feature_summary,
            "warning_status": self.warning_status,
            "warning_handler": self.warning_handler,
            "warning_note": self.warning_note,
            "warning_handled_at": self.warning_handled_at.isoformat() if self.warning_handled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SocialHotTopic(Base):
    __tablename__ = "social_hot_topics"
    __table_args__ = (
        UniqueConstraint("topic_key", name="uq_social_hot_topics_topic_key"),
        CheckConstraint("status IN ('active','expired','blocked')", name="ck_social_hot_topics_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="weibo", server_default="weibo", index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    heat_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    keywords: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active", index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic_key": self.topic_key,
            "title": self.title,
            "summary": self.summary,
            "platform": self.platform,
            "source_url": self.source_url,
            "heat_score": self.heat_score,
            "keywords": self.keywords,
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "status": self.status,
            "is_verified": bool(self.is_verified),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ContentDraft(Base):
    __tablename__ = "content_drafts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('article','video','video_prompt')",
            name="ck_content_drafts_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ContentGenerationJob(Base):
    __tablename__ = "content_generation_jobs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('article','video','video_prompt')",
            name="ck_content_generation_jobs_kind",
        ),
        CheckConstraint(
            "status IN ('pending','running','done','error','cancelled')",
            name="ck_content_generation_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending", index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    error_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    draft_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "text": self.text,
            "error_message": self.error_message,
            "draft_id": self.draft_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

