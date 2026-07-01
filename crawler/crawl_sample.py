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
from datetime import datetime, time as datetime_time, timedelta, timezone
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
    value = re.sub(r"-?\d+\s*일\s*남음", " ", value)
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
        "purchase_review": ["구매평", "스마트스토어", "쿠팡", "로켓프레시"],
    }
    for tag, needles in benefit_rules.items():
        if any(needle in text for needle in needles):
            benefit_tags.append(tag)

    for region in ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "제주", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]:
        if region in text:
            region_tags.append(region)

    return sorted(set(platform_tags)), sorted(set(region_tags)), sorted(set(benefit_tags))


def extract_image(block: str, base_url: str) -> str | None:
    candidates: list[str] = []
    candidates.extend(re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", block, flags=re.I))
    for srcset in re.findall(r"\bsrcset=[\"']([^\"']+)[\"']", block, flags=re.I):
        for candidate in srcset.split(","):
            url = candidate.strip().split(" ")[0]
            if url:
                candidates.append(url)
    candidates.extend(
        re.findall(
            r"background-image:\s*url\((?:&quot;|[\"']?)(.*?)(?:&quot;|[\"']?)\)",
            block,
            flags=re.I,
        )
    )

    for candidate in candidates:
        image_url = usable_image_url(candidate, base_url)
        if image_url:
            return image_url
    return None


def usable_image_url(value: str, base_url: str) -> str | None:
    value = html.unescape(value).strip()
    if not value or value.startswith("data:") or value == "/empty.webp":
        return None

    absolute = normalize_url(base_url, value)
    parsed = urllib.parse.urlsplit(absolute)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.path.endswith("/_next/image") and query.get("url"):
        return normalize_url(base_url, query["url"][0])
    return absolute


def bracket_groups(text: str) -> list[str]:
    return [clean_text(group) for group in re.findall(r"\[([^\]]+)\]", text) if clean_text(group)]


def split_category_tokens(groups: list[str]) -> list[str]:
    tokens: list[str] = []
    for group in groups:
        tokens.extend(token.strip() for token in re.split(r"[/,·|]", group) if token.strip())
    return tokens


def region_from_token(token: str) -> str | None:
    for region in ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "제주", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]:
        if token.startswith(region) or token == region:
            return region
    return None


def metadata_from_text(text: str) -> dict[str, Any]:
    groups = bracket_groups(text)
    tokens = split_category_tokens(groups)
    platform_tags: set[str] = set()
    region_tags: set[str] = set()
    benefit_tags: set[str] = set()
    location_parts: list[str] = []
    source_categories: list[str] = []

    category_words = {"블로그", "인스타", "릴스", "유튜브", "쇼츠", "클립", "재택", "배송", "방문", "맛집", "카페", "숙박", "구매평", "스마트스토어", "쿠팡", "로켓프레시", "기자단"}
    for group in groups:
        group_tokens = [token.strip() for token in re.split(r"[/,·|]", group) if token.strip()]
        if group_tokens and region_from_token(group_tokens[0]):
            location_tokens = [token for token in group_tokens if token.replace(" ", "") not in category_words]
            if location_tokens:
                location_parts.append(" ".join(location_tokens))

    for token in tokens:
        normalized = token.replace(" ", "")
        source_categories.append(token)
        if normalized in {"재택", "배송"}:
            benefit_tags.add("delivery")
            if normalized == "재택":
                location_parts.append("재택")
        if normalized in {"방문", "맛집", "카페", "숙박"}:
            benefit_tags.add("visit")
        if normalized in {"구매평", "스마트스토어", "쿠팡", "로켓프레시"}:
            benefit_tags.add("purchase_review")
        if normalized == "기자단":
            benefit_tags.add("reporter")
        if "블로그" in normalized:
            platform_tags.add("blog")
        if "인스타" in normalized or "릴스" in normalized:
            platform_tags.add("instagram")
        if "유튜브" in normalized or "쇼츠" in normalized:
            platform_tags.add("youtube")
        if "클립" in normalized:
            platform_tags.add("naver_clip")

        region = region_from_token(token)
        if region:
            region_tags.add(region)
            benefit_tags.add("visit")
            if " " in token:
                location_parts.append(token)

    deadline_text = None
    if re.search(r"오늘\s*마감|오늘마감", text):
        deadline_text = "오늘마감"
    else:
        deadline_match = re.search(r"\bD\s*[-–]\s*(\d+)\b|-?\d+\s*일\s*남음", text, flags=re.I)
        if deadline_match:
            deadline_text = deadline_match.group(0)

    applicant_count = None
    recruit_count = None
    count_match = re.search(r"신청\s*([\d,]+)\s*명?\s*/\s*(?:모집\s*)?([\d,]+)\s*명?", text)
    if count_match:
        applicant_count = int(count_match.group(1).replace(",", ""))
        recruit_count = int(count_match.group(2).replace(",", ""))

    reward_points = None
    points_match = re.search(r"(\d[\d,]*)\s*P\b", text, flags=re.I)
    if points_match:
        reward_points = int(points_match.group(1).replace(",", ""))

    return {
        "source_categories": sorted(set(source_categories)),
        "platform_tags": sorted(platform_tags),
        "region_tags": sorted(region_tags),
        "benefit_tags": sorted(benefit_tags),
        "location_text": " ".join(dict.fromkeys(location_parts)) if location_parts else None,
        "deadline_text": deadline_text,
        "applicant_count": applicant_count,
        "recruit_count": recruit_count,
        "reward_points": reward_points,
    }


