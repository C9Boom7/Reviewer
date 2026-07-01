#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import re
import urllib.parse
import urllib.request
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
    source_mode: str = "summary_only"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_sources(path: Path) -> list[Source]:
    raw_sources = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**item) for item in raw_sources]


def robots_allows(robots_url: str, target_url: str) -> bool:
    try:
        robots_text = fetch_text(robots_url)
    except Exception:
        return False
    return robots_text_allows(robots_text, target_url)


def robots_text_allows(robots_text: str, target_url: str) -> bool:
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []

    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if agents and not rules:
                agents.append(value.lower())
                continue
            if agents or rules:
                groups.append((agents, rules))
                rules = []
            agents = [value.lower()]
        elif key in {"allow", "disallow"}:
            rules.append((key, value))

    if agents or rules:
        groups.append((agents, rules))

    matching_rules: list[tuple[str, str]] = []
    user_agent = USER_AGENT.lower()
    for group_agents, group_rules in groups:
        if "*" in group_agents or any(user_agent.startswith(agent) for agent in group_agents if agent != "*"):
            matching_rules.extend(group_rules)

    if not matching_rules:
        return True

    parsed = urllib.parse.urlsplit(target_url)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    best_length = -1
    best_rule = "allow"
    for rule, pattern in matching_rules:
        if rule == "disallow" and pattern == "":
            continue
        if pattern == "":
            continue
        if not robots_pattern_matches(pattern, target):
            continue
        pattern_length = len(pattern.rstrip("$"))
        if pattern_length > best_length or (pattern_length == best_length and rule == "allow"):
            best_length = pattern_length
            best_rule = rule

    return best_rule == "allow"


def robots_pattern_matches(pattern: str, target: str) -> bool:
    exact_end = pattern.endswith("$")
    pattern_body = pattern[:-1] if exact_end else pattern
    escaped = re.escape(pattern_body).replace(r"\*", ".*")
    regex = f"^{escaped}{'$' if exact_end else ''}"
    return bool(re.match(regex, target))


def fetch_text(url: str) -> str:
    try:
        return fetch_text_with_urllib(url)
    except Exception:
        try:
            return fetch_text_with_curl(url)
        except Exception:
            return fetch_text_with_curl(url, insecure=True)


def fetch_text_with_urllib(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "ignore")


def fetch_text_with_curl(url: str, insecure: bool = False) -> str:
    command = [
        "curl",
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "20",
        "--user-agent",
        USER_AGENT,
        "--header",
        "Accept: text/html,application/xhtml+xml,text/plain",
        "--header",
        "Accept-Language: ko-KR,ko;q=0.9,en;q=0.5",
    ]
    if insecure:
        command.append("--insecure")
    command.append(url)
    result = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", "ignore")


def fetch_html(url: str) -> str:
    return fetch_text(url)


def crawl_source(source: Source, limit: int) -> dict[str, Any]:
    started_at = now_iso()
    source_mode = source.source_mode
    if not source.active:
        return {
            "source_code": source.code,
            "source_mode": source_mode,
            "status": "skipped",
            "reason": "source inactive",
            "started_at": started_at,
            "finished_at": now_iso(),
            "items": [],
        }

    if source_mode not in {"full", "summary_only"}:
        return {
            "source_code": source.code,
            "source_mode": source_mode,
            "status": "skipped",
            "reason": f"source mode {source_mode} is not crawlable",
            "started_at": started_at,
            "finished_at": now_iso(),
            "items": [],
        }

    if not robots_allows(source.robots_url, source.target_url):
        return {
            "source_code": source.code,
            "source_mode": source_mode,
            "status": "blocked_by_robots",
            "reason": f"robots.txt does not allow fetching {source.target_url}",
            "started_at": started_at,
            "finished_at": now_iso(),
            "items": [],
        }

    try:
        page_html = fetch_html(source.target_url)
        items = extract_campaigns(source, page_html, limit=limit)
        status = "ok" if items else "empty_parse"
        reason = None if items else f"no campaign snippets matched parser {source.parser}"
        return {
            "source_code": source.code,
            "source_mode": source_mode,
            "status": status,
            "reason": reason,
            "started_at": started_at,
            "finished_at": now_iso(),
            "fetched_url": source.target_url,
            "items": items,
        }
    except Exception as exc:
        return {
            "source_code": source.code,
            "source_mode": source_mode,
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
        "crawl_mode": "source_mode_policy_no_detail_fetch",
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
