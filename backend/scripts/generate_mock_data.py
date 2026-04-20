from __future__ import annotations

import random
from datetime import datetime, timedelta

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.models import Student, StudentNumericData, StudentTextData
from sqlalchemy.orm import Session


def _period_now() -> str:
    return datetime.now().strftime("%Y-%m")


def main() -> None:
    cfg = DatabaseConfig.from_env()
    _engine, SessionLocal = init_engine_and_session(cfg.database_url)

    majors = ["计算机", "软件工程", "电子信息", "数学", "新闻传播", "政治学"]
    period = _period_now()
    text_sources = ["crawler", "platform", "questionnaire", "interview"]
    text_types = ["post", "comment", "topic", "qa"]

    session: Session = SessionLocal()
    try:
        for i in range(20):
            student = Student(
                student_no=f"2026{i:04d}",
                name=f"学生{i}",
                gender=random.choice(["男", "女"]),
                age=random.randint(18, 24),
                grade=random.choice(["大一", "大二", "大三", "大四"]),
                major=random.choice(majors),
                gpa=round(random.uniform(2.0, 4.0), 2),
            )
            session.add(student)
            session.flush()

            numeric = StudentNumericData(
                student_id=student.id,
                period=period,
                library_visits=random.randint(0, 40),
                signin_count=random.randint(0, 30),
                course_submit_count=random.randint(0, 80),
                online_duration_min=round(random.uniform(60, 2400), 1),
                avg_score=round(random.uniform(55, 98), 2),
                correct_rate=round(random.uniform(0.45, 0.98), 3),
            )
            session.add(numeric)

            for _ in range(random.randint(2, 5)):
                event_time = datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
                text = StudentTextData(
                    student_id=student.id,
                    period=period,
                    source=random.choice(text_sources),
                    text_type=random.choice(text_types),
                    content=random.choice(
                        [
                            "最近关注了很多时政与社会热点讨论。",
                            "更喜欢短视频平台上的学习类内容。",
                            "参与了课程论坛答疑，表达了不同观点。",
                            "在问卷中提到对就业与考研压力较大。",
                        ]
                    ),
                    event_time=event_time,
                )
                session.add(text)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("mock data generated")


if __name__ == "__main__":
    main()

