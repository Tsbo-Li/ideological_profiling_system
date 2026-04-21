from __future__ import annotations

import argparse
import json
import ssl
import time
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import select

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.models import Base, SocialHotTopic


def _request_json(url: str, *, timeout: int = 20, retries: int = 3) -> Any:
    req = Request(
        url,
        headers={
            "User-Agent": "ideological-profiling-system/1.0",
            "Accept": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT  # type: ignore[attr-defined]

    last_err: Exception | None = None
    for i in range(retries):
        try:
            with urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            last_err = exc
            # 4xx does not benefit much from retries.
            if 400 <= exc.code < 500:
                break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        if i < retries - 1:
            time.sleep(0.6 * (i + 1))
    raise RuntimeError(f"request failed url={url} err={last_err}")


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("list") or payload.get("items")
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    return []


def fetch_dailyhot() -> dict[str, Any]:
    base_urls = [
        "https://dailyhot-five-opal.vercel.app",
    ]
    routes = {
        "bilibili": "bilibili",
        "douyin": "douyin",
    }

    merged: dict[str, Any] = {"data": []}
    for platform, route_candidates in routes.items():
        got_platform = False
        for base_url in base_urls:
            for route in [x.strip() for x in route_candidates.split(",") if x.strip()]:
                url = f"{base_url.rstrip('/')}/{route}"
                try:
                    payload = _request_json(url)
                    rows = _extract_rows(payload)
                    if not rows:
                        continue
                    for row in rows:
                        item = dict(row)
                        item["platform"] = platform
                        merged["data"].append(item)
                    got_platform = True
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] fetch {platform} failed ({url}): {exc}")
                    continue
            if got_platform:
                break

    if not merged["data"]:
        raise RuntimeError("DailyHotApi returned no data")
    return merged


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def normalize_topics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for row in payload.get("data", []):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("name") or row.get("word") or "").strip()
        if not title:
            continue
        platform = str(row.get("platform") or "bilibili").strip().lower()
        if platform not in {"bilibili", "douyin"}:
            continue

        score_raw = row.get("hot") or row.get("heat") or row.get("score") or row.get("index")
        try:
            heat_score = float(score_raw) if score_raw is not None else None
        except Exception:
            heat_score = None

        topic_key = f"{platform}:{sha1(title.encode('utf-8')).hexdigest()[:16]}"
        items.append(
            {
                "topic_key": topic_key,
                "title": title[:255],
                "summary": str(row.get("desc") or row.get("summary") or "").strip() or None,
                "platform": platform,
                "source_url": str(row.get("url") or row.get("link") or "").strip() or None,
                "heat_score": heat_score,
                "keywords": [
                    str(x).strip()
                    for x in [
                        row.get("author"),
                        row.get("id"),
                    ]
                    if str(x).strip()
                ]
                or None,
                "event_time": now,
                "captured_at": _to_datetime(row.get("updated_at") or row.get("updateTime")) or now,
            }
        )

    dedup: dict[str, dict[str, Any]] = {}
    for item in items:
        dedup[item["topic_key"]] = item
    return list(dedup.values())


def save_topics(topics: list[dict[str, Any]]) -> int:
    cfg = DatabaseConfig.from_env()
    engine, SessionLocal = init_engine_and_session(cfg.database_url)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        for item in topics:
            existing = session.execute(
                select(SocialHotTopic).where(SocialHotTopic.topic_key == item["topic_key"]).limit(1)
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    SocialHotTopic(
                        topic_key=item["topic_key"],
                        title=item["title"],
                        summary=item["summary"],
                        platform=item["platform"],
                        source_url=item["source_url"],
                        heat_score=item["heat_score"],
                        keywords=item["keywords"],
                        event_time=item["event_time"],
                        captured_at=item["captured_at"],
                        status="active",
                        is_verified=False,
                    )
                )
            else:
                existing.title = item["title"]
                existing.summary = item["summary"]
                existing.platform = item["platform"]
                existing.source_url = item["source_url"]
                existing.heat_score = item["heat_score"]
                existing.event_time = item["event_time"]
                existing.captured_at = item["captured_at"]
                if existing.status != "blocked":
                    existing.status = "active"
        session.commit()
    return len(topics)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch social hot topics from DailyHotApi")
    parser.add_argument("--dry-run", action="store_true", help="only print parsed topics")
    args = parser.parse_args()

    payload = fetch_dailyhot()
    topics = normalize_topics(payload)
    if not topics:
        raise RuntimeError("no topics parsed")

    if args.dry_run:
        print(json.dumps(topics[:20], ensure_ascii=False, indent=2, default=str))
        print(f"dry-run parsed topics: {len(topics)}")
        return

    n = save_topics(topics)
    print(f"upserted social_hot_topics: {n}")


if __name__ == "__main__":
    main()