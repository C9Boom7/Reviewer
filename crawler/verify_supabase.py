#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

from sync_supabase import SUPABASE_KEY_ENV, SUPABASE_URL_ENV, SupabaseClient, clean_supabase_url


def env_value(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def build_client(args: argparse.Namespace) -> SupabaseClient:
    url = args.supabase_url or env_value(SUPABASE_URL_ENV)
    key = args.supabase_key or env_value(SUPABASE_KEY_ENV)
    if not url:
        raise SystemExit(f"Missing {SUPABASE_URL_ENV}")
    if not key:
        raise SystemExit(f"Missing {SUPABASE_KEY_ENV}")
    return SupabaseClient(base_url=clean_supabase_url(url), service_key=key, dry_run=False)


def encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def select_latest_run_id(client: SupabaseClient) -> str | None:
    rows = client.request(
        "GET",
        "/crawler_runs?select=github_run_id&github_run_id=not.is.null&order=finished_at.desc&limit=1",
    )
    if not rows:
        return None
    return rows[0].get("github_run_id")


def select_run_rows(client: SupabaseClient, github_run_id: str | None) -> list[dict[str, Any]]:
    run_id = github_run_id or select_latest_run_id(client)
    if not run_id:
        return []
    encoded_run_id = encode(run_id)
    return client.request(
        "GET",
        "/crawler_runs"
        "?select=github_run_id,status,started_at,finished_at,fetched_count,upserted_count,closed_count,error_count,error_message,meta,sources(code,name)"
        f"&github_run_id=eq.{encoded_run_id}"
        "&order=finished_at.desc",
    )


def select_sources(client: SupabaseClient) -> dict[str, dict[str, str]]:
    rows = client.request("GET", "/sources?select=id,code,name&limit=1000")
    return {row["id"]: {"code": row["code"], "name": row["name"]} for row in rows}


def select_all_rows(client: SupabaseClient, table: str, select: str, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.request("GET", f"/{table}?select={select}&limit={page_size}&offset={offset}")
        if not page:
            break
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def source_listing_metrics(client: SupabaseClient) -> list[dict[str, Any]]:
    sources_by_id = select_sources(client)
    rows = select_all_rows(
        client,
        "source_listings",
        "source_id,status,image_url,application_deadline_at,reward_summary,location_text",
    )
    metrics: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "code": "unknown",
            "name": "unknown",
            "active_count": 0,
            "removed_count": 0,
            "with_image": 0,
            "with_deadline": 0,
            "with_reward": 0,
            "with_location": 0,
        }
    )

    for row in rows:
        source = sources_by_id.get(row["source_id"], {"code": "unknown", "name": "unknown"})
        metric = metrics[source["code"]]
        metric["code"] = source["code"]
        metric["name"] = source["name"]
        if row["status"] == "active":
            metric["active_count"] += 1
            metric["with_image"] += int(bool(row.get("image_url")))
            metric["with_deadline"] += int(bool(row.get("application_deadline_at")))
            metric["with_reward"] += int(bool(row.get("reward_summary")))
            metric["with_location"] += int(bool(row.get("location_text")))
        elif row["status"] == "removed":
            metric["removed_count"] += 1

    return sorted(metrics.values(), key=lambda value: value["code"])


def campaign_card_metrics(client: SupabaseClient) -> dict[str, int]:
    rows = select_all_rows(
        client,
        "campaign_cards",
        "id,status,source_count,primary_image_url,application_deadline_at,reward_summary,location_text",
    )
    active_rows = [row for row in rows if row.get("status") == "active"]
    return {
        "active_count": len(active_rows),
        "without_active_sources": sum(int(row.get("source_count") or 0) == 0 for row in active_rows),
        "with_image": sum(bool(row.get("primary_image_url")) for row in active_rows),
        "with_deadline": sum(bool(row.get("application_deadline_at")) for row in active_rows),
        "with_reward": sum(bool(row.get("reward_summary")) for row in active_rows),
        "with_location": sum(bool(row.get("location_text")) for row in active_rows),
    }


def source_from_run_row(row: dict[str, Any]) -> dict[str, str | None]:
    source = row.get("sources")
    if isinstance(source, dict):
        return {"code": source.get("code"), "name": source.get("name")}
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    return {"code": meta.get("source_code"), "name": meta.get("source_code")}


