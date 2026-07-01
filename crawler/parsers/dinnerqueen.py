from __future__ import annotations

import re
from typing import Any

from .common import HomepageParser


class DinnerqueenParser(HomepageParser):
    def external_id(self, normalized_url: str) -> str | None:
        match = re.search(r"/taste/(\d+)", normalized_url)
        return match.group(1) if match else None

    def extract_campaigns(self, source: Any, page_html: str, limit: int) -> list[dict[str, Any]]:
        items = super().extract_campaigns(source, page_html, limit=limit * 3)
        filtered = [
            item
            for item in items
            if item.get("external_id") and item.get("title") not in {"메인 캐러셀 링크", "캠페인 더 보기"}
        ]
        return filtered[:limit]
