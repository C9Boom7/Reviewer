#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_for_key(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


def canonical_key_for(item: dict[str, Any]) -> str:
    # Conservative cross-source merge: title + reward must match after normalization.
    # This may leave duplicates, which is safer than merging unrelated campaigns.
    basis = "|".join(
        [
            normalize_for_key(item.get("title")),
            normalize_for_key(item.get("reward_summary")),
            normalize_for_key(item.get("location_text")),
        ]
    )
    return sha256_text(basis)


def clean_supabase_url(value: str) -> str:
    return value.rstrip("/")


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


@dataclass
class SupabaseClient:
    base_url: str
    service_key: str
    dry_run: bool = False

    @property
    def rest_url(self) -> str:
        return f"{self.base_url}/rest/v1"

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self.dry_run and method.upper() != "GET":
            print(f"[dry-run] {method} {path}")
            return []

        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
        }
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)

        request = urllib.request.Request(
            f"{self.rest_url}{path}",
            data=body,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            raise RuntimeError(f"Supabase {method} {path} failed: HTTP {exc.code} {detail}") from exc

        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def select_sources(self, codes: list[str]) -> dict[str, str]:
        if not codes:
            return {}
        if self.dry_run:
            return {code: f"dry-source-{sha256_text(code)[:12]}" for code in codes}
        encoded_codes = ",".join(codes)
        rows = self.request("GET", f"/sources?select=id,code&code=in.({encoded_codes})")
        return {row["code"]: row["id"] for row in rows}

    def select_paginated(self, path: str, page_size: int = 1000) -> list[dict[str, Any]]:
        if self.dry_run:
            return []

        rows: list[dict[str, Any]] = []
        offset = 0
        separator = "&" if "?" in path else "?"
        while True:
            page = self.request("GET", f"{path}{separator}limit={page_size}&offset={offset}")
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def select_active_listings(self, source_id: str) -> list[dict[str, Any]]:
        if self.dry_run:
            return []
        encoded_source_id = urllib.parse.quote(source_id, safe="")
        return self.select_paginated(
            f"/source_listings?select=id,normalized_url&source_id=eq.{encoded_source_id}&status=eq.active",
        )

    def select_active_listing_ids(self) -> set[str]:
        if self.dry_run:
            return set()
        rows = self.select_paginated("/source_listings?select=id&status=eq.active")
        return {row["id"] for row in rows}

    def select_active_campaign_ids(self) -> set[str]:
        if self.dry_run:
            return set()
        rows = self.select_paginated("/campaigns?select=id&status=eq.active")
        return {row["id"] for row in rows}

    def select_campaign_ids_for_listings(self, listing_ids: list[str]) -> set[str]:
        if not listing_ids or self.dry_run:
            return set()
        campaign_ids: set[str] = set()
        for listing_id_chunk in chunked(listing_ids, 80):
            encoded_ids = ",".join(urllib.parse.quote(value, safe="") for value in listing_id_chunk)
            rows = self.request(
                "GET",
                f"/campaign_source_listings?select=campaign_id,source_listing_id&source_listing_id=in.({encoded_ids})",
            )
            campaign_ids.update(row["campaign_id"] for row in rows)
        return campaign_ids

    def select_listing_statuses_for_campaign(self, campaign_id: str) -> list[str]:
        if self.dry_run:
            return []
        encoded_campaign_id = urllib.parse.quote(campaign_id, safe="")
        links = self.request(
            "GET",
            f"/campaign_source_listings?select=source_listing_id&campaign_id=eq.{encoded_campaign_id}",
        )
        listing_ids = [row["source_listing_id"] for row in links]
        if not listing_ids:
            return []

        statuses: list[str] = []
        for listing_id_chunk in chunked(listing_ids, 80):
            encoded_ids = ",".join(urllib.parse.quote(value, safe="") for value in listing_id_chunk)
            rows = self.request("GET", f"/source_listings?select=id,status&id=in.({encoded_ids})")
            statuses.extend(row["status"] for row in rows)
        return statuses

    def select_listing_id(self, row: dict[str, Any]) -> str | None:
        if self.dry_run:
            return None

        select = "select=id,normalized_url,external_id,dedup_key"
        filters = [
            ("external_id", row.get("external_id")),
            ("normalized_url", row["normalized_url"]),
            ("dedup_key", row["dedup_key"]),
        ]
        for column, value in filters:
            if value is None:
                continue
            encoded_value = urllib.parse.quote(str(value), safe="")
            path = f"/source_listings?{select}&source_id=eq.{row['source_id']}&{column}=eq.{encoded_value}&limit=1"
            rows = self.request("GET", path)
            if rows:
                return rows[0]["id"]
        return None

    def patch_by_id(self, table: str, row_id: str, row: dict[str, Any], return_representation: bool) -> list[dict[str, Any]]:
        if self.dry_run:
            print(f"[dry-run] PATCH /{table}?id=eq.{row_id}")
            result = dict(row)
            result["id"] = row_id
            return [result]

        prefer = "return=representation" if return_representation else "return=minimal"
        result = self.request(
            "PATCH",
            f"/{table}?id=eq.{row_id}",
            row,
            headers={"Prefer": prefer},
        )
        return result or []

    def insert_one(self, table: str, row: dict[str, Any], return_representation: bool) -> list[dict[str, Any]]:
        if self.dry_run:
            print(f"[dry-run] POST /{table}")
            result = dict(row)
            result["id"] = f"dry-{table}-{sha256_text(json.dumps(row, sort_keys=True, default=str))[:12]}"
            return [result]

        return self.insert(table, [row], return_representation=return_representation)

    def upsert_listing(self, row: dict[str, Any]) -> dict[str, Any]:
        existing_id = self.select_listing_id(row)
        if existing_id:
            rows = self.patch_by_id("source_listings", existing_id, row, return_representation=True)
            return rows[0]

        try:
            rows = self.insert_one("source_listings", row, return_representation=True)
            return rows[0]
        except RuntimeError:
            # A concurrent run or a secondary unique key may have won between lookup and insert.
            existing_id = self.select_listing_id(row)
            if not existing_id:
                raise
            rows = self.patch_by_id("source_listings", existing_id, row, return_representation=True)
            return rows[0]

    def upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str, return_representation: bool) -> list[dict[str, Any]]:
        if not rows:
            return []
        if self.dry_run:
            print(f"[dry-run] POST /{table}?on_conflict={on_conflict} rows={len(rows)}")
            if not return_representation:
                return []
            result_rows = []
            for row in rows:
                result = dict(row)
                result["id"] = f"dry-{table}-{sha256_text(json.dumps(row, sort_keys=True, default=str))[:12]}"
                result_rows.append(result)
            return result_rows
        query = urllib.parse.urlencode({"on_conflict": on_conflict})
        prefer = "resolution=merge-duplicates"
        prefer += ",return=representation" if return_representation else ",return=minimal"
        result = self.request(
            "POST",
            f"/{table}?{query}",
            rows,
            headers={"Prefer": prefer},
        )
        return result or []

    def insert(self, table: str, rows: list[dict[str, Any]], return_representation: bool) -> list[dict[str, Any]]:
        if not rows:
            return []
        if self.dry_run:
            print(f"[dry-run] POST /{table} rows={len(rows)}")
            if not return_representation:
                return []
            result_rows = []
            for row in rows:
                result = dict(row)
                result["id"] = f"dry-{table}-{sha256_text(json.dumps(row, sort_keys=True, default=str))[:12]}"
                result_rows.append(result)
            return result_rows
        prefer = "return=representation" if return_representation else "return=minimal"
        result = self.request(
            "POST",
            f"/{table}",
            rows,
            headers={"Prefer": prefer},
        )
        return result or []


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_source_configs(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_seed_rows(source_configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, source in enumerate(source_configs, start=1):
        rows.append(
            {
                "code": source["code"],
                "name": source["name"],
                "homepage_url": source["target_url"],
                "robots_url": source["robots_url"],
                "crawl_priority": index * 10,
                "is_active": bool(source["active"]),
                "crawl_interval_minutes": 120,
                "crawl_policy": {
                    "status": "homepage_only" if source["active"] else "inactive",
                    "reason": source.get("policy_note"),
                },
                "crawler_config": {
                    "parser": source.get("parser", "homepage_anchor_snippets"),
                    "target_url": source["target_url"],
                    "allowed_link_patterns": source["allowed_link_patterns"],
                    "detail_fetch": source["detail_fetch"],
                },
                "notes": source.get("policy_note"),
            }
        )
    return rows


def listing_row(item: dict[str, Any], source_id: str, crawled_at: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "external_id": item.get("external_id"),
        "source_url": item["source_url"],
        "normalized_url": item["normalized_url"],
        "title": item["title"],
        "brand_name": item.get("brand_name"),
        "status": item.get("status", "active"),
        "application_deadline_at": item.get("application_deadline_at"),
        "image_url": item.get("image_url"),
        "reward_summary": item.get("reward_summary"),
        "location_text": item.get("location_text"),
        "content_hash": item.get("content_hash"),
        "dedup_key": item["dedup_key"],
        "raw_payload": item.get("raw_payload", {}),
        "parsed_payload": item.get("parsed_payload", {}),
        "last_seen_at": crawled_at,
        "last_crawled_at": crawled_at,
    }


def campaign_row(item: dict[str, Any], crawled_at: str) -> dict[str, Any]:
    parsed = item.get("parsed_payload", {})
    platform_tags = parsed.get("platform_tags") or []
    region_tags = parsed.get("region_tags") or []
    benefit_tags = parsed.get("benefit_tags") or []
    canonical_key = canonical_key_for(item)

    return {
        "canonical_key": canonical_key,
        "title": item["title"],
        "brand_name": item.get("brand_name"),
        "summary": item.get("reward_summary"),
        "status": "active",
        "application_deadline_at": item.get("application_deadline_at"),
        "reward_summary": item.get("reward_summary"),
        "location_text": item.get("location_text"),
        "primary_image_url": item.get("image_url"),
        "canonical_url": item.get("source_url"),
        "platform_tags": platform_tags,
        "region_tags": region_tags,
        "benefit_tags": benefit_tags,
        "details": {
            "latest_source_code": item.get("source_code"),
            "latest_external_id": item.get("external_id"),
            "deadline_text": parsed.get("deadline_text"),
            "applicant_count": parsed.get("applicant_count"),
            "recruit_count": parsed.get("recruit_count"),
            "reward_points": parsed.get("reward_points"),
            "source_categories": parsed.get("source_categories") or [],
        },
        "dedup_meta": {
            "strategy": "normalized_title_reward_location_v1",
            "source_dedup_key": item.get("dedup_key"),
        },
        "last_seen_at": crawled_at,
    }


def current_urls_by_source(campaigns: list[dict[str, Any]]) -> dict[str, set[str]]:
    urls_by_source: dict[str, set[str]] = {}
    for item in campaigns:
        urls_by_source.setdefault(item["source_code"], set()).add(item["normalized_url"])
    return urls_by_source


def successful_source_codes(source_summaries: list[dict[str, Any]]) -> set[str]:
    return {
        summary["source_code"]
        for summary in source_summaries
        if summary.get("status") == "ok" and int(summary.get("item_count") or 0) > 0
    }


def is_error_status(status: str) -> bool:
    return status not in {"ok", "empty_parse", "skipped"}


def mark_blocked_sources(
    source_summaries: list[dict[str, Any]],
    source_configs: list[dict[str, Any]],
    source_ids: dict[str, str],
    client: SupabaseClient,
) -> int:
    source_config_by_code = {source["code"]: source for source in source_configs}
    blocked_count = 0
    for summary in source_summaries:
        if summary.get("status") != "blocked_by_robots":
            continue
        source_id = source_ids.get(summary["source_code"])
        if not source_id:
            continue
        source_config = source_config_by_code.get(summary["source_code"], {})
        client.patch_by_id(
            "sources",
            source_id,
            {
                "crawl_policy": {
                    "status": "blocked_by_robots_candidate",
                    "reason": summary.get("reason"),
                    "last_checked_at": summary.get("finished_at") or now_iso(),
                    "policy_note": source_config.get("policy_note"),
                },
                "notes": f"Blocked by robots candidate: {summary.get('reason')}",
            },
            return_representation=False,
        )
        blocked_count += 1
    return blocked_count


def close_stale_listings_and_campaigns(
    campaigns: list[dict[str, Any]],
    source_summaries: list[dict[str, Any]],
    source_ids: dict[str, str],
    client: SupabaseClient,
    crawled_at: str,
) -> tuple[dict[str, int], int]:
    urls_by_source = current_urls_by_source(campaigns)
    stale_counts_by_source: dict[str, int] = {}
    affected_campaign_ids: set[str] = set()

    for source_code in successful_source_codes(source_summaries):
        source_id = source_ids.get(source_code)
        if not source_id:
            continue
        current_urls = urls_by_source.get(source_code, set())
        if not current_urls:
            continue

        active_rows = client.select_active_listings(source_id)
        stale_rows = [row for row in active_rows if row["normalized_url"] not in current_urls]
        stale_ids = [row["id"] for row in stale_rows]
        stale_counts_by_source[source_code] = len(stale_ids)
        if not stale_ids:
            continue

        affected_campaign_ids.update(client.select_campaign_ids_for_listings(stale_ids))
        for stale_id in stale_ids:
            client.patch_by_id(
                "source_listings",
                stale_id,
                {
                    "status": "removed",
                    "last_crawled_at": crawled_at,
                },
                return_representation=False,
            )

    closed_campaigns = 0
    for campaign_id in sorted(affected_campaign_ids):
        statuses = client.select_listing_statuses_for_campaign(campaign_id)
        if statuses and any(status == "active" for status in statuses):
            continue
        client.patch_by_id(
            "campaigns",
            campaign_id,
            {"status": "closed"},
            return_representation=False,
        )
        closed_campaigns += 1

    return stale_counts_by_source, closed_campaigns


def close_orphan_campaigns(client: SupabaseClient) -> int:
    active_campaign_ids = client.select_active_campaign_ids()
    if not active_campaign_ids:
        return 0

    active_listing_ids = client.select_active_listing_ids()
    campaign_ids_with_active_listings = client.select_campaign_ids_for_listings(sorted(active_listing_ids))
    orphan_campaign_ids = sorted(active_campaign_ids - campaign_ids_with_active_listings)

    for campaign_id in orphan_campaign_ids:
        client.patch_by_id(
            "campaigns",
            campaign_id,
            {"status": "closed"},
            return_representation=False,
        )

    return len(orphan_campaign_ids)


def sync(payload: dict[str, Any], source_configs: list[dict[str, Any]], client: SupabaseClient) -> dict[str, Any]:
    crawled_at = payload.get("generated_at") or now_iso()
    campaigns = payload.get("campaigns", [])
    source_summaries = payload.get("source_summaries", [])
    source_codes = sorted(
        {item["source_code"] for item in campaigns}
        | {summary["source_code"] for summary in source_summaries}
    )

    client.upsert("sources", source_seed_rows(source_configs), on_conflict="code", return_representation=False)
    source_ids = client.select_sources(source_codes)
    missing_sources = sorted(set(source_codes) - set(source_ids))
    if missing_sources:
        raise RuntimeError(f"Missing sources after upsert: {', '.join(missing_sources)}")

    listing_rows = [listing_row(item, source_ids[item["source_code"]], crawled_at) for item in campaigns]
    listing_results = [client.upsert_listing(row) for row in listing_rows]
    listing_ids_by_url = {row["normalized_url"]: row["id"] for row in listing_results}

    campaign_rows_by_key: dict[str, dict[str, Any]] = {}
    item_key_by_url: dict[str, str] = {}
    for item in campaigns:
        row = campaign_row(item, crawled_at)
        campaign_rows_by_key[row["canonical_key"]] = row
        item_key_by_url[item["normalized_url"]] = row["canonical_key"]

    campaign_results = client.upsert(
        "campaigns",
        list(campaign_rows_by_key.values()),
        on_conflict="canonical_key",
        return_representation=True,
    )
    campaign_ids_by_key = {row["canonical_key"]: row["id"] for row in campaign_results}

    links = []
    for item in campaigns:
        listing_id = listing_ids_by_url.get(item["normalized_url"])
        campaign_id = campaign_ids_by_key.get(item_key_by_url[item["normalized_url"]])
        if not listing_id or not campaign_id:
            continue
        links.append(
            {
                "campaign_id": campaign_id,
                "source_listing_id": listing_id,
                "is_primary": True,
                "match_confidence": 0.900,
                "match_reason": "canonical_key:normalized_title_reward_location_v1",
            }
        )

    client.upsert(
        "campaign_source_listings",
        links,
        on_conflict="source_listing_id",
        return_representation=False,
    )

    stale_counts_by_source, closed_campaigns = close_stale_listings_and_campaigns(
        campaigns,
        source_summaries,
        source_ids,
        client,
        crawled_at,
    )
    orphan_campaigns_closed = close_orphan_campaigns(client)
    blocked_source_candidates = mark_blocked_sources(source_summaries, source_configs, source_ids, client)

    run_rows = []
    github_run_id = os.environ.get("GITHUB_RUN_ID")
    git_sha = os.environ.get("GITHUB_SHA")
    for summary in source_summaries:
        source_id = source_ids.get(summary["source_code"])
        closed_count = stale_counts_by_source.get(summary["source_code"], 0)
        summary["closed_count"] = closed_count
        run_rows.append(
            {
                "source_id": source_id,
                "github_run_id": github_run_id,
                "git_sha": git_sha,
                "status": summary["status"],
                "started_at": summary.get("started_at") or crawled_at,
                "finished_at": summary.get("finished_at") or now_iso(),
                "fetched_count": summary.get("item_count", 0),
                "upserted_count": summary.get("item_count", 0) if summary["status"] == "ok" else 0,
                "closed_count": closed_count,
                "error_count": 1 if is_error_status(summary["status"]) else 0,
                "error_message": summary.get("reason"),
                "meta": summary,
            }
        )
    client.insert("crawler_runs", run_rows, return_representation=False)

    return {
        "sources": len(source_ids),
        "source_listings": len(listing_rows),
        "campaigns": len(campaign_rows_by_key),
        "links": len(links),
        "stale_source_listings": sum(stale_counts_by_source.values()),
        "closed_campaigns": closed_campaigns,
        "orphan_campaigns_closed": orphan_campaigns_closed,
        "total_campaigns_closed": closed_campaigns + orphan_campaigns_closed,
        "blocked_source_candidates": blocked_source_candidates,
        "crawler_runs": len(run_rows),
    }


def build_client(args: argparse.Namespace) -> SupabaseClient:
    url = args.supabase_url or os.environ.get(SUPABASE_URL_ENV)
    key = args.supabase_key or os.environ.get(SUPABASE_KEY_ENV)
    if args.dry_run:
        return SupabaseClient(base_url=clean_supabase_url(url or "https://dry-run.supabase.co"), service_key=key or "dry-run", dry_run=True)
    if not url:
        raise SystemExit(f"Missing {SUPABASE_URL_ENV}")
    if not key:
        raise SystemExit(f"Missing {SUPABASE_KEY_ENV}")
    return SupabaseClient(base_url=clean_supabase_url(url), service_key=key, dry_run=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync crawled campaign JSON into Supabase.")
    parser.add_argument("--input", type=Path, default=Path("data/samples/campaigns.sample.json"))
    parser.add_argument("--sources", type=Path, default=Path("crawler/sources.json"))
    parser.add_argument("--supabase-url")
    parser.add_argument("--supabase-key")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = load_json(args.input)
    source_configs = load_source_configs(args.sources)
    client = build_client(args)
    result = sync(payload, source_configs, client)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        raise
