from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    headless: bool = True
    log_level: str = "INFO"
    demo_base_url: str = "http://127.0.0.1:8000"
    llm_model: str = "gpt-5.6"

    @classmethod
    def from_env(cls) -> "Settings":
        headless_raw = os.getenv("HEADLESS", "true").strip().lower()
        return cls(
            headless=headless_raw not in {"0", "false", "no"},
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            demo_base_url=os.getenv("DEMO_BASE_URL", "http://127.0.0.1:8000"),
            llm_model=os.getenv("LLM_MODEL", "gpt-5.6"),
        )
