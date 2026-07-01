from __future__ import annotations

import urllib.parse

from .common import HomepageParser


class GangnamMatzipParser(HomepageParser):
    def external_id(self, normalized_url: str) -> str | None:
        parsed = urllib.parse.urlsplit(normalized_url)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get("id", [None])[0]
