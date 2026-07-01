from __future__ import annotations

import re
import urllib.parse

from .common import HomepageParser, class_texts, clean_text, looks_like_deadline_text, normalize_title


def ringble_reward_text(block: str) -> str | None:
    pattern = re.compile(
        r"<td\b[^>]*color\s*:\s*#aaaaaa[^>]*>(?P<body>.*?)</td>",
        flags=re.I | re.S,
    )
    for match in pattern.finditer(block):
        value = clean_text(match.group("body")).strip()
        if value and not re.search(r"신청|모집", value):
            return value
    return None


class RingbleParser(HomepageParser):
    card_marker = "<td width='240' class='store_list_wrap'"
    max_card_length = 4000

    def external_id(self, normalized_url: str) -> str | None:
        parsed = urllib.parse.urlsplit(normalized_url)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get("number", [None])[0]

    def title_and_reward(self, block: str, fallback_text: str) -> tuple[str, str | None]:
        title = next((value for value in class_texts(block, "list_title") if not looks_like_deadline_text(value)), None)
        reward = ringble_reward_text(block)
        if title:
            return normalize_title(title), reward
        return super().title_and_reward(block, fallback_text)
