from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CRAWLER_DIR = ROOT / "crawler"
sys.path.insert(0, str(CRAWLER_DIR))
sys.path.insert(0, str(ROOT))

from verify_supabase import build_markdown, build_warnings, coverage_cell, delta_cell, run_totals


class VerifySupabaseFormattingTest(unittest.TestCase):
    def test_coverage_cell_handles_counts_and_zero_total(self) -> None:
        self.assertEqual("9/10 (90.0%)", coverage_cell(9, 10))
        self.assertEqual("0/0 (n/a)", coverage_cell(0, 0))

    def test_delta_cell_formats_previous_comparison(self) -> None:
        self.assertEqual("+3", delta_cell(13, 10))
        self.assertEqual("-2", delta_cell(8, 10))
        self.assertEqual("0", delta_cell(10, 10))
        self.assertEqual("n/a", delta_cell(10, None))

    def test_run_totals_groups_statuses_and_counts(self) -> None:
        totals = run_totals(
            [
                {"status": "ok", "fetched_count": 20, "upserted_count": 20, "closed_count": 1, "error_count": 0},
                {"status": "empty_parse", "fetched_count": 0, "upserted_count": 0, "closed_count": 0, "error_count": 0},
                {"status": "blocked_by_robots", "fetched_count": 0, "upserted_count": 0, "closed_count": 0, "error_count": 1},
            ]
        )
        self.assertEqual(3, totals["sources"])
        self.assertEqual(1, totals["ok_sources"])
        self.assertEqual(1, totals["empty_parse_sources"])
        self.assertEqual(1, totals["blocked_sources"])
        self.assertEqual(1, totals["error_sources"])
        self.assertEqual(20, totals["fetched"])
        self.assertEqual(20, totals["upserted"])
        self.assertEqual(1, totals["closed"])

    def test_build_warnings_marks_empty_parse_without_failure_language(self) -> None:
        warnings = build_warnings(
            [{"status": "empty_parse", "sources": {"code": "reviewnote"}}],
            [],
            {"active_count": 0, "with_reward": 0, "without_active_sources": 0},
        )
        self.assertEqual(["reviewnote fetched the homepage but parsed 0 campaign cards."], warnings)

    def test_build_markdown_renders_dashboard_sections_and_deltas(self) -> None:
        markdown = build_markdown(
            {
                "github_run_id": "100",
                "previous_github_run_id": "99",
                "run_rows": [
                    {
                        "status": "ok",
                        "fetched_count": 20,
                        "upserted_count": 20,
                        "closed_count": 1,
                        "error_count": 0,
                        "error_message": None,
                        "sources": {"code": "reviewplace", "name": "리뷰플레이스"},
                    },
                    {
                        "status": "empty_parse",
                        "fetched_count": 0,
                        "upserted_count": 0,
                        "closed_count": 0,
                        "error_count": 0,
                        "error_message": "no campaign snippets matched parser",
                        "sources": {"code": "reviewnote", "name": "리뷰노트"},
                    },
                ],
                "previous_run_rows": [
                    {
                        "status": "ok",
                        "fetched_count": 18,
                        "upserted_count": 18,
                        "closed_count": 0,
                        "error_count": 0,
                    }
                ],
                "source_metrics": [
                    {
                        "code": "reviewplace",
                        "name": "리뷰플레이스",
                        "active_count": 20,
                        "removed_count": 2,
                        "with_image": 20,
                        "with_deadline": 18,
                        "with_reward": 20,
                        "with_location": 4,
                    }
                ],
                "campaign_metrics": {
                    "active_count": 19,
                    "without_active_sources": 0,
                    "with_image": 19,
                    "with_deadline": 17,
                    "with_reward": 19,
                    "with_location": 4,
                },
                "warnings": ["reviewnote fetched the homepage but parsed 0 campaign cards."],
            }
        )
        self.assertIn("## Supabase crawl operations dashboard", markdown)
        self.assertIn("Previous run id: `99`", markdown)
        self.assertIn("### Operation summary", markdown)
        self.assertIn("| fetched listings | 20 | +2 |", markdown)
        self.assertIn("[WARN] empty_parse", markdown)
        self.assertIn("20/20 (100.0%)", markdown)
        self.assertIn("reviewnote fetched the homepage but parsed 0 campaign cards.", markdown)


if __name__ == "__main__":
    unittest.main()