def deadline_at_from_text(text: str, base: datetime | None = None) -> str | None:
    days: int | None = None
    if re.search(r"오늘\s*마감|오늘마감|D\s*[-–]\s*DAY", text, flags=re.I):
        days = 0
    else:
        dday_match = re.search(r"\bD\s*[-–]\s*(\d+)\b", text, flags=re.I)
        if dday_match:
            days = int(dday_match.group(1))
        else:
            remain_match = re.search(r"(-?\d+)\s*일\s*남음", text)
            if remain_match:
                days = max(0, int(remain_match.group(1)))

    if days is None:
        return None

    base_date = (base or datetime.now(timezone.utc)).date()
    target_date = base_date + timedelta(days=days)
    # Treat campaign deadlines as end-of-day Korea time, represented in UTC.
    deadline = datetime.combine(target_date, datetime_time(14, 59, 59), tzinfo=timezone.utc)
    return deadline.isoformat()


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


def class_texts(block: str, class_name: str) -> list[str]:
    pattern = re.compile(
        rf"<(?P<tag>[a-z0-9]+)\b[^>]*\bclass=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>",
        flags=re.I | re.S,
    )
    values = []
    for match in pattern.finditer(block):
        value = clean_text(match.group("body"))
        if value:
            values.append(value)
    return values


def looks_like_deadline_text(value: str) -> bool:
    return bool(re.search(r"오늘\s*마감|오늘마감|\bD\s*[-–]\s*(?:DAY|\d+)\b|-?\d+\s*일\s*남음", value, flags=re.I))


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


def preferred_title_and_reward(source_code: str, block: str, fallback_text: str) -> tuple[str, str | None]:
    if source_code == "reviewnote":
        title = first_class_text(block, "text-16m")
        reward = first_class_text(block, "text-14r")
        if title:
            return normalize_title(title), reward

    if source_code == "ringble":
        title = next((value for value in class_texts(block, "list_title") if not looks_like_deadline_text(value)), None)
        reward = ringble_reward_text(block)
        if title:
            return normalize_title(title), reward

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


def card_block_for_anchor(source_code: str, page_html: str, match: re.Match[str]) -> str:
    markers = {
        "reviewnote": '<div class="relative pl-[2.5px]">',
        "ringble": "<td width='240' class='store_list_wrap'",
    }
    marker = markers.get(source_code)
    if not marker:
        return match.group("body")

    start = page_html.rfind(marker, 0, match.start())
    if start == -1:
        return match.group("body")

    next_start = page_html.find(marker, match.end())
    if next_start == -1:
        max_lengths = {"reviewnote": 7000, "ringble": 4000}
        next_start = min(len(page_html), start + max_lengths.get(source_code, 5000))
    return page_html[start:next_start]


def extract_campaigns(source: Source, page_html: str, limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    image_by_url: dict[str, str] = {}
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
        card_block = card_block_for_anchor(source.code, page_html, match)
        text = clean_text(card_block)
        image_url = extract_image(card_block, source.target_url)
        if image_url:
            image_by_url[normalized_url] = image_url
            if normalized_url in grouped and not grouped[normalized_url].get("image_url"):
                grouped[normalized_url]["image_url"] = image_url

        if not text:
            alt_match = re.search(r"\balt=[\"']([^\"']+)[\"']", body, flags=re.I)
            text = clean_text(alt_match.group(1)) if alt_match else ""

        if not text or text in {"더보기", "More View"}:
            continue

        title, reward_summary = preferred_title_and_reward(source.code, card_block, text)
        if len(title) < 3 or title.lower() in {"campaign"} or title in {"캠페인", "캠페인 이미지", "인기 캠페인"}:
            continue

        existing = grouped.get(normalized_url)
        if existing and len(existing["title"]) >= len(title):
            continue

        external_id = external_id_for(source.code, normalized_url)
        platform_tags, region_tags, benefit_tags = infer_tags(text)
        metadata = metadata_from_text(text)
        platform_tags = sorted(set(platform_tags) | set(metadata["platform_tags"]))
        region_tags = sorted(set(region_tags) | set(metadata["region_tags"]))
        benefit_tags = sorted(set(benefit_tags) | set(metadata["benefit_tags"]))
        location_text = metadata["location_text"] or (", ".join(region_tags) if region_tags else None)
        application_deadline_at = deadline_at_from_text(text)
        final_image_url = image_url or image_by_url.get(normalized_url)
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
            "image_url": final_image_url,
            "application_deadline_at": application_deadline_at,
            "reward_summary": reward_summary,
            "location_text": location_text,
            "content_hash": sha256_text(text + "|" + (final_image_url or "")),
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
                "source_categories": metadata["source_categories"],
                "deadline_text": metadata["deadline_text"],
                "applicant_count": metadata["applicant_count"],
                "recruit_count": metadata["recruit_count"],
                "reward_points": metadata["reward_points"],
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