def build_warnings(run_rows: list[dict[str, Any]], source_metrics: list[dict[str, Any]], campaign_metrics: dict[str, int]) -> list[str]:
    warnings: list[str] = []
    if not run_rows:
        warnings.append("No crawler_runs rows found for verification target.")

    for row in run_rows:
        source = source_from_run_row(row)
        status = row.get("status")
        if status == "empty_parse":
            warnings.append(f"{source.get('code') or 'unknown'} fetched the homepage but parsed 0 campaign cards.")
        elif status not in {"ok", "blocked_by_robots", "skipped"}:
            warnings.append(f"{source.get('code') or 'unknown'} finished with status={status}.")

    for metric in source_metrics:
        if metric["active_count"] <= 0:
            continue
        if metric["with_reward"] == 0:
            warnings.append(f"{metric['code']} has active listings but no reward_summary values.")
        if metric["with_deadline"] == 0:
            warnings.append(f"{metric['code']} has active listings but no application_deadline_at values.")

    if campaign_metrics["active_count"] > 0 and campaign_metrics["with_reward"] == 0:
        warnings.append("campaign_cards has active rows but no reward_summary values.")
    active_listing_total = sum(metric["active_count"] for metric in source_metrics)
    if campaign_metrics["active_count"] > active_listing_total:
        warnings.append(
            f"campaign_cards active rows ({campaign_metrics['active_count']}) exceed active source listings ({active_listing_total})."
        )
    if campaign_metrics["without_active_sources"] > 0:
        warnings.append(f"{campaign_metrics['without_active_sources']} active campaign_cards rows have source_count=0.")
    return warnings


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    output = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        output.append("| " + " | ".join(str(value) if value is not None else "" for value in row) + " |")
    return "\n".join(output)


def build_markdown(result: dict[str, Any]) -> str:
    run_rows = result["run_rows"]
    source_metrics = result["source_metrics"]
    campaign_metrics = result["campaign_metrics"]
    warnings = result["warnings"]

    run_table = markdown_table(
        ["source", "status", "fetched", "upserted", "closed", "errors", "message"],
        [
            [
                source_from_run_row(row).get("code"),
                row.get("status"),
                row.get("fetched_count"),
                row.get("upserted_count"),
                row.get("closed_count"),
                row.get("error_count"),
                row.get("error_message") or "",
            ]
            for row in run_rows
        ],
    )
    listing_table = markdown_table(
        ["source", "active", "removed", "image", "deadline", "reward", "location"],
        [
            [
                metric["code"],
                metric["active_count"],
                metric["removed_count"],
                metric["with_image"],
                metric["with_deadline"],
                metric["with_reward"],
                metric["with_location"],
            ]
            for metric in source_metrics
        ],
    )
    campaign_table = markdown_table(
        ["active", "no active source", "image", "deadline", "reward", "location"],
        [
            [
                campaign_metrics["active_count"],
                campaign_metrics["without_active_sources"],
                campaign_metrics["with_image"],
                campaign_metrics["with_deadline"],
                campaign_metrics["with_reward"],
                campaign_metrics["with_location"],
            ]
        ],
    )
    warning_lines = "\n".join(f"- {warning}" for warning in warnings) if warnings else "- No warnings."
    return "\n\n".join(
        [
            "## Supabase crawl verification",
            f"GitHub run id: `{result['github_run_id'] or 'latest'}`",
            "### Latest crawler runs",
            run_table,
            "### Source listings",
            listing_table,
            "### Campaign cards",
            campaign_table,
            "### Warnings",
            warning_lines,
        ]
    )


def write_summary(markdown: str) -> None:
    summary_path = env_value("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(markdown)
        summary.write("\n")


def verify(result: dict[str, Any], min_successful_sources: int, min_active_campaigns: int) -> list[str]:
    failures: list[str] = []
    successful_sources = [
        row
        for row in result["run_rows"]
        if row.get("status") == "ok" and int(row.get("upserted_count") or 0) > 0
    ]
    if len(successful_sources) < min_successful_sources:
        failures.append(f"Expected at least {min_successful_sources} successful source(s), got {len(successful_sources)}.")
    active_campaigns = result["campaign_metrics"]["active_count"]
    if active_campaigns < min_active_campaigns:
        failures.append(f"Expected at least {min_active_campaigns} active campaign card(s), got {active_campaigns}.")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Supabase crawl sync results.")
    parser.add_argument("--supabase-url")
    parser.add_argument("--supabase-key")
    parser.add_argument("--github-run-id", default=env_value("GITHUB_RUN_ID"))
    parser.add_argument("--min-successful-sources", type=int, default=1)
    parser.add_argument("--min-active-campaigns", type=int, default=1)
    args = parser.parse_args()

    client = build_client(args)
    run_rows = select_run_rows(client, args.github_run_id)
    source_metrics = source_listing_metrics(client)
    campaign_metrics = campaign_card_metrics(client)
    result = {
        "github_run_id": args.github_run_id,
        "run_rows": run_rows,
        "source_metrics": source_metrics,
        "campaign_metrics": campaign_metrics,
        "warnings": [],
    }
    result["warnings"] = build_warnings(run_rows, source_metrics, campaign_metrics)

    markdown = build_markdown(result)
    write_summary(markdown)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failures = verify(result, args.min_successful_sources, args.min_active_campaigns)
    if failures:
        for failure in failures:
            print(f"verification failed: {failure}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
