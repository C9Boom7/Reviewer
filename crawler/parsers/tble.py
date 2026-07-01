from __future__ import annotations

import urllib.parse

from .common import HomepageParser, first_class_text, normalize_title


class TbleParser(HomepageParser):
    def external_id(self, normalized_url: str) -> str | None:
        parsed = urllib.parse.urlsplit(normalized_url)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get("cp_id", [None])[0]

    def title_and_reward(self, block: str, fallback_text: str) -> tuple[str, str | None]:
        title = first_class_text(block, "t2")
        reward = first_class_text(block, "t3")
        if title:
            return normalize_title(title), reward
        return super().title_and_reward(block, fallback_text)
