#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from parsers import extract_campaigns
except ImportError:
    from crawler.parsers import extract_campaigns


USER_AGENT = "CampaignAggregatorBot/0.1 (+https://example.com/bot; contact: admin@example.com)"


@dataclass(frozen=True)
class Source:
    code: str
    name: str
    target_url: str
    robots_url: str
    active: bool
    parser: str
    allowed_link_patterns: list[str]
    detail_fetch: bool
    policy_note: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_sources(path: Path) -> list[Source]:
    raw_sources = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**item) for item in raw_sources]


def robots_allows(robots_url: str, target_url: str) -> bool:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return False
    return parser.can_fetch(USER_AGENT, target_url)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "ignore")


def crawl_source(source: Source, limit: int) -> dict[str, Any]:
    started_at = now_iso()
    if not source.active:
        return {
            "source_code": source.code,
            "status": "skipped",
            "reason": "source inactive",
            "started_at": started_at,
            "finished_at": now_iso(),
            "items": [],
        }

    if not robots_allows(source.robots_url, source.target_url):
        return {
            "source_code": source.code,
            "status": "blocked_by_robots",
            "reason": f"robots.txt does not allow fetching {source.target_url}",
            "started_at": started_at,
            "finished_at": now_iso(),
            "items": [],
        }

    try:
        page_html = fetch_html(source.target_url)
        items = extract_campaigns(source, page_html, limit=limit)
        return {
            "source_code": source.code,
            "status": "ok",
            "reason": None,
            "started_at": started_at,
            "finished_at": now_iso(),
            "fetched_url": source.target_url,
            "items": items,
        }
    except Exception as exc:
        return {
            "source_code": source.code,
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
            "started_at": started_at,
            "finished_at": now_iso(),
            "items": [],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch homepage campaign snippets from configured review campaign sources.")
    parser.add_argument("--sources", type=Path, default=Path("crawler/sources.json"))
    parser.add_argument("--out", type=Path, default=Path("data/samples/campaigns.sample.json"))
    parser.add_argument("--limit-per-source", type=int, default=12)
    parser.add_argument("--sleep", type=float, default=1.5)
    args = parser.parse_args()

    sources = load_sources(args.sources)
    source_runs: list[dict[str, Any]] = []
    campaigns: list[dict[str, Any]] = []

    for index, source in enumerate(sources):
        if index > 0:
            time.sleep(args.sleep)
        result = crawl_source(source, limit=args.limit_per_source)
        source_runs.append(result)
        campaigns.extend(result["items"])

    payload = {
        "generated_at": now_iso(),
        "crawl_mode": "homepage_only_no_detail_fetch",
        "source_summaries": [
            {
                **{key: value for key, value in result.items() if key != "items"},
                "item_count": len(result["items"]),
            }
            for result in source_runs
        ],
        "campaigns": campaigns,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "campaign_count": len(campaigns)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
