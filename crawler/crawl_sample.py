#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_AGENT = "CampaignAggregatorBot/0.1 (+https://example.com/bot; contact: admin@example.com)"


@dataclass(frozen=True)
class Source:
    code: str
    name: str
    target_url: str
    robots_url: str
    active: bool
    allowed_link_patterns: list[str]
    detail_fetch: bool
    policy_note: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def clean_text(raw: str) -> str:
    raw = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<svg\b.*?</svg>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def normalize_title(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = re.sub(r"\bD\s*[-+]?\s*\d+\b", " ", value, flags=re.I)
    value = re.sub(r"\d+\s*일\s*남음", " ", value)
    value = re.sub(r"신청\s*\d[\d,]*\s*명?\s*/\s*(모집\s*)?\d[\d,]*\s*명?", " ", value)
    value = re.sub(r"\d[\d,]*\s*P\b", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -|")


def normalize_url(base_url: str, href: str) -> str:
    absolute = urllib.parse.urljoin(base_url, html.unescape(href))
    parsed = urllib.parse.urlsplit(absolute)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if not key.lower().startswith(("utm_", "fbclid", "gclid"))]
    normalized_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, normalized_query, ""))


def external_id_for(source_code: str, url: str) -> str | None:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parsed.query)
    if source_code == "reviewnote":
        match = re.search(r"/campaigns/(\d+)", parsed.path)
        return match.group(1) if match else None
    if source_code == "gangnammatzip":
        return query.get("id", [None])[0]
    if source_code == "ringble":
        return query.get("number", [None])[0]
    if source_code == "reviewplace":
        return query.get("id", [None])[0]
    if source_code == "tble":
        return query.get("cp_id", [None])[0]
    return None


def infer_tags(text: str) -> tuple[list[str], list[str], list[str]]:
    platform_tags: list[str] = []
    region_tags: list[str] = []
    benefit_tags: list[str] = []

    platform_rules = {
        "blog": ["블로그", "blog"],
        "instagram": ["인스타", "릴스", "instagram", "reels"],
        "youtube": ["유튜브", "쇼츠", "youtube", "shorts"],
        "naver_clip": ["클립"],
        "receipt": ["영수증"],
    }
    for tag, needles in platform_rules.items():
        if any(needle.lower() in text.lower() for needle in needles):
            platform_tags.append(tag)

    benefit_rules = {
        "delivery": ["배송", "재택", "제품"],
        "visit": ["방문", "지역", "맛집", "카페", "숙박"],
        "reporter": ["기자단"],
        "purchase_review": ["구매평"],
    }
    for tag, needles in benefit_rules.items():
        if any(needle in text for needle in needles):
            benefit_tags.append(tag)

    for region in ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "제주", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]:
        if region in text:
            region_tags.append(region)

    return sorted(set(platform_tags)), sorted(set(region_tags)), sorted(set(benefit_tags))


def extract_image(block: str, base_url: str) -> str | None:
    match = re.search(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", block, flags=re.I)
    if not match:
        return None
    return normalize_url(base_url, match.group(1))


def first_class_text(block: str, class_name: str) -> str | None:
    pattern = re.compile(
        rf"<(?P<tag>[a-z0-9]+)\b[^>]*\bclass=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>",
        flags=re.I | re.S,
    )
    match = pattern.search(block)
    if not match:
        return None
    value = clean_text(match.group("body"))
    return value or None


def preferred_title_and_reward(source_code: str, block: str, fallback_text: str) -> tuple[str, str | None]:
    if source_code == "reviewplace":
        title = first_class_text(block, "tit")
        reward = first_class_text(block, "txt")
        if title:
            return normalize_title(title), reward

    if source_code == "tble":
        title = first_class_text(block, "t2")
        reward = first_class_text(block, "t3")
        if title:
            return normalize_title(title), reward

    return normalize_title(fallback_text), None


def extract_campaigns(source: Source, page_html: str, limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    anchor_pattern = re.compile(
        r"<a\b(?P<attrs>[^>]*\bhref=[\"'](?P<href>[^\"']+)[\"'][^>]*)>(?P<body>.*?)</a>",
        flags=re.I | re.S,
    )

    for match in anchor_pattern.finditer(page_html):
        href = html.unescape(match.group("href"))
        if not any(pattern in href for pattern in source.allowed_link_patterns):
            continue

        normalized_url = normalize_url(source.target_url, href)
        body = match.group("body")
        text = clean_text(body)
        image_url = extract_image(body, source.target_url)

        if not text:
            alt_match = re.search(r"\balt=[\"']([^\"']+)[\"']", body, flags=re.I)
            text = clean_text(alt_match.group(1)) if alt_match else ""

        if not text or text in {"더보기", "More View"}:
            continue

        title, reward_summary = preferred_title_and_reward(source.code, body, text)
        if len(title) < 3 or title.lower() in {"campaign"} or title in {"캠페인", "캠페인 이미지", "인기 캠페인"}:
            continue

        existing = grouped.get(normalized_url)
        if existing and len(existing["title"]) >= len(title):
            continue

        external_id = external_id_for(source.code, normalized_url)
        platform_tags, region_tags, benefit_tags = infer_tags(text)
        dedup_basis = "|".join([source.code, title.lower(), external_id or normalized_url])

        grouped[normalized_url] = {
            "source_code": source.code,
            "source_name": source.name,
            "external_id": external_id,
            "source_url": normalized_url,
            "normalized_url": normalized_url,
            "title": title,
            "brand_name": None,
            "status": "active",
            "image_url": image_url,
            "reward_summary": reward_summary,
            "location_text": ", ".join(region_tags) if region_tags else None,
            "content_hash": sha256_text(text + "|" + (image_url or "")),
            "dedup_key": sha256_text(dedup_basis),
            "raw_payload": {
                "homepage_text": text,
                "homepage_url": source.target_url,
                "policy_note": source.policy_note,
            },
            "parsed_payload": {
                "platform_tags": platform_tags,
                "region_tags": region_tags,
                "benefit_tags": benefit_tags,
            },
        }

        if len(grouped) >= limit:
            break

    return list(grouped.values())


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
