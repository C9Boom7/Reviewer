from __future__ import annotations

from typing import Any

from .common import HomepageParser
from .gangnammatzip import GangnamMatzipParser
from .reviewnote import ReviewnoteParser
from .reviewplace import ReviewplaceParser
from .ringble import RingbleParser
from .tble import TbleParser


PARSERS: dict[str, HomepageParser] = {
    "gangnammatzip": GangnamMatzipParser(),
    "reviewnote": ReviewnoteParser(),
    "reviewplace": ReviewplaceParser(),
    "ringble": RingbleParser(),
    "tble": TbleParser(),
}


def extract_campaigns(source: Any, page_html: str, limit: int) -> list[dict[str, Any]]:
    parser = PARSERS.get(source.code, HomepageParser())
    return parser.extract_campaigns(source, page_html, limit=limit)
