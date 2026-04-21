from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AiConfig:
    """
    AI provider config for counselor talking assistant.
    Defaults are set for DeepSeek's OpenAI-compatible endpoint.
    """

    api_key: str
    base_url: str
    model: str

    @staticmethod
    def from_env() -> "AiConfig":
        # Keep compatibility with older env names if present.
        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("AI_API_KEY")
            or "sk-fbce499f33044bc8a4ccadfb8d9f7a40"
        ).strip()
        base_url = (
            os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("AI_API_BASE")
            or "https://api.deepseek.com/v1"
        ).strip().rstrip("/")
        model = (
            os.getenv("DEEPSEEK_MODEL")
            or os.getenv("AI_MODEL")
            or "deepseek-chat"
        ).strip()
        return AiConfig(api_key=api_key, base_url=base_url, model=model)

    def masked(self) -> dict[str, str]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key": "***" if self.api_key else "",
        }

