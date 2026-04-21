from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import threading
import time
import re
from typing import Any, Callable

import jieba
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import ContentDraft, ContentGenerationJob, Profile, SocialHotTopic, Student, StudentNumericData, StudentTextData
from services.ai_talking_service import AiTalkingService


class CounselorApiService:
    """Aggregate data for counselor-facing frontend endpoints."""

    def __init__(self, session_factory: Callable[[], Session], ai_talking_service: AiTalkingService | None = None):
        self._session_factory = session_factory
        self._text_embedding_model = None
        self._text_embedding_cache: dict[tuple, tuple[dict[int, np.ndarray], int]] = {}
        self._wordcloud_stopwords: set[str] | None = None
        self._wordcloud_stopwords_mtime: float | None = None
        self._ai_talking_service = ai_talking_service or AiTalkingService()
        self._content_job_threads: dict[int, threading.Thread] = {}
        self._content_job_lock = threading.Lock()
        # In-memory cache for resumable streaming (avoid polling DB during streaming).
        # NOTE: cache is per-process; server restart will lose in-flight jobs.
        self._content_job_cache: dict[int, dict[str, Any]] = {}

    def get_frontend_profile(self, student_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            student = self._find_student(session, student_id)
            if student is None:
                return None

            profile = session.execute(
                select(Profile)
                .where(Profile.student_id == student.id)
                .order_by(Profile.period.desc(), Profile.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if profile is None:
                return None

            return self._build_profile(student, profile)

    def get_clusters(self, method: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            if method == "text_topic":
                rows = session.execute(
                    select(Profile.text_cluster_id, func.count(Profile.id))
                    .group_by(Profile.text_cluster_id)
                    .order_by(Profile.text_cluster_id.asc())
                ).all()
                label_map = self._build_cluster_label_map(kind="text")
                items: list[dict[str, Any]] = []
                for topic_id, count in rows:
                    label = label_map.get(topic_id, {})
                    fallback_display = f"主题{topic_id}" if topic_id is not None else "离群主题（未归类文本）"
                    label_display = str(label.get("label_display") or fallback_display)
                    label_code = str(label.get("label_code") or (f"topic_{topic_id}" if topic_id is not None else "topic_outlier"))
                    items.append(
                        {
                            "topic_id": topic_id,
                            "label_display": label_display,
                            "label_code": label_code,
                            "name": label_display,  # keep frontend compatibility
                            "value": count,
                        }
                    )
                return items

            if method == "temporal":
                rows = session.execute(
                    select(Profile.warning_status, func.count(Profile.id))
                    .group_by(Profile.warning_status)
                    .order_by(Profile.warning_status.asc())
                ).all()
                return [{"name": status or "unknown", "value": count} for status, count in rows]

            rows = session.execute(
                select(Profile.numeric_cluster_id, func.count(Profile.id))
                .group_by(Profile.numeric_cluster_id)
                .order_by(Profile.numeric_cluster_id.asc())
            ).all()
            label_map = self._build_cluster_label_map(kind="numeric")
            items: list[dict[str, Any]] = []
            for cluster_id, count in rows:
                label = label_map.get(cluster_id, {})
                fallback_display = f"群组 {cluster_id if cluster_id is not None else '未分配'}"
                label_display = str(label.get("label_display") or fallback_display)
                label_code = str(label.get("label_code") or (f"cluster_{cluster_id}" if cluster_id is not None else "cluster_unassigned"))
                items.append(
                    {
                        "cluster_id": cluster_id,
                        "label_display": label_display,
                        "label_code": label_code,
                        "name": label_display,  # keep frontend compatibility
                        "value": count,
                    }
                )
            return items

    def get_dashboard(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=6)).date()
        days = [start + timedelta(days=i) for i in range(7)]
        day_keys = [d.strftime("%m-%d") for d in days]

        with self._session_factory() as session:
            total_students = session.execute(select(func.count(Student.id))).scalar_one()
            warning_students = session.execute(
                select(func.count(Profile.id)).where(Profile.warning_score.isnot(None))
            ).scalar_one()
            high_risk_students = session.execute(
                select(func.count(Profile.id)).where(Profile.warning_score >= 70)
            ).scalar_one()
            in_progress_tasks = session.execute(
                select(func.count(Profile.id)).where(Profile.warning_status.in_(["pending", "processing"]))
            ).scalar_one()
            closed_tasks = session.execute(
                select(func.count(Profile.id)).where(Profile.warning_status.in_(["resolved", "ignored"]))
            ).scalar_one()

            # Trend: count warning triggers per day in last 7 days.
            trend_rows = session.execute(
                select(Profile.updated_at, Profile.warning_score)
                .where(Profile.updated_at.isnot(None))
                .where(Profile.updated_at >= (now - timedelta(days=7)))
                .where(Profile.warning_score.isnot(None))
            ).all()
            counter: dict[str, int] = {k: 0 for k in day_keys}
            for updated_at, score in trend_rows:
                if not isinstance(updated_at, datetime):
                    continue
                d = updated_at.date()
                key = d.strftime("%m-%d")
                if key not in counter:
                    continue
                # Treat any non-null score as a trigger.
                try:
                    _ = float(score or 0)
                except Exception:
                    continue
                counter[key] += 1

            # Alerts: latest pending/processing profiles with warning_score (include student_no for navigation).
            alert_rows = session.execute(
                select(Profile, Student)
                .join(Student, Student.id == Profile.student_id)
                .where(Profile.warning_score.isnot(None))
                .where(Profile.warning_status.in_(["pending", "processing"]))
                .order_by(Profile.updated_at.desc().nullslast(), Profile.created_at.desc())
                .limit(30)
            ).all()

        warning_trend = [{"day": k, "value": int(counter.get(k, 0))} for k in day_keys]

        alerts: list[dict[str, Any]] = []
        for p, s in alert_rows:
            score = float(p.warning_score or 0)
            risk = self._risk_level_from_score(score)
            if risk != "high":
                continue
            numeric_tags = p.numeric_tags if isinstance(p.numeric_tags, dict) else {}
            text_tags = p.text_tags if isinstance(p.text_tags, dict) else {}
            numeric_label = (
                numeric_tags.get("label_display")
                if isinstance(numeric_tags.get("label_display"), str) and str(numeric_tags.get("label_display")).strip()
                else ""
            )
            text_label = (
                text_tags.get("label_display")
                if isinstance(text_tags.get("label_display"), str) and str(text_tags.get("label_display")).strip()
                else ""
            )
            if not numeric_label:
                numeric_label = "未分配"
            if not text_label:
                text_label = "未分配"
            student_no = str(getattr(s, "student_no", "") or "").strip()
            class_name = " ".join([x for x in [getattr(s, "grade", None), getattr(s, "major", None)] if x]) or "未分班级"
            summary = f"数值簇：{numeric_label}；文本簇：{text_label}"

            alerts.append(
                {
                    "id": f"w-{p.id}",
                    "student_id": student_no,
                    "class_name": class_name,
                    "numeric_cluster_label": numeric_label,
                    "text_cluster_label": text_label,
                    "title": f"{student_no}（分数 {round(score, 1)}）",
                    "risk_level": risk,
                    "summary": summary,
                    "created_at": self._to_iso(p.updated_at) or self._to_iso(p.created_at) or "",
                }
            )

        grouped_hot_topics = self.get_hot_topics(limit_per_platform=10)
        dashboard_hot_topics: list[dict[str, Any]] = []
        for platform_items in grouped_hot_topics.values():
            dashboard_hot_topics.extend(platform_items[:3])

        return {
            "kpis": {
                "totalStudents": int(total_students or 0),
                "warningStudents": int(warning_students or 0),
                "highRiskStudents": int(high_risk_students or 0),
                "inProgressTasks": int(in_progress_tasks or 0),
                "closedTasks": int(closed_tasks or 0),
            },
            "groupDistribution": self.get_clusters("behavior_kmeans"),
            "warningTrend": warning_trend,
            "alerts": alerts[:10],
            "hot_topics": dashboard_hot_topics[:10],
        }

    def get_hot_topics(self, *, platform: str | None = None, limit_per_platform: int = 10) -> dict[str, list[dict[str, Any]]]:
        limit_per_platform = max(1, min(int(limit_per_platform or 10), 50))
        allowed_platforms = {"weibo", "douyin", "xiaohongshu", "bilibili"}
        platform = (platform or "").strip().lower()
        with self._session_factory() as session:
            rows = session.execute(
                select(SocialHotTopic)
                .where(SocialHotTopic.status == "active")
                .order_by(
                    SocialHotTopic.is_verified.desc(),
                    SocialHotTopic.heat_score.desc().nullslast(),
                    SocialHotTopic.event_time.desc().nullslast(),
                    SocialHotTopic.captured_at.desc().nullslast(),
                    SocialHotTopic.created_at.desc(),
                )
                .limit(2000)
            ).scalars().all()

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            p = str(row.platform or "").strip().lower()
            if p not in allowed_platforms:
                continue
            if platform and p != platform:
                continue
            if len(grouped[p]) >= limit_per_platform:
                continue
            grouped[p].append(
                {
                    "id": f"hot-{row.id}",
                    "platform": p,
                    "title": str(row.title or "").strip(),
                    "summary": str(row.summary or "").strip() or None,
                    "heat_score": float(row.heat_score) if row.heat_score is not None else None,
                    "heat_label": "高" if (row.heat_score or 0) >= 80 else ("中高" if (row.heat_score or 0) >= 50 else "中"),
                    "source_url": str(row.source_url or "").strip() or None,
                    "captured_at": self._to_iso(row.captured_at) or self._to_iso(row.created_at) or datetime.now().isoformat(timespec="seconds"),
                    "event_time": self._to_iso(row.event_time) or self._to_iso(row.captured_at) or None,
                }
            )

        if platform:
            return {platform: grouped.get(platform, [])}
        # Keep a stable platform order for frontend tabs.
        ordered = ["weibo", "douyin", "xiaohongshu", "bilibili"]
        return {p: grouped.get(p, []) for p in ordered if grouped.get(p, [])}

    def get_hot_topics_page(self, *, platform: str, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        platform = (platform or "").strip().lower()
        if platform not in {"douyin", "bilibili"}:
            platform = "douyin"
        limit = max(1, min(int(limit or 10), 50))
        offset = max(0, int(offset or 0))

        with self._session_factory() as session:
            rows = session.execute(
                select(SocialHotTopic)
                .where(SocialHotTopic.status == "active")
                .order_by(
                    SocialHotTopic.is_verified.desc(),
                    SocialHotTopic.heat_score.desc().nullslast(),
                    SocialHotTopic.event_time.desc().nullslast(),
                    SocialHotTopic.captured_at.desc().nullslast(),
                    SocialHotTopic.created_at.desc(),
                )
                .limit(5000)
            ).scalars().all()

        # Keep platform normalization consistent with grouped endpoint.
        filtered: list[SocialHotTopic] = []
        for row in rows:
            p = str(row.platform or "").strip().lower()
            if p == platform:
                filtered.append(row)
        total = len(filtered)
        page_rows = filtered[offset : offset + limit]

        items: list[dict[str, Any]] = []
        for row in page_rows:
            items.append(
                {
                    "id": f"hot-{row.id}",
                    "platform": platform,
                    "title": str(row.title or "").strip(),
                    "summary": str(row.summary or "").strip() or None,
                    "heat_score": float(row.heat_score) if row.heat_score is not None else None,
                    "heat_label": "高" if (row.heat_score or 0) >= 80 else ("中高" if (row.heat_score or 0) >= 50 else "中"),
                    "source_url": str(row.source_url or "").strip() or None,
                    "captured_at": self._to_iso(row.captured_at) or self._to_iso(row.created_at) or datetime.now().isoformat(timespec="seconds"),
                    "event_time": self._to_iso(row.event_time) or self._to_iso(row.captured_at) or None,
                }
            )
        return {"platform": platform, "items": items, "total": total, "limit": limit, "offset": offset}

    def get_groups(self, method: str = "numeric") -> list[dict[str, Any]]:
        method = (method or "numeric").strip().lower()
        if method not in {"numeric", "text"}:
            method = "numeric"

        rows = self._latest_profile_rows()
        grouped: dict[int | None, list[tuple[Profile, Student]]] = defaultdict(list)
        for profile, student in rows:
            key = profile.numeric_cluster_id if method == "numeric" else profile.text_cluster_id
            grouped[key].append((profile, student))
        student_text_keywords = self._load_student_content_keywords(
            [student.id for _profile, student in rows]
        )
        label_map = self._build_cluster_label_map(kind="numeric" if method == "numeric" else "text")

        items: list[dict[str, Any]] = []
        for cluster_id, members in sorted(grouped.items(), key=lambda x: (-len(x[1]), x[0] is None, x[0] or -1)):
            member_count = len(members)
            top_profile, top_student = max(
                members,
                key=lambda x: (x[0].warning_score or 0, x[0].updated_at or x[0].created_at),
            )
            tag_counter: dict[str, int] = defaultdict(int)
            text_tag_counter: dict[str, int] = defaultdict(int)
            for profile, member_student in members:
                if method == "numeric":
                    for tag in self._extract_behavior_tags_from_numeric_tags(profile.numeric_tags):
                        tag_counter[tag] += 1
                else:
                    # For text-group cards, show text-clustering tags as primary tags.
                    for tag in self._extract_text_tags_from_text_tags(profile.text_tags):
                        tag_counter[tag] += 1
                text_tags = student_text_keywords.get(member_student.id, [])
                if text_tags:
                    for tag in text_tags:
                        text_tag_counter[tag] += 1
                else:
                    for tag in self._extract_text_tags_from_text_tags(profile.text_tags):
                        text_tag_counter[tag] += 1
            top_tags = [tag for tag, _ in sorted(tag_counter.items(), key=lambda x: (-x[1], x[0]))[:5]]
            top_text_tags = [tag for tag, _ in sorted(text_tag_counter.items(), key=lambda x: (-x[1], x[0]))[:20]]
            if not top_text_tags:
                # ensure the wordcloud block still has meaningful content
                top_text_tags = top_tags

            label_display = (label_map.get(cluster_id, {}) or {}).get("label_display") or ""
            if method == "text":
                fallback = f"主题{cluster_id}" if cluster_id is not None else "离群主题"
            else:
                fallback = f"群组 {cluster_id if cluster_id is not None else '未分配'}"
            group_title = label_display.strip() or fallback
            items.append(
                {
                    "name": group_title,
                    "size": member_count,
                    "topStudent": top_student.student_no,
                    # Keep field name for frontend compatibility; in text mode it represents topic_id.
                    "cluster_label": cluster_id,
                    "representative_behavior_tags": top_tags,
                    "representative_text_tags": top_text_tags,
                }
            )

        if not items:
            return self._demo_groups()

        return items

    def get_students(self, *, keyword: str | None, risk_level: str | None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        rows = self._latest_profile_rows()
        student_text_keywords = self._load_student_content_keywords([student.id for _profile, student in rows])
        risk_level = (risk_level or "").strip().lower()
        keyword = (keyword or "").strip().lower()

        items: list[dict[str, Any]] = []
        for profile, student in rows:
            warning_score = float(profile.warning_score or 0)
            risk = self._risk_level_from_score(warning_score)
            if risk_level in {"high", "medium", "low"} and risk != risk_level:
                continue

            class_name = " ".join([x for x in [student.grade, student.major] if x]) or "未分班级"
            behavior_tags = self._extract_behavior_tags_from_numeric_tags(profile.numeric_tags)
            text_tags = self._extract_text_tags_from_text_tags(profile.text_tags)
            content_tags = student_text_keywords.get(student.id, [])

            tags: list[str] = []
            for t in [*behavior_tags, *text_tags, *content_tags]:
                if t and t not in tags:
                    tags.append(t)
            tags = tags[:8]

            row = {
                "student_id": student.student_no,
                "class_name": class_name,
                "risk_level": risk,
                "latest_warning_score": round(warning_score, 2),
                "latest_active_at": self._to_iso(profile.updated_at) or self._to_iso(profile.created_at) or "",
                "tags": tags,
            }
            if keyword:
                search_text = " ".join([row["student_id"], row["class_name"], " ".join(tags)]).lower()
                if keyword not in search_text:
                    continue
            items.append(row)

        items.sort(key=lambda x: (-float(x["latest_warning_score"]), x["student_id"]))
        total = len(items)
        limit = max(1, min(int(limit or 20), 100))
        offset = max(0, int(offset or 0))
        sliced = items[offset : offset + limit]
        return {"items": sliced, "total": total, "limit": limit, "offset": offset}

    def get_talking_draft(self, student_id: str) -> list[str]:
        context = self.build_talking_context(student_id)
        return self._ai_talking_service.generate_talking_draft(context)

    def update_warning_handling(
        self,
        *,
        student_id: str,
        status: str,
        handler: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        student_id = (student_id or "").strip()
        status = (status or "").strip().lower()
        allowed = {"pending", "processing", "resolved", "ignored"}
        if status not in allowed:
            status = "processing"
        with self._session_factory() as session:
            student = self._find_student(session, student_id)
            if student is None:
                return None
            profile = session.execute(
                select(Profile)
                .where(Profile.student_id == student.id)
                .order_by(Profile.period.desc(), Profile.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if profile is None:
                # Allow handling write even if clustering profile hasn't been generated yet.
                profile = Profile(
                    student_id=student.id,
                    period=datetime.now().strftime("%Y-%m"),
                    warning_score=0.0,
                    warning_status="pending",
                )
                session.add(profile)
                session.flush()

            profile.warning_status = status
            profile.warning_handler = (handler or "").strip()[:128] or None
            profile.warning_note = (note or "").strip()[:2000] or None
            profile.warning_handled_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(profile)
            return self._build_profile(student, profile)

    def recompute_warning_scores(self) -> dict[str, Any]:
        """
        Recompute warning scores using interpretable weighted components.
        Components (0-100):
          - academic_risk: 40%
          - behavior_risk: 30%
          - text_risk: 20%
          - trend_risk: 10%
        """
        rows = self._latest_profile_rows()
        numeric_map = self._latest_numeric_map()

        if not rows:
            return {"updated": 0}

        raw_items: list[dict[str, Any]] = []
        for profile, student in rows:
            nd = numeric_map.get(student.id)
            avg_score = float(nd.avg_score) if nd and nd.avg_score is not None else None
            correct_rate = float(nd.correct_rate) if nd and nd.correct_rate is not None else None
            gpa = float(student.gpa) if student.gpa is not None else None
            online = float(nd.online_duration_min) if nd else 0.0
            signin = float(nd.signin_count) if nd else 0.0
            library = float(nd.library_visits) if nd else 0.0

            text_tags = profile.text_tags if isinstance(profile.text_tags, dict) else {}
            keywords = text_tags.get("keywords") if isinstance(text_tags.get("keywords"), list) else []
            kw_len = float(len([k for k in keywords if str(k).strip()]))
            # Outlier topic is generally less stable/less interpretable; add risk.
            main_topic = text_tags.get("main_topic_id")
            outlier_penalty = 20.0 if main_topic == -1 else 0.0

            def inv01(v: float | None, lo: float, hi: float) -> float:
                if v is None:
                    return 0.5
                if hi <= lo:
                    return 0.0
                p = (v - lo) / (hi - lo)
                p = min(1.0, max(0.0, p))
                return 1.0 - p

            academic_risk = (
                inv01(avg_score, 50.0, 95.0) * 0.45
                + inv01(correct_rate, 0.5, 0.98) * 0.35
                + inv01(gpa, 1.5, 4.0) * 0.20
            ) * 100.0

            behavior_risk = (
                # too high online duration may indicate unhealthy rhythm
                min(1.0, online / 3600.0) * 0.45
                + inv01(signin, 4.0, 50.0) * 0.30
                + inv01(library, 0.0, 30.0) * 0.25
            ) * 100.0

            text_risk = min(100.0, kw_len * 8.0 + outlier_penalty)

            # Trend proxy: if profile already had high warning status pending/processing, keep slight trend pressure.
            trend_risk = 65.0 if profile.warning_status in {"pending", "processing"} else 35.0

            warning_score = (
                academic_risk * 0.40
                + behavior_risk * 0.30
                + text_risk * 0.20
                + trend_risk * 0.10
            )
            warning_score = round(min(100.0, max(0.0, warning_score)), 2)
            raw_items.append(
                {
                    "profile_id": int(profile.id),
                    "warning_score": warning_score,
                    "components": {
                        "academic_risk": round(academic_risk, 2),
                        "behavior_risk": round(behavior_risk, 2),
                        "text_risk": round(text_risk, 2),
                        "trend_risk": round(trend_risk, 2),
                    },
                }
            )

        if not raw_items:
            return {"updated": 0}

        with self._session_factory() as session:
            for item in raw_items:
                profile = session.get(Profile, int(item["profile_id"]))
                if profile is None:
                    continue
                profile.warning_score = float(item["warning_score"])
                summary = profile.feature_summary if isinstance(profile.feature_summary, dict) else {}
                summary = dict(summary)
                summary["warning_scoring"] = {
                    "version": "v1",
                    "weights": {
                        "academic_risk": 0.40,
                        "behavior_risk": 0.30,
                        "text_risk": 0.20,
                        "trend_risk": 0.10,
                    },
                    "components": item["components"],
                    "final_warning_score": item["warning_score"],
                }
                profile.feature_summary = summary
            session.commit()
        return {"updated": len(raw_items)}

    def stream_talking_draft(self, student_id: str):
        context = self.build_talking_context(student_id)
        return self._ai_talking_service.stream_talking_draft(context)

    def get_content_suggestions(self) -> list[dict[str, Any]]:
        context = self.build_content_context()
        return self._ai_talking_service.generate_content_suggestions(context)

    def build_content_context(self) -> dict[str, Any]:
        groups = self.get_groups(method="numeric")
        hot_topics = self._collect_hot_topics()
        group_context = [
            {
                "name": str(g.get("name") or ""),
                "size": int(g.get("size") or 0),
                "behavior_tags": [str(x) for x in (g.get("representative_behavior_tags") or [])[:6]],
                "text_tags": [str(x) for x in (g.get("representative_text_tags") or [])[:6]],
            }
            for g in groups[:6]
        ]
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hot_topics": hot_topics,
            "hot_keywords": [str(x.get("title") or "") for x in hot_topics[:10] if str(x.get("title") or "").strip()],
            "group_labels": [str(x.get("name") or "") for x in group_context if str(x.get("name") or "").strip()],
            "group_profiles": group_context,
            "requirements": {
                "privacy": "禁止输出学号、姓名等任何个人识别信息",
                "deliverables": ["公众号/班会长文草稿（更长、更可用）", "短视频脚本与分镜（可直接编辑）"],
            },
        }

    def stream_content_text(self, *, kind: str):
        kind = (kind or "").strip().lower()
        if kind not in {"article", "video", "video_prompt"}:
            kind = "article"

        context = self.build_content_context()
        # Wrap AI stream to persist draft on done.
        def gen():
            buf: list[str] = []
            last_text: str | None = None
            for evt in self._ai_talking_service.stream_content_text(kind=kind, context=context):
                # Capture deltas for persistence.
                if isinstance(evt, str) and evt.startswith("data:"):
                    try:
                        payload = json.loads(evt.split("data:", 1)[1].strip())
                        if payload.get("type") == "delta" and payload.get("kind") == kind:
                            buf.append(str(payload.get("content") or ""))
                        if payload.get("type") == "done" and payload.get("kind") == kind:
                            last_text = str(payload.get("text") or "")
                    except Exception:
                        pass
                yield evt
            text = (last_text or "".join(buf)).strip()
            if text:
                draft = self.save_content_draft(kind=kind, text=text, context=context)
                yield f"data: {json.dumps({'type':'saved','kind':kind,'draft_id':draft['id']}, ensure_ascii=False)}\n\n"

        return gen()

    def create_content_job(self, *, kind: str) -> dict[str, Any]:
        kind = (kind or "").strip().lower()
        if kind not in {"article", "video", "video_prompt"}:
            kind = "article"
        context = self.build_content_context()
        with self._session_factory() as session:
            # Create a draft immediately so the generation is always recoverable from history.
            draft = ContentDraft(kind=kind, title=None, text="", context=context)
            session.add(draft)
            session.commit()
            session.refresh(draft)

            job = ContentGenerationJob(kind=kind, status="pending", text="", context=context, draft_id=int(draft.id))
            session.add(job)
            session.commit()
            session.refresh(job)
            job_dict = job.to_dict()
        self._ensure_job_running(job_dict["id"])
        return job_dict

    def get_content_job(self, job_id: int) -> dict[str, Any] | None:
        with self._session_factory() as session:
            job = session.get(ContentGenerationJob, int(job_id))
            return job.to_dict() if job else None

    def stream_content_job(self, *, job_id: int, from_offset: int = 0):
        job_id = int(job_id)
        from_offset = max(0, int(from_offset or 0))
        self._ensure_job_running(job_id)

        def sse(payload: dict[str, Any]) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        last_sent = from_offset
        idle_ticks = 0
        while True:
            with self._content_job_lock:
                cached = dict(self._content_job_cache.get(job_id) or {})
            if cached:
                text = str(cached.get("text") or "")
                status = str(cached.get("status") or "pending")
                draft_id = cached.get("draft_id")
                err_msg = cached.get("error_message")
            else:
                # Fallback to DB for completed jobs or if cache missing.
                job = self.get_content_job(job_id)
                if not job:
                    yield sse({"type": "error", "message": "job_not_found"})
                    return
                text = str(job.get("text") or "")
                status = str(job.get("status") or "pending")
                draft_id = job.get("draft_id")
                err_msg = job.get("error_message")

            if last_sent < len(text):
                chunk = text[last_sent:]
                last_sent = len(text)
                idle_ticks = 0
                yield sse({"type": "delta", "job_id": job_id, "from": last_sent - len(chunk), "to": last_sent, "content": chunk})
            else:
                idle_ticks += 1
                # heartbeat every ~10s
                if idle_ticks % 20 == 0:
                    yield sse({"type": "ping", "job_id": job_id, "offset": last_sent, "status": status})

            if status in {"done", "error", "cancelled"}:
                payload = {"type": "done", "job_id": job_id, "status": status, "draft_id": draft_id}
                if err_msg:
                    payload["error_message"] = err_msg
                yield sse(payload)
                return

            time.sleep(0.5)

    def _ensure_job_running(self, job_id: int) -> None:
        job_id = int(job_id)
        with self._content_job_lock:
            t = self._content_job_threads.get(job_id)
            if t and t.is_alive():
                return
            th = threading.Thread(target=self._run_content_job, args=(job_id,), daemon=True)
            self._content_job_threads[job_id] = th
            th.start()

    def _run_content_job(self, job_id: int) -> None:
        job_id = int(job_id)
        # mark running and read config
        with self._session_factory() as session:
            job = session.get(ContentGenerationJob, job_id)
            if not job:
                return
            if job.status in {"done", "error", "cancelled"}:
                return
            job.status = "running"
            session.commit()
            kind = str(job.kind)
            context = job.context if isinstance(job.context, dict) else {}
            draft_id = int(job.draft_id) if getattr(job, "draft_id", None) else None

        with self._content_job_lock:
            self._content_job_cache[job_id] = {
                "id": job_id,
                "kind": kind,
                "status": "running",
                "text": "",
                "draft_id": draft_id,
                "error_message": None,
            }
        try:
            last_persist_ts = 0.0
            last_persist_len = 0
            for evt in self._ai_talking_service.stream_content_text(kind=kind, context=context):
                # parse SSE payload from AiTalkingService
                if not isinstance(evt, str) or not evt.startswith("data:"):
                    continue
                try:
                    payload = json.loads(evt.split("data:", 1)[1].strip())
                except Exception:
                    continue
                if payload.get("type") == "delta" and payload.get("kind") == kind:
                    piece = str(payload.get("content") or "")
                    if piece:
                        with self._content_job_lock:
                            cached = self._content_job_cache.get(job_id)
                            if cached is not None:
                                cached["text"] = str(cached.get("text") or "") + piece
                        # Low-frequency persistence: ensure history can recover even after refresh/navigation.
                        now = time.time()
                        with self._content_job_lock:
                            cached_now = self._content_job_cache.get(job_id) or {}
                            txt_now = str(cached_now.get("text") or "")
                            did = cached_now.get("draft_id")
                        if did and (len(txt_now) - last_persist_len >= 1024 or now - last_persist_ts >= 2.0):
                            try:
                                with self._session_factory() as session:
                                    drow = session.get(ContentDraft, int(did))
                                    if drow:
                                        drow.text = txt_now
                                        session.commit()
                                last_persist_ts = now
                                last_persist_len = len(txt_now)
                            except Exception:
                                # best-effort: streaming must continue even if DB write fails
                                pass
                if payload.get("type") in {"error"} and payload.get("kind") == kind:
                    # still allow fallbacks; store message
                    msg = str(payload.get("message") or "")
                    with self._content_job_lock:
                        cached = self._content_job_cache.get(job_id)
                        if cached is not None:
                            cached["error_message"] = msg[:255]

            # persist draft (final) and mark done
            with self._session_factory() as session:
                job = session.get(ContentGenerationJob, job_id)
                if not job:
                    return
                with self._content_job_lock:
                    cached = self._content_job_cache.get(job_id) or {}
                    cached_text = str(cached.get("text") or "")
                text = cached_text.strip()
                # Update existing draft created when job was submitted.
                if job.draft_id:
                    drow = session.get(ContentDraft, int(job.draft_id))
                else:
                    drow = None
                if drow is None:
                    drow = ContentDraft(kind=kind, title=None, text="", context=job.context if isinstance(job.context, dict) else None)
                    session.add(drow)
                    session.commit()
                    session.refresh(drow)
                    job.draft_id = int(drow.id)
                drow.text = text
                # If article: try extract title on final text.
                if kind == "article":
                    m = re.search(r"^#\s+(.+)$", text.strip(), flags=re.MULTILINE)
                    if m:
                        drow.title = m.group(1).strip()[:255]
                job.status = "done"
                job.text = ""  # job text kept in cache; drafts store final text
                if cached.get("error_message"):
                    job.error_message = str(cached.get("error_message"))[:255]
                session.commit()
            with self._content_job_lock:
                cached = self._content_job_cache.get(job_id)
                if cached is not None:
                    cached["status"] = "done"
                    cached["draft_id"] = int(job.draft_id) if getattr(job, "draft_id", None) else cached.get("draft_id")
        except Exception as exc:  # noqa: BLE001
            with self._session_factory() as session:
                job = session.get(ContentGenerationJob, job_id)
                if job:
                    job.status = "error"
                    job.error_message = str(exc)[:255]
                    session.commit()
            with self._content_job_lock:
                cached = self._content_job_cache.get(job_id)
                if cached is not None:
                    cached["status"] = "error"
                    cached["error_message"] = str(exc)[:255]

    def save_content_draft(self, *, kind: str, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        kind = (kind or "").strip().lower()
        if kind not in {"article", "video", "video_prompt"}:
            kind = "article"
        title = None
        if kind == "article":
            # Best-effort extract first markdown heading.
            m = re.search(r"^#\s+(.+)$", text.strip(), flags=re.MULTILINE)
            if m:
                title = m.group(1).strip()[:255]
        with self._session_factory() as session:
            row = ContentDraft(kind=kind, title=title, text=text, context=context)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_dict()

    def get_latest_content_drafts(self) -> dict[str, Any]:
        kinds = ["article", "video", "video_prompt"]
        result: dict[str, Any] = {}
        with self._session_factory() as session:
            for k in kinds:
                row = session.execute(
                    select(ContentDraft)
                    .where(ContentDraft.kind == k)
                    .order_by(ContentDraft.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                result[k] = row.to_dict() if row else None
        return result

    def list_content_drafts(self, *, kind: str | None, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        kind = (kind or "").strip().lower()
        if kind and kind not in {"article", "video", "video_prompt"}:
            kind = ""
        limit = max(1, min(int(limit or 20), 100))
        offset = max(0, int(offset or 0))
        with self._session_factory() as session:
            q = select(ContentDraft).order_by(ContentDraft.created_at.desc()).limit(limit).offset(offset)
            if kind:
                q = q.where(ContentDraft.kind == kind)
            rows = session.execute(q).scalars().all()
            draft_ids = [int(r.id) for r in rows if getattr(r, "id", None) is not None]
            jobs: list[ContentGenerationJob] = []
            if draft_ids:
                jobs = (
                    session.execute(
                        select(ContentGenerationJob)
                        .where(ContentGenerationJob.draft_id.in_(draft_ids))
                        .order_by(ContentGenerationJob.updated_at.desc())
                    )
                    .scalars()
                    .all()
                )
            job_by_draft: dict[int, ContentGenerationJob] = {}
            for j in jobs:
                if getattr(j, "draft_id", None) is None:
                    continue
                did = int(j.draft_id)
                # keep the latest job per draft
                if did not in job_by_draft:
                    job_by_draft[did] = j
        items: list[dict[str, Any]] = []
        for r in rows:
            d = r.to_dict()
            # Attach job info for "in-progress" drafts.
            j = job_by_draft.get(int(r.id))
            if j is not None:
                d["job_id"] = int(j.id)
                d["job_status"] = str(getattr(j, "status", "") or "")
                # If running and we still have in-memory cache, prefer cache text.
                if d.get("job_status") == "running":
                    with self._content_job_lock:
                        cached = dict(self._content_job_cache.get(int(j.id)) or {})
                    if cached and str(cached.get("text") or ""):
                        d["text"] = str(cached.get("text") or "")
            title = str(getattr(r, "title", None) or "").strip()
            if not title:
                ctx = r.context if isinstance(getattr(r, "context", None), dict) else {}
                # Prefer group/topic hints if present; otherwise dump minimal json.
                hint = ""
                if isinstance(ctx.get("hot_keywords"), list) and ctx.get("hot_keywords"):
                    hint = "热点：" + "、".join([str(x) for x in ctx.get("hot_keywords", [])[:2] if str(x).strip()])
                if not hint and isinstance(ctx.get("group_labels"), list) and ctx.get("group_labels"):
                    hint = "群体：" + "、".join([str(x) for x in ctx.get("group_labels", [])[:2] if str(x).strip()])
                if not hint and ctx:
                    hint = json.dumps(ctx, ensure_ascii=False)[:24]
                if not hint:
                    hint = (str(d.get("text") or "")[:24] or "（无标题）").replace("\n", " ").strip()
                title = hint
            created_at = getattr(r, "created_at", None)
            date_str = created_at.date().isoformat() if isinstance(created_at, datetime) else ""
            d["display_title"] = title
            d["display_date"] = date_str
            items.append(d)
        return items

    def build_talking_context(self, student_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            student = self._find_student(session, student_id)
            if student is None:
                return {
                    "gpa": None,
                    "warning_score": None,
                    "warning_status": None,
                    "behavior_tags": [],
                    "cognitive_tags": [],
                    "content_keywords": [],
                    "intervention_action": None,
                }

            profile = session.execute(
                select(Profile)
                .where(Profile.student_id == student.id)
                .order_by(Profile.period.desc(), Profile.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()

        if profile is None:
            return {
                "gpa": student.gpa,
                "warning_score": None,
                "warning_status": None,
                "behavior_tags": [],
                "cognitive_tags": [],
                "content_keywords": [],
                "intervention_action": None,
            }

        payload = self._build_profile(student, profile)
        behavior = payload.get("behavior_tags", []) if isinstance(payload.get("behavior_tags"), list) else []
        cognitive = payload.get("cognitive_tags", []) if isinstance(payload.get("cognitive_tags"), list) else []
        keywords = payload.get("content_keywords", []) if isinstance(payload.get("content_keywords"), list) else []

        # Privacy-safe context for external LLM call:
        # do NOT pass direct identifiers like student_no/name.
        return {
            "gpa": student.gpa,
            "warning_score": profile.warning_score,
            "warning_status": profile.warning_status,
            "behavior_tags": behavior,
            "cognitive_tags": cognitive,
            "content_keywords": keywords,
            "intervention_action": payload.get("intervention_action"),
        }

    def _collect_hot_topics(self, *, limit_rows: int = 240) -> list[dict[str, Any]]:
        topics_from_table = self._load_hot_topics_from_table(limit=12)
        if topics_from_table:
            return topics_from_table

        with self._session_factory() as session:
            rows = session.execute(
                select(
                    StudentTextData.source,
                    StudentTextData.content,
                    StudentTextData.created_at,
                )
                .order_by(StudentTextData.created_at.desc())
                .limit(limit_rows)
            ).all()

        source_map = {
            "weibo": "weibo",
            "douyin": "douyin",
            "xiaohongshu": "xiaohongshu",
        }
        by_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        latest_time: dict[str, datetime | None] = defaultdict(lambda: None)

        for source, content, created_at in rows:
            src = source_map.get(str(source or "").strip().lower(), "weibo")
            text = (content or "").strip()
            if not text:
                continue
            if latest_time[src] is None or (isinstance(created_at, datetime) and created_at > latest_time[src]):
                latest_time[src] = created_at if isinstance(created_at, datetime) else latest_time[src]
            for token in self._tokenize_content_for_wordcloud(text):
                by_source[src][token] += 1

        topics: list[dict[str, Any]] = []
        for src, counter in by_source.items():
            top_keywords = [w for w, _ in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:3]]
            if not top_keywords:
                continue
            ttl = " / ".join(top_keywords)
            topics.append(
                {
                    "id": f"{src}-hot",
                    "platform": src,
                    "title": ttl,
                    "heat_label": "中高",
                    "captured_at": self._to_iso(latest_time.get(src)) or datetime.now().isoformat(timespec="seconds"),
                }
            )
        return topics[:6]

    def _load_hot_topics_from_table(self, *, limit: int = 12) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(SocialHotTopic)
                .where(SocialHotTopic.status == "active")
                .order_by(
                    SocialHotTopic.is_verified.desc(),
                    SocialHotTopic.heat_score.desc().nullslast(),
                    SocialHotTopic.captured_at.desc().nullslast(),
                    SocialHotTopic.created_at.desc(),
                )
                .limit(limit)
            ).scalars().all()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "id": f"hot-{row.id}",
                    "platform": str(row.platform or "weibo"),
                    "title": str(row.title or "").strip(),
                    "heat_label": "高" if (row.heat_score or 0) >= 80 else ("中高" if (row.heat_score or 0) >= 50 else "中"),
                    "captured_at": self._to_iso(row.captured_at) or self._to_iso(row.created_at) or datetime.now().isoformat(timespec="seconds"),
                }
            )
        return [x for x in items if x["title"]][:6]

    def get_scatter_points(self, method: str = "numeric") -> list[dict[str, Any]]:
        latest_profiles = self._latest_profile_map()
        students = self._all_students()
        method = (method or "numeric").strip().lower()
        if method not in {"numeric", "text"}:
            method = "numeric"

        numeric_map = self._latest_numeric_map() if method == "numeric" else {}
        text_label_map = self._build_cluster_label_map(kind="text")
        numeric_label_map = self._build_cluster_label_map(kind="numeric")
        text_embedding_map: dict[int, np.ndarray] = {}
        text_embedding_dim = 0
        if method == "text":
            text_embedding_map, text_embedding_dim = self._build_text_embedding_map([s.id for s in students])

        feature_rows: list[list[float]] = []
        base_rows: list[dict[str, Any]] = []

        for student in students:
            profile = latest_profiles.get(student.id)
            warning_score = float(profile.warning_score or 0) if profile is not None else 0.0
            cluster_label = profile.numeric_cluster_id if profile is not None and profile.numeric_cluster_id is not None else -1
            text_cluster = profile.text_cluster_id if profile is not None and profile.text_cluster_id is not None else -1

            if method == "text":
                emb = text_embedding_map.get(student.id)
                if emb is not None:
                    vector = emb.tolist()
                else:
                    # Fallback when no raw text or model unavailable.
                    text_tags = profile.text_tags if profile is not None and isinstance(profile.text_tags, dict) else {}
                    topic_distribution = text_tags.get("topic_distribution")
                    top_counts = [0.0, 0.0, 0.0]
                    if isinstance(topic_distribution, list):
                        for idx, item in enumerate(topic_distribution[:3]):
                            if isinstance(item, dict):
                                top_counts[idx] = float(item.get("count") or 0.0)
                    text_count = float(text_tags.get("text_count") or 0.0) if isinstance(text_tags, dict) else 0.0
                    keyword_count = float(len(text_tags.get("keywords", []))) if isinstance(text_tags.get("keywords"), list) else 0.0
                    vector = [float(text_cluster), warning_score, text_count, keyword_count, *top_counts]
                    if text_embedding_dim > 0:
                        # Align vector length with embedding vectors for PCA input matrix.
                        vector = vector + [0.0] * max(0, text_embedding_dim - len(vector))
                group_meta = text_label_map.get(profile.text_cluster_id if profile is not None else None, {})
                group_name = (
                    str(group_meta.get("label_display"))
                    if group_meta.get("label_display")
                    else (f"主题{text_cluster}" if text_cluster != -1 else "离群主题")
                )
            else:
                numeric = numeric_map.get(student.id)
                vector = [
                    float(numeric.library_visits) if numeric is not None else 0.0,
                    float(numeric.signin_count) if numeric is not None else 0.0,
                    float(numeric.course_submit_count) if numeric is not None else 0.0,
                    float(numeric.online_duration_min) if numeric is not None else 0.0,
                    float(numeric.avg_score or 0.0) if numeric is not None else 0.0,
                    float(numeric.correct_rate or 0.0) if numeric is not None else 0.0,
                    float(student.gpa or 0.0),
                    warning_score,
                ]
                group_meta = numeric_label_map.get(profile.numeric_cluster_id if profile is not None else None, {})
                group_name = (
                    str(group_meta.get("label_display"))
                    if group_meta.get("label_display")
                    else (f"群组 {profile.numeric_cluster_id}" if profile is not None and profile.numeric_cluster_id is not None else "未聚类")
                )

            feature_rows.append(vector)
            base_rows.append(
                {
                    "student_id": student.student_no,
                    "group": group_name,
                    "cluster_label": profile.numeric_cluster_id if profile is not None else None,
                    "warning_score": round(warning_score, 2),
                }
            )

        coords = self._pca_2d(feature_rows)
        points: list[dict[str, Any]] = []
        for row, coord in zip(base_rows, coords):
            jx, jy = self._stable_jitter(str(row["student_id"]))
            points.append(
                {
                    **row,
                    "x": round(float(coord[0]) + jx, 3),
                    "y": round(float(coord[1]) + jy, 3),
                }
            )

        if not points:
            return self._demo_scatter_points()
        return points

    @staticmethod
    def _find_student(session: Session, student_id: str) -> Student | None:
        student = None
        if student_id.isdigit():
            student = session.get(Student, int(student_id))
        if student is not None:
            return student
        return session.execute(select(Student).where(Student.student_no == student_id).limit(1)).scalar_one_or_none()

    @staticmethod
    def _extract_tags(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(x) for x in value if x is not None]
        if isinstance(value, dict):
            if isinstance(value.get("tags"), list):
                return [str(x) for x in value.get("tags", []) if x is not None]
            if isinstance(value.get("top_keywords"), list):
                return [str(x) for x in value.get("top_keywords", []) if x is not None]
            return [str(k) for k, v in value.items() if v]
        return []

    @staticmethod
    def _extract_behavior_tags_from_numeric_tags(value: Any) -> list[str]:
        if not isinstance(value, dict):
            return []

        feature_display_map = {
            "avg_score": "成绩",
            "gpa": "绩点",
            "correct_rate": "正确率",
            "signin_count": "签到",
            "course_submit_count": "提交次数",
            "online_duration_min": "在线时长",
            "library_visits": "图书馆访问",
        }

        tags: list[str] = []
        drivers = value.get("drivers")
        if isinstance(drivers, list):
            for x in drivers:
                raw = str(x).strip()
                if not raw:
                    continue
                tags.append(feature_display_map.get(raw, raw))

        label_display = value.get("label_display")
        if isinstance(label_display, str) and label_display.strip():
            tags.append(label_display.strip())

        # Backward compatibility for older payloads with top_keywords/tags.
        if isinstance(value.get("top_keywords"), list):
            tags.extend([str(x).strip() for x in value.get("top_keywords", []) if str(x).strip()])
        if isinstance(value.get("tags"), list):
            tags.extend([str(x).strip() for x in value.get("tags", []) if str(x).strip()])

        # De-duplicate while preserving order.
        dedup: list[str] = []
        seen: set[str] = set()
        for t in tags:
            if t not in seen:
                seen.add(t)
                dedup.append(t)
        return dedup[:8]

    @staticmethod
    def _extract_text_tags_from_text_tags(value: Any) -> list[str]:
        if not isinstance(value, dict):
            return []

        tags: list[str] = []
        label_display = value.get("label_display")
        if isinstance(label_display, str) and label_display.strip():
            tags.append(label_display.strip())

        keywords = value.get("keywords")
        if isinstance(keywords, list):
            tags.extend([str(x).strip() for x in keywords if str(x).strip()])

        topic_distribution = value.get("topic_distribution")
        if isinstance(topic_distribution, list):
            for item in topic_distribution[:3]:
                if isinstance(item, dict):
                    label = item.get("label_display")
                    if isinstance(label, str) and label.strip():
                        tags.append(label.strip())

        dedup: list[str] = []
        seen: set[str] = set()
        for t in tags:
            if t not in seen:
                seen.add(t)
                dedup.append(t)
        return dedup[:10]

    def _load_student_content_keywords(self, student_ids: list[int], *, limit_per_student: int = 30) -> dict[int, list[str]]:
        if not student_ids:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    StudentTextData.student_id,
                    StudentTextData.content,
                    StudentTextData.created_at,
                )
                .where(StudentTextData.student_id.in_(student_ids))
                .order_by(StudentTextData.student_id.asc(), StudentTextData.created_at.desc())
            ).all()

        grouped: dict[int, list[str]] = defaultdict(list)
        for student_id, content, _created_at in rows:
            if len(grouped[int(student_id)]) >= limit_per_student:
                continue
            text = (content or "").strip()
            if text:
                grouped[int(student_id)].append(text)

        result: dict[int, list[str]] = {}
        for student_id, texts in grouped.items():
            counter: dict[str, int] = defaultdict(int)
            for text in texts:
                for token in self._tokenize_content_for_wordcloud(text):
                    counter[token] += 1
            keywords = [w for w, _ in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:20]]
            result[student_id] = keywords
        return result

    def _tokenize_content_for_wordcloud(self, text: str) -> list[str]:
        stopwords = self._get_wordcloud_stopwords()
        cleaned = re.sub(r"https?://\S+|www\.\S+", " ", text or "")
        cleaned = re.sub(r"@[\w\u4e00-\u9fa5_-]+", " ", cleaned)
        cleaned = re.sub(r"#([^#]+)#", r"\1", cleaned)
        cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        tokens: list[str] = []
        for token in jieba.lcut(cleaned):
            t = token.strip()
            if not t:
                continue
            if t in stopwords:
                continue
            if re.fullmatch(r"[\W_]+", t, flags=re.UNICODE):
                continue
            if re.fullmatch(r"\d+(\.\d+)?", t):
                continue
            if len(t) <= 1 and re.fullmatch(r"[\u4e00-\u9fff]", t):
                continue
            tokens.append(t)
        return tokens

    def _get_wordcloud_stopwords(self) -> set[str]:
        path = Path.cwd() / "backend" / "data" / "hit_stopwords.txt"
        if not path.exists():
            path = Path.cwd() / "data" / "hit_stopwords.txt"

        mtime: float | None = None
        try:
            mtime = path.stat().st_mtime if path.exists() else None
        except Exception:
            mtime = None

        # Reload if stopwords file changed on disk.
        if self._wordcloud_stopwords is not None and self._wordcloud_stopwords_mtime == mtime:
            return self._wordcloud_stopwords
        stopwords: set[str] = set()
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip()
                    if w:
                        stopwords.add(w)
        stopwords.update({"我们", "你们", "他们", "这个", "那个", "然后", "就是", "一个", "一些"})
        self._wordcloud_stopwords = stopwords
        self._wordcloud_stopwords_mtime = mtime
        return stopwords

    @staticmethod
    def _to_iso(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        return None

    def _build_profile(self, student: Student, profile: Profile) -> dict[str, Any]:
        numeric_tags = profile.numeric_tags if isinstance(profile.numeric_tags, dict) else {}
        text_tags = profile.text_tags if isinstance(profile.text_tags, dict) else {}
        feature_summary = profile.feature_summary if isinstance(profile.feature_summary, dict) else {}

        basic_tags: list[str] = []
        if student.grade:
            basic_tags.append(student.grade)
        if student.major:
            basic_tags.append(student.major)
        if student.gender:
            basic_tags.append(student.gender)

        # Only use human-readable labels, avoid leaking dict keys like "label_code/topic_distribution".
        behavior_tags = self._extract_behavior_tags_from_numeric_tags(numeric_tags)[:6]
        cognitive_tags = self._extract_text_tags_from_text_tags(text_tags)[:6]

        if isinstance(feature_summary.get("radar_scores"), dict):
            radar_scores = dict(feature_summary.get("radar_scores", {}))
        else:
            warning_score = float(profile.warning_score or 0)
            radar_scores = {
                "basic": warning_score,
                "learning": warning_score,
                "preference": warning_score,
                "stability": warning_score,
                "behavior": warning_score,
            }

        latest_time = self._to_iso(profile.updated_at) or self._to_iso(profile.created_at)
        content_keywords = self._load_student_content_keywords([student.id]).get(student.id, [])
        return {
            "student_id": student.student_no,
            "basic_tags": basic_tags,
            "behavior_tags": behavior_tags,
            "cognitive_tags": cognitive_tags,
            "radar_scores": radar_scores,
            "intervention_action": profile.warning_note,
            "warning_score": profile.warning_score,
            "warning_status": profile.warning_status,
            "warning_handler": profile.warning_handler,
            "warning_handled_at": self._to_iso(profile.warning_handled_at),
            "last_computed_at": latest_time,
            "activity_trend": [],
            "content_keywords": content_keywords[:30],
        }

    def _latest_profile_rows(self) -> list[tuple[Profile, Student]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(Profile, Student)
                .join(Student, Student.id == Profile.student_id)
                .order_by(Profile.student_id.asc(), Profile.period.desc(), Profile.updated_at.desc())
            ).all()

        latest_by_student: dict[int, tuple[Profile, Student]] = {}
        for profile, student in rows:
            if profile.student_id not in latest_by_student:
                latest_by_student[profile.student_id] = (profile, student)
        return list(latest_by_student.values())

    def _latest_profile_map(self) -> dict[int, Profile]:
        rows = self._latest_profile_rows()
        return {profile.student_id: profile for profile, _student in rows}

    def _all_students(self) -> list[Student]:
        with self._session_factory() as session:
            return session.execute(select(Student).order_by(Student.id.asc())).scalars().all()

    def _latest_numeric_map(self) -> dict[int, StudentNumericData]:
        with self._session_factory() as session:
            rows = session.execute(
                select(StudentNumericData)
                .order_by(StudentNumericData.student_id.asc(), StudentNumericData.period.desc(), StudentNumericData.updated_at.desc())
            ).scalars().all()
        latest: dict[int, StudentNumericData] = {}
        for row in rows:
            if row.student_id not in latest:
                latest[row.student_id] = row
        return latest

    def _build_text_embedding_map(self, student_ids: list[int]) -> tuple[dict[int, np.ndarray], int]:
        if not student_ids:
            return {}, 0
        model = self._get_text_embedding_model()
        if model is None:
            return {}, 0

        cache_key = self._text_embedding_cache_key(student_ids)
        cached = self._text_embedding_cache.get(cache_key)
        if cached is not None:
            return cached

        student_texts = self._load_student_text_documents(student_ids)
        if not student_texts:
            result = ({}, int(getattr(model, "get_sentence_embedding_dimension", lambda: 0)()))
            self._text_embedding_cache[cache_key] = result
            return result

        ordered_ids = list(student_texts.keys())
        docs = [student_texts[sid] for sid in ordered_ids]
        embeddings = model.encode(docs, show_progress_bar=False, normalize_embeddings=True)
        arr = np.array(embeddings, dtype=float)
        if arr.ndim != 2 or arr.shape[0] == 0:
            result = ({}, 0)
            self._text_embedding_cache[cache_key] = result
            return result
        emb_map = {sid: arr[idx] for idx, sid in enumerate(ordered_ids)}
        result = (emb_map, int(arr.shape[1]))
        self._text_embedding_cache[cache_key] = result
        return result

    def _load_student_text_documents(self, student_ids: list[int]) -> dict[int, str]:
        with self._session_factory() as session:
            rows = session.execute(
                select(StudentTextData)
                .where(StudentTextData.student_id.in_(student_ids))
                .order_by(StudentTextData.student_id.asc(), StudentTextData.created_at.desc())
            ).scalars().all()

        by_student: dict[int, list[str]] = defaultdict(list)
        for row in rows:
            text = (row.content or "").strip()
            if not text:
                continue
            if len(by_student[row.student_id]) >= 10:
                continue
            by_student[row.student_id].append(text[:300])

        return {sid: "\n".join(parts) for sid, parts in by_student.items() if parts}

    def _text_embedding_cache_key(self, student_ids: list[int]) -> tuple:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    StudentTextData.student_id,
                    func.max(StudentTextData.created_at),
                    func.count(StudentTextData.text_id),
                    func.sum(func.length(StudentTextData.content)),
                )
                .where(StudentTextData.student_id.in_(student_ids))
                .group_by(StudentTextData.student_id)
                .order_by(StudentTextData.student_id.asc())
            ).all()
        # Include summed content length to invalidate cache on content edits,
        # even if created_at/count stays unchanged.
        normalized = tuple(
            (int(sid), str(ts) if ts is not None else "", int(cnt), int(total_len or 0))
            for sid, ts, cnt, total_len in rows
        )
        return ("bge-base-zh-v1.5", normalized)

    def _get_text_embedding_model(self):
        if self._text_embedding_model is not None:
            return self._text_embedding_model
        try:
            from sentence_transformers import SentenceTransformer

            self._text_embedding_model = SentenceTransformer("BAAI/bge-base-zh-v1.5")
        except Exception:
            self._text_embedding_model = None
        return self._text_embedding_model

    def _build_cluster_label_map(self, kind: str) -> dict[int | None, dict[str, str]]:
        rows = self._latest_profile_rows()
        bag: dict[int | None, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for profile, _student in rows:
            if kind == "text":
                cluster_id = profile.text_cluster_id
                tags = profile.text_tags if isinstance(profile.text_tags, dict) else {}
            else:
                cluster_id = profile.numeric_cluster_id
                tags = profile.numeric_tags if isinstance(profile.numeric_tags, dict) else {}

            label_display = tags.get("label_display")
            label_code = tags.get("label_code")
            if isinstance(label_display, str) and label_display.strip():
                bag[cluster_id][f"display::{label_display.strip()}"] += 1
            if isinstance(label_code, str) and label_code.strip():
                bag[cluster_id][f"code::{label_code.strip()}"] += 1

            # Fallback to feature_summary when tags are absent in old rows.
            summary = profile.feature_summary if isinstance(profile.feature_summary, dict) else {}
            if kind == "text":
                text_summary = summary.get("text_clustering") if isinstance(summary.get("text_clustering"), dict) else {}
                topic_label = text_summary.get("topic_label")
                if isinstance(topic_label, str) and topic_label.strip():
                    bag[cluster_id][f"display::{topic_label.strip()}"] += 1
            else:
                numeric_summary = summary.get("numeric_clustering") if isinstance(summary.get("numeric_clustering"), dict) else {}
                cluster_label = numeric_summary.get("cluster_label")
                if isinstance(cluster_label, str) and cluster_label.strip():
                    bag[cluster_id][f"display::{cluster_label.strip()}"] += 1

        result: dict[int | None, dict[str, str]] = {}
        for cluster_id, counter in bag.items():
            label_display = None
            label_code = None
            display_candidates = [(k.replace("display::", "", 1), v) for k, v in counter.items() if k.startswith("display::")]
            code_candidates = [(k.replace("code::", "", 1), v) for k, v in counter.items() if k.startswith("code::")]
            if display_candidates:
                label_display = sorted(display_candidates, key=lambda x: (-x[1], x[0]))[0][0]
            if code_candidates:
                label_code = sorted(code_candidates, key=lambda x: (-x[1], x[0]))[0][0]
            result[cluster_id] = {
                "label_display": label_display or "",
                "label_code": label_code or "",
            }
        return result

    @staticmethod
    def _risk_level_from_score(score: float) -> str:
        if score >= 70:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    @staticmethod
    def _stable_jitter(student_no: str) -> tuple[float, float]:
        # Separate overlapping points while keeping deterministic rendering.
        raw = sum((idx + 1) * ord(ch) for idx, ch in enumerate(student_no))
        x = ((raw % 29) - 14) / 100.0
        y = (((raw // 29) % 29) - 14) / 100.0
        return x, y

    @staticmethod
    def _pca_2d(vectors: list[list[float]]) -> list[tuple[float, float]]:
        if not vectors:
            return []
        x = np.array(vectors, dtype=float)
        if x.ndim != 2:
            return [(0.0, 0.0) for _ in vectors]
        if x.shape[0] == 1:
            return [(0.0, 0.0)]

        means = x.mean(axis=0)
        stds = x.std(axis=0)
        stds = np.where(stds == 0, 1.0, stds)
        x_norm = (x - means) / stds

        cov = np.cov(x_norm, rowvar=False)
        if np.ndim(cov) == 0:
            return [(0.0, 0.0) for _ in vectors]

        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        eigvecs = eigvecs[:, order]
        components = eigvecs[:, :2] if eigvecs.shape[1] >= 2 else eigvecs[:, :1]
        projected = x_norm @ components

        if projected.shape[1] == 1:
            projected = np.hstack([projected, np.zeros((projected.shape[0], 1))])
        return [(float(row[0]), float(row[1])) for row in projected]

    @staticmethod
    def _demo_groups() -> list[dict[str, Any]]:
        # Keep group-analysis page usable before clustering data is generated.
        return [
            {
                "name": "学业投入群",
                "size": 42,
                "topStudent": "STU_001",
                "cluster_label": 0,
                "representative_behavior_tags": ["图书馆高频", "作息规律", "课程提交稳定"],
            },
            {
                "name": "夜间活跃群",
                "size": 31,
                "topStudent": "STU_002",
                "cluster_label": 1,
                "representative_behavior_tags": ["夜间在线", "短视频高频", "碎片化学习"],
            },
            {
                "name": "待观察群",
                "size": 19,
                "topStudent": "STU_003",
                "cluster_label": 2,
                "representative_behavior_tags": ["活跃下降", "课程波动", "情绪词增加"],
            },
        ]

    @staticmethod
    def _demo_scatter_points() -> list[dict[str, Any]]:
        return [
            {"student_id": "STU_001", "group": "群组 0", "cluster_label": 0, "x": -2.1, "y": 0.8, "warning_score": 35.0},
            {"student_id": "STU_002", "group": "群组 0", "cluster_label": 0, "x": -1.5, "y": 1.1, "warning_score": 41.0},
            {"student_id": "STU_003", "group": "群组 1", "cluster_label": 1, "x": 0.3, "y": 1.7, "warning_score": 58.0},
            {"student_id": "STU_004", "group": "群组 1", "cluster_label": 1, "x": 0.9, "y": 2.0, "warning_score": 66.0},
            {"student_id": "STU_005", "group": "群组 2", "cluster_label": 2, "x": 2.1, "y": 2.8, "warning_score": 79.0},
            {"student_id": "STU_006", "group": "群组 2", "cluster_label": 2, "x": 2.7, "y": 3.0, "warning_score": 84.0},
        ]
