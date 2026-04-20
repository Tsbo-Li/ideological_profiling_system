from __future__ import annotations

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.models import Base


def main() -> None:
    cfg = DatabaseConfig.from_env()
    engine, _SessionLocal = init_engine_and_session(cfg.database_url)
    Base.metadata.create_all(bind=engine)
    print("db initialized (create_all done)")


if __name__ == "__main__":
    main()

