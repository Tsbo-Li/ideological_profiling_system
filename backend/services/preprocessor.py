from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any


@dataclass
class PreprocessResult:
    text: str


class Preprocessor:
    DEFAULT_NUMERIC_FEATURE_FIELDS = (
        "library_visits",
        "signin_count",
        "course_submit_count",
        "online_duration_min",
        "avg_score",
        "correct_rate",
        "gpa",
    )
    # Central mapping table for numeric feature normalization rules.
    # You can modify parser/default/min/max here without touching code logic.
    NUMERIC_FEATURE_RULES: dict[str, dict[str, Any]] = {
        "library_visits": {"parser": "int", "default": 0, "min": 0},
        "signin_count": {"parser": "int", "default": 0, "min": 0},
        "course_submit_count": {"parser": "int", "default": 0, "min": 0},
        "online_duration_min": {"parser": "float", "default": 0.0, "min": 0.0},
        "avg_score": {"parser": "float", "default": None, "min": 0.0, "max": 100.0},
        "correct_rate": {"parser": "float", "default": None, "min": 0.0, "max": 1.0},
        "gpa": {"parser": "float", "default": None, "min": 0.0, "max": 5.0},
    }
    SUPPORTED_NORMALIZATIONS = {"none", "minmax", "zscore"}
    
    DEFAULT_TEXT_FIELDS = ("content",)
    TEXT_FIELD_RULES: dict[str, dict[str, Any]] = {
        "content": {
            "strip_zero_width": True,
            "collapse_whitespace": True,
            "remove_urls": True,
            "remove_mentions": True,
            "remove_topics": False,
            "lowercase_english": False,
        }
    }

    def normalize_text(self, text: str) -> PreprocessResult:
        text = (text or "").strip()
        # Collapse repeated whitespace and remove simple zero-width chars.
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return PreprocessResult(text=text)

    def _sanitize_text_by_rule(self, field: str, raw_value: Any) -> str:
        text = str(raw_value or "")
        rule = self.TEXT_FIELD_RULES.get(field, {})

        if rule.get("strip_zero_width", True):
            text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        if rule.get("remove_urls", False):
            text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        if rule.get("remove_mentions", False):
            text = re.sub(r"@[\w\u4e00-\u9fa5_-]+", " ", text)
        if rule.get("remove_topics", False):
            text = re.sub(r"#([^#]+)#", r"\1", text)
        if rule.get("collapse_whitespace", True):
            text = re.sub(r"\s+", " ", text)
        text = text.strip()
        if rule.get("lowercase_english", False):
            text = text.lower()
        return text

    def _clip(self, value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    def _parse_int_or_default(self, value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _parse_float_or_default(self, value: Any, default: float | None = None) -> float | None:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _sanitize_numeric_feature_value(self, field: str, raw_value: Any) -> int | float | None:
        rule = self.NUMERIC_FEATURE_RULES.get(field)
        if not rule:
            return self._parse_float_or_default(raw_value, None)

        parser = rule.get("parser", "float")
        default = rule.get("default", None)
        min_value = rule.get("min", None)
        max_value = rule.get("max", None)

        if parser == "int":
            value: int | float | None = self._parse_int_or_default(raw_value, default if default is not None else 0)
        else:
            value = self._parse_float_or_default(raw_value, default)

        if value is None:
            return None
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    def _normalize_feature_batch(
        self,
        payloads: list[dict[str, Any]],
        normalization: str = "none",
    ) -> list[dict[str, Any]]:
        if normalization == "none" or not payloads:
            return payloads
        if normalization not in self.SUPPORTED_NORMALIZATIONS:
            raise ValueError(f"unsupported normalization: {normalization}")

        # Collect values by feature key.
        feature_values: dict[str, list[float]] = {}
        for payload in payloads:
            for key, value in payload["features"].items():
                if value is None:
                    continue
                feature_values.setdefault(key, []).append(float(value))

        if normalization == "minmax":
            stats: dict[str, tuple[float, float]] = {}
            for key, values in feature_values.items():
                stats[key] = (min(values), max(values))
            for payload in payloads:
                for key, value in payload["features"].items():
                    if value is None or key not in stats:
                        continue
                    min_v, max_v = stats[key]
                    if max_v == min_v:
                        payload["features"][key] = 0.0
                    else:
                        payload["features"][key] = (float(value) - min_v) / (max_v - min_v)
            return payloads

        # z-score normalization
        stats_z: dict[str, tuple[float, float]] = {}
        for key, values in feature_values.items():
            mean_v = sum(values) / len(values)
            var_v = sum((v - mean_v) ** 2 for v in values) / len(values)
            std_v = math.sqrt(var_v)
            stats_z[key] = (mean_v, std_v)

        for payload in payloads:
            for key, value in payload["features"].items():
                if value is None or key not in stats_z:
                    continue
                mean_v, std_v = stats_z[key]
                if std_v == 0:
                    payload["features"][key] = 0.0
                else:
                    payload["features"][key] = (float(value) - mean_v) / std_v
        return payloads

    def build_numeric_payload(
        self,
        row: dict[str, Any],
        numeric_feature_fields: list[str] | None = None,
        include_only_existing_fields: bool = True,
    ) -> dict[str, Any]:
        fields = numeric_feature_fields or list(self.DEFAULT_NUMERIC_FEATURE_FIELDS)
        features: dict[str, Any] = {}
        for field in fields:
            if include_only_existing_fields and field not in row:
                continue
            features[field] = self._sanitize_numeric_feature_value(field, row.get(field))

        return {
            "student_id": int(row["student_id"]),
            "period": str(row["period"]),  # YYYY-MM
            "features": features,
        }

    def build_numeric_payloads(
        self,
        rows: list[dict[str, Any]],
        drop_if_all_none: bool = False,
        numeric_feature_fields: list[str] | None = None,
        include_only_existing_fields: bool = True,
        normalization: str = "none",
    ) -> list[dict[str, Any]]:
        payloads = [
            self.build_numeric_payload(
                row,
                numeric_feature_fields=numeric_feature_fields,
                include_only_existing_fields=include_only_existing_fields,
            )
            for row in rows
        ]
        if not drop_if_all_none:
            return self._normalize_feature_batch(payloads, normalization=normalization)
        result: list[dict[str, Any]] = []
        for payload in payloads:
            features = payload["features"]
            if any(value is not None for value in features.values()):
                result.append(payload)
        return self._normalize_feature_batch(result, normalization=normalization)

    def build_text_payload(
        self,
        row: dict[str, Any],
        text_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        event_time = row.get("event_time")
        if isinstance(event_time, datetime):
            event_time = event_time.isoformat()

        fields = text_fields or list(self.DEFAULT_TEXT_FIELDS)
        content = ""
        if "content" in fields:
            content = self._sanitize_text_by_rule("content", row.get("content"))

        return {
            "textid": int(row["textid"]),
            "student_id": int(row["student_id"]),
            "period": str(row.get("period") or ""),
            "source": str(row.get("source") or ""),
            "text_type": str(row.get("text_type") or ""),
            "content": content,
            "event_time": event_time,  # str | None
        }

    def build_text_payloads(
        self,
        rows: list[dict[str, Any]],
        min_content_len: int = 5,
        deduplicate_by_content: bool = True,
        text_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payloads = [self.build_text_payload(row, text_fields=text_fields) for row in rows]
        payloads = [payload for payload in payloads if len(payload["content"]) >= min_content_len]

        if not deduplicate_by_content:
            return payloads

        seen: set[tuple[int, str]] = set()
        deduped: list[dict[str, Any]] = []
        for payload in payloads:
            key = (payload["student_id"], payload["content"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(payload)
        return deduped


def test_preprocessor_with_db(limit: int = 5, normalization: str = "none") -> None:
    """
    Read real records from DB and print preprocessing samples.
    Usage:
      python -m services.preprocessor
      python -c "from services.preprocessor import test_preprocessor_with_db; test_preprocessor_with_db(limit=10, normalization='minmax')"
    """
    from sqlalchemy import select

    from configs.database_cfg import DatabaseConfig
    from database.db import init_engine_and_session
    from database.models import Student, StudentNumericData, StudentTextData

    cfg = DatabaseConfig.from_env()
    _engine, SessionLocal = init_engine_and_session(cfg.database_url)

    preprocessor = Preprocessor()
    session = SessionLocal()
    try:
        numeric_rows_db = session.execute(select(StudentNumericData).limit(limit)).scalars().all()
        text_rows_db = session.execute(select(StudentTextData).limit(limit)).scalars().all()

        numeric_rows: list[dict[str, Any]] = []
        for item in numeric_rows_db:
            numeric_rows.append(
                {
                    "student_id": item.student_id,
                    "period": item.period,
                    "library_visits": item.library_visits,
                    "signin_count": item.signin_count,
                    "course_submit_count": item.course_submit_count,
                    "online_duration_min": item.online_duration_min,
                    "avg_score": item.avg_score,
                    "correct_rate": item.correct_rate,
                    # gpa sits in students table; fetch through relationship fallback query.
                    "gpa": item.student.gpa if item.student is not None else None,
                }
            )

        text_rows: list[dict[str, Any]] = []
        for item in text_rows_db:
            text_rows.append(
                {
                    "textid": item.textid,
                    "student_id": item.student_id,
                    "period": item.period,
                    "source": item.source,
                    "text_type": item.text_type,
                    "content": item.content,
                    "event_time": item.event_time,
                }
            )

        numeric_payloads = preprocessor.build_numeric_payloads(
            numeric_rows,
            normalization=normalization,
            include_only_existing_fields=True,
        )
        text_payloads = preprocessor.build_text_payloads(
            text_rows,
            min_content_len=5,
            deduplicate_by_content=True,
        )

        print("=== Preprocessor DB Test ===")
        print(f"numeric_input_rows={len(numeric_rows)} numeric_payload_rows={len(numeric_payloads)}")
        print(f"text_input_rows={len(text_rows)} text_payload_rows={len(text_payloads)}")
        if numeric_payloads:
            print(f"numeric_sample={numeric_payloads[0]}")
        if text_payloads:
            print(f"text_sample={text_payloads[0]}")
    finally:
        session.close()


if __name__ == "__main__":
    test_preprocessor_with_db()

