from __future__ import annotations

import re
from typing import Any

from .common import HomepageParser, clean_text, first_class_text, normalize_title


class DinnerqueenParser(HomepageParser):
    card_marker = '<div class="qz-col'

    def external_id(self, normalized_url: str) -> str | None:
        match = re.search(r"/taste/(\d+)", normalized_url)
        return match.group(1) if match else None

    def title_and_reward(self, block: str, fallback_text: str) -> tuple[str, str | None]:
        title_match = re.search(r"\btitle=[\"']([^\"']+?)(?:\s*신청하기)?[\"']", block, flags=re.I | re.S)
        title = clean_text(title_match.group(1)) if title_match else None
        if not title:
            title = first_class_text(block, "color-title") or first_class_text(block, "qz-body2-kr--line")
        if not title:
            title = fallback_text
        return normalize_title(title), None

    def extract_campaigns(self, source: Any, page_html: str, limit: int) -> list[dict[str, Any]]:
        items = super().extract_campaigns(source, page_html, limit=limit * 20)
        ignored_titles = {"메인 캐러셀 링크", "캐러셀 링크", "캠페인 더 보기"}
        filtered = [
            item
            for item in items
            if item.get("external_id") and item.get("title") not in ignored_titles
        ]
        return filtered[:limit]
