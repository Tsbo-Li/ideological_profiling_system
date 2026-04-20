from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Prefer DATABASE_URL; otherwise compose from parts.
    Example:
      postgresql+psycopg2://user:pass@localhost:5432/ideological_profiling_sys
    """

    database_url: str

    @staticmethod
    def from_env() -> "DatabaseConfig":
        url = os.getenv("DATABASE_URL", "").strip()
        if url:
            return DatabaseConfig(database_url=url)

        host = os.getenv("DB_HOST", "127.0.0.1")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "ideological_profiling_sys")
        user = os.getenv("DB_USER", "xiaozhuyizi")
        password = os.getenv("DB_PASSWORD", "123456")
        driver = os.getenv("DB_DRIVER", "postgresql+psycopg2")
        url = f"{driver}://{user}:{password}@{host}:{port}/{name}"
        return DatabaseConfig(database_url=url)

    def database_url_masked(self) -> str:
        # Best-effort masking, avoids leaking passwords in /api/config
        url = self.database_url
        if "://" not in url or "@" not in url:
            return url
        scheme, rest = url.split("://", 1)
        creds, tail = rest.split("@", 1)
        if ":" in creds:
            user, _pw = creds.split(":", 1)
            return f"{scheme}://{user}:***@{tail}"
        return f"{scheme}://***@{tail}"

