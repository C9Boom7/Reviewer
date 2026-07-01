from __future__ import annotations

import re
import urllib.parse

from .common import HomepageParser, first_class_text, normalize_title


class ReviewnoteParser(HomepageParser):
    card_marker = '<div class="relative pl-[2.5px]">'
    max_card_length = 7000

    def external_id(self, normalized_url: str) -> str | None:
        parsed = urllib.parse.urlsplit(normalized_url)
        match = re.search(r"/campaigns/(\d+)", parsed.path)
        return match.group(1) if match else None

    def title_and_reward(self, block: str, fallback_text: str) -> tuple[str, str | None]:
        title = first_class_text(block, "text-16m")
        reward = first_class_text(block, "text-14r")
        if title:
            return normalize_title(title), reward
        return super().title_and_reward(block, fallback_text)
