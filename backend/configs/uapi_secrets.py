from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UapiSecrets:
    """
    Secrets for the 'uapi' provider (hot榜爬虫会用到).
    Store them in environment variables; do NOT commit real keys.
    """

    api_key: str
    base_url: str

    @staticmethod
    def from_env() -> "UapiSecrets":
        api_key = os.getenv("UAPI_API_KEY", "").strip()
        base_url = os.getenv("UAPI_BASE_URL", "https://api.uapi.example").strip()
        return UapiSecrets(api_key=api_key, base_url=base_url)

    def masked(self) -> dict:
        return {
            "base_url": self.base_url,
            "api_key": "***" if self.api_key else "",
        }

