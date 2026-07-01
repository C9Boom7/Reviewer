from __future__ import annotations

import re
from typing import Any

from .common import HomepageParser


class ModublogParser(HomepageParser):
    def external_id(self, normalized_url: str) -> str | None:
        match = re.search(r"/product/(\d+)", normalized_url)
        return match.group(1) if match else None

    def extract_campaigns(self, source: Any, page_html: str, limit: int) -> list[dict[str, Any]]:
        items = super().extract_campaigns(source, page_html, limit=limit * 2)
        return [item for item in items if item.get("external_id")][:limit]
