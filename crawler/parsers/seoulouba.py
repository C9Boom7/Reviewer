from __future__ import annotations

import re

from .common import HomepageParser, normalize_title


class SeouloubaParser(HomepageParser):
    def external_id(self, normalized_url: str) -> str | None:
        match = re.search(r"[?&]c=(\d+)", normalized_url)
        return match.group(1) if match else None

    def title_and_reward(self, block: str, fallback_text: str) -> tuple[str, str | None]:
        title = normalize_title(fallback_text)
        title = re.sub(r"\b모집\s*\d[\d,]*\s*명?\b", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title, None
