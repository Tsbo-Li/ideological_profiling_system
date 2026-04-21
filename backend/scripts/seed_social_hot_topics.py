from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.models import Base, SocialHotTopic


def main() -> None:
    cfg = DatabaseConfig.from_env()
    engine, SessionLocal = init_engine_and_session(cfg.database_url)
    Base.metadata.create_all(bind=engine)

    samples = [
        {
            "topic_key": "campus-job-hunt-anxiety",
            "title": "春招焦虑与就业节奏调整",
            "summary": "围绕春招压力与求职节奏管理的讨论持续升温。",
            "platform": "weibo",
            "source_url": "",
            "heat_score": 82.0,
            "keywords": ["春招", "就业", "焦虑", "节奏"],
        },
        {
            "topic_key": "night-activity-sleep-balance",
            "title": "夜间活跃与作息平衡",
            "summary": "夜间在线行为与第二天学习状态的关系成为高频话题。",
            "platform": "douyin",
            "source_url": "",
            "heat_score": 67.0,
            "keywords": ["夜间活跃", "作息", "效率"],
        },
    ]

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        for item in samples:
            existing = session.execute(
                select(SocialHotTopic).where(SocialHotTopic.topic_key == item["topic_key"]).limit(1)
            ).scalar_one_or_none()
            if existing:
                existing.title = item["title"]
                existing.summary = item["summary"]
                existing.platform = item["platform"]
                existing.source_url = item["source_url"]
                existing.heat_score = item["heat_score"]
                existing.keywords = item["keywords"]
                existing.captured_at = now
                existing.status = "active"
                existing.is_verified = True
            else:
                session.add(
                    SocialHotTopic(
                        topic_key=item["topic_key"],
                        title=item["title"],
                        summary=item["summary"],
                        platform=item["platform"],
                        source_url=item["source_url"],
                        heat_score=item["heat_score"],
                        keywords=item["keywords"],
                        captured_at=now,
                        status="active",
                        is_verified=True,
                    )
                )
        session.commit()
    print("seeded social_hot_topics")


if __name__ == "__main__":
    main()

