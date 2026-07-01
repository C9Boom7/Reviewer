from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CRAWLER_DIR = ROOT / "crawler"
sys.path.insert(0, str(CRAWLER_DIR))
sys.path.insert(0, str(ROOT))

import crawl_sample
from parsers import PARSERS, extract_campaigns


def make_source(
    code: str,
    name: str,
    target_url: str,
    robots_url: str,
    parser: str,
    allowed_link_patterns: list[str],
) -> crawl_sample.Source:
    return crawl_sample.Source(
        code=code,
        name=name,
        target_url=target_url,
        robots_url=robots_url,
        active=True,
        parser=parser,
        allowed_link_patterns=allowed_link_patterns,
        detail_fetch=False,
        policy_note="test fixture",
    )


SOURCES = {
    "dinnerqueen": make_source(
        "dinnerqueen",
        "디너의여왕",
        "https://dinnerqueen.net/taste",
        "https://dinnerqueen.net/robots.txt",
        "dinnerqueen_homepage",
        ["/taste/"],
    ),
    "reviewnote": make_source(
        "reviewnote",
        "리뷰노트",
        "https://www.reviewnote.co.kr/",
        "https://www.reviewnote.co.kr/robots.txt",
        "reviewnote_homepage",
        ["/campaigns/"],
    ),
    "ringble": make_source(
        "ringble",
        "링블",
        "https://www.ringble.co.kr/",
        "https://www.ringble.co.kr/robots.txt",
        "ringble_homepage",
        ["detail.php?number="],
    ),
    "reviewplace": make_source(
        "reviewplace",
        "리뷰플레이스",
        "https://www.reviewplace.co.kr/",
        "https://www.reviewplace.co.kr/robots.txt",
        "reviewplace_homepage",
        ["/pr/?id="],
    ),
    "gangnammatzip": make_source(
        "gangnammatzip",
        "강남맛집 체험단",
        "https://xn--939au0g4vj8sq.net/",
        "https://xn--939au0g4vj8sq.net/robots.txt",
        "gangnammatzip_homepage",
        ["/cp/?id="],
    ),
    "tble": make_source(
        "tble",
        "티블",
        "https://tble.kr/",
        "https://www.tble.kr/robots.txt",
        "tble_homepage",
        ["view.php?cp_id="],
    ),
    "seoulouba": make_source(
        "seoulouba",
        "서울오빠",
        "https://www.seoulouba.co.kr/",
        "https://www.seoulouba.co.kr/robots.txt",
        "seoulouba_homepage",
        ["campaign/?c="],
    ),
    "modublog": make_source(
        "modublog",
        "모블",
        "https://www.modublog.co.kr/",
        "https://www.modublog.co.kr/robots.txt",
        "modublog_homepage",
        ["/product/"],
    ),
}


class ParserRegistryTest(unittest.TestCase):
    def test_configured_sources_have_parser(self) -> None:
        sources = crawl_sample.load_sources(ROOT / "crawler" / "sources.json")
        self.assertEqual(10, len(sources))
        for source in sources:
            if not source.active:
                continue
            self.assertIn(source.code, PARSERS)
            self.assertTrue(source.parser.endswith("_homepage"))


class HomepageParserTest(unittest.TestCase):
    def assert_single_item(
        self,
        source_code: str,
        html: str,
        external_id: str,
        title: str,
        reward: str | None,
    ) -> dict:
        items = extract_campaigns(SOURCES[source_code], html, limit=3)
        self.assertEqual(1, len(items), items)
        item = items[0]
        self.assertEqual(source_code, item["source_code"])
        self.assertEqual(external_id, item["external_id"])
        self.assertEqual(title, item["title"])
        self.assertEqual(reward, item["reward_summary"])
        self.assertTrue(item["dedup_key"])
        self.assertTrue(item["content_hash"])
        return item

    def test_reviewnote_parser_extracts_card_fields(self) -> None:
        item = self.assert_single_item(
            "reviewnote",
            """
            <div class="relative pl-[2.5px]">
              <a href="/campaigns/123?utm_source=test">
                <img src="/images/mochi.jpg">
                <span class="text-16m">[서울/맛집] 모찌도넛</span>
                <span class="text-14r">2만원 쿠폰</span>
                <span>D-3</span>
              </a>
            </div>
            """,
            "123",
            "모찌도넛",
            "2만원 쿠폰",
        )
        self.assertEqual("서울", item["location_text"])
        self.assertIn("visit", item["parsed_payload"]["benefit_tags"])
        self.assertTrue(item["application_deadline_at"])
        self.assertEqual("https://www.reviewnote.co.kr/images/mochi.jpg", item["image_url"])

    def test_ringble_parser_extracts_table_card_fields(self) -> None:
        item = self.assert_single_item(
            "ringble",
            """
            <td width='240' class='store_list_wrap'>
              <a href='detail.php?number=456&utm_campaign=x'>
                <img src='/upload/vacuum.jpg'>
                <span class='list_title'>차량용 청소기</span>
                <td style='color:#aaaaaa'>제품 제공</td>
                <span>D-1</span>
              </a>
            </td>
            """,
            "456",
            "차량용 청소기",
            "제품 제공",
        )
        self.assertIn("delivery", item["parsed_payload"]["benefit_tags"])
        self.assertTrue(item["application_deadline_at"])
        self.assertEqual("https://www.ringble.co.kr/upload/vacuum.jpg", item["image_url"])

    def test_reviewplace_parser_extracts_card_fields(self) -> None:
        item = self.assert_single_item(
            "reviewplace",
            """
            <a href="/pr/?id=789">
              <img src="/files/donut.png">
              <div class="tit">글루텐프리 도넛</div>
              <div class="txt">제품 제공</div>
              <span>오늘마감</span>
            </a>
            """,
            "789",
            "글루텐프리 도넛",
            "제품 제공",
        )
        self.assertEqual("오늘마감", item["parsed_payload"]["deadline_text"])
        self.assertTrue(item["application_deadline_at"])

    def test_gangnammatzip_parser_extracts_url_id_with_common_fields(self) -> None:
        item = self.assert_single_item(
            "gangnammatzip",
            '<a href="/cp/?id=321">[서울/맛집] 파스타 방문 D-2</a>',
            "321",
            "파스타 방문",
            None,
        )
        self.assertEqual("서울", item["location_text"])
        self.assertIn("visit", item["parsed_payload"]["benefit_tags"])

    def test_tble_parser_extracts_card_fields(self) -> None:
        item = self.assert_single_item(
            "tble",
            """
            <a href="view.php?cp_id=654">
              <div class="t2">인스타 릴스 캠페인</div>
              <div class="t3">5만원 상당</div>
              <span>D-4</span>
            </a>
            """,
            "654",
            "인스타 릴스 캠페인",
            "5만원 상당",
        )
        self.assertIn("instagram", item["parsed_payload"]["platform_tags"])
        self.assertTrue(item["application_deadline_at"])

    def test_dinnerqueen_parser_skips_category_links(self) -> None:
        items = extract_campaigns(
            SOURCES["dinnerqueen"],
            """
            <a href="/taste?ct=%EB%A7%9B%EC%A7%91">맛집</a>
            <a href="/taste/1431298">메인 캐러셀 링크</a>
            <a href="/taste/1431299">캐러셀 링크</a>
            <div class="qz-col pc2 lt3 tb2 mb2 mr-b7 mb-mr-b5">
              <div class="qz-dq-card qz-button fluid hover">
                <a class="qz-dq-card__link" href="/taste/1420173" title="[랜덤픽] 시코 미니 선풍기 신청하기">
                  <div class="qz-dq-card__link__img">
                    <img src="/uploads/fan.jpg" alt="[랜덤픽] 시코 미니 선풍기">
                  </div>
                </a>
                <div class="qz-dq-card__text">
                  <div class="layer-primary"><p><strong>D-6</strong></p></div>
                  <div><p><strong>배송</strong></p></div>
                  <p class="qz-body2-kr--line ellipsis color-title">
                    <span>[랜덤픽] 시코 미니 선풍기</span>
                  </p>
                  <p class="apply_badge">
                    <span><span class="color-subtitle">신청 367</span><span> / 모집 1</span></span>
                  </p>
                </div>
              </div>
            </div>
            """,
            limit=3,
        )
        self.assertEqual(1, len(items), items)
        self.assertEqual("1420173", items[0]["external_id"])
        self.assertEqual("시코 미니 선풍기", items[0]["title"])
        self.assertIsNone(items[0]["reward_summary"])
        self.assertTrue(items[0]["application_deadline_at"])
        self.assertEqual(367, items[0]["parsed_payload"]["applicant_count"])
        self.assertEqual(1, items[0]["parsed_payload"]["recruit_count"])
        self.assertIn("delivery", items[0]["parsed_payload"]["benefit_tags"])
        self.assertEqual("https://dinnerqueen.net/uploads/fan.jpg", items[0]["image_url"])

    def test_seoulouba_parser_extracts_homepage_campaign_links(self) -> None:
        item = self.assert_single_item(
            "seoulouba",
            """
            <a href="https://www.seoulouba.co.kr/campaign/?cat=377">방문형</a>
            <li class="campaign_content">
              <div class="load_campaign">
                <a href="https://www.seoulouba.co.kr/campaign/?c=415627" class="tum_img">
                  <img src="/data/file/campaign/thumb.jpg">
                </a>
              </div>
              <div class="load_info">
                <div class="com_icon"><div class="icon_tag"><span>배송형</span></div></div>
                <div class="t_ttl">
                  <a href="https://www.seoulouba.co.kr/campaign/?c=415627">
                    <strong class="s_campaign_title">[배송형] 은혜로운팜</strong>
                  </a>
                </div>
                <div class="t_basic">
                  <span class="basic_blue">대극천 복숭아 500g 제공</span>
                </div>
                <div class="campaign_day_people">
                  <div class="d_day"><span>D-3</span></div>
                  <div class="recruit"><span>신청 285 <span class="span_gray">/ 모집 5</span></span></div>
                </div>
              </div>
            </li>
            """,
            "415627",
            "은혜로운팜",
            "대극천 복숭아 500g 제공",
        )
        self.assertIn("delivery", item["parsed_payload"]["benefit_tags"])
        self.assertTrue(item["application_deadline_at"])
        self.assertEqual(285, item["parsed_payload"]["applicant_count"])
        self.assertEqual(5, item["parsed_payload"]["recruit_count"])
        self.assertEqual("https://www.seoulouba.co.kr/data/file/campaign/thumb.jpg", item["image_url"])

    def test_modublog_parser_extracts_product_cards(self) -> None:
        items = extract_campaigns(
            SOURCES["modublog"],
            """
            <a href="https://www.modublog.co.kr/product/?up=1">확률UP</a>
            <a href="https://www.modublog.co.kr/product/48716">
              휴대용 블루투스 15w 스피커 [방수 블루투스 스피커/쿠팡리뷰] 하리보
            </a>
            """,
            limit=3,
        )
        self.assertEqual(1, len(items), items)
        self.assertEqual("48716", items[0]["external_id"])
        self.assertEqual("휴대용 블루투스 15w 스피커 하리보", items[0]["title"])
        self.assertIn("purchase_review", items[0]["parsed_payload"]["benefit_tags"])


class CrawlSourceStatusTest(unittest.TestCase):
    def test_robots_allows_exact_home_with_dollar_rule(self) -> None:
        robots_text = """
        User-agent: *
        Disallow: /
        Allow: /$
        """
        self.assertTrue(crawl_sample.robots_text_allows(robots_text, "https://www.example.com/"))
        self.assertFalse(crawl_sample.robots_text_allows(robots_text, "https://www.example.com/campaign/?c=1"))

    def test_robots_disallows_query_patterns(self) -> None:
        robots_text = """
        User-agent: *
        Allow: /
        Disallow: /*?*
        """
        self.assertTrue(crawl_sample.robots_text_allows(robots_text, "https://example.com/taste"))
        self.assertFalse(crawl_sample.robots_text_allows(robots_text, "https://example.com/taste?order=hot"))

    def test_robots_keeps_consecutive_user_agents_in_one_group(self) -> None:
        robots_text = """
        User-agent: Googlebot
        User-agent: *
        Disallow: /private/
        """
        self.assertTrue(crawl_sample.robots_text_allows(robots_text, "https://example.com/public/1"))
        self.assertFalse(crawl_sample.robots_text_allows(robots_text, "https://example.com/private/1"))

    def test_empty_parse_status_when_homepage_fetch_succeeds_with_no_items(self) -> None:
        original_robots_allows = crawl_sample.robots_allows
        original_fetch_html = crawl_sample.fetch_html
        try:
            crawl_sample.robots_allows = lambda robots_url, target_url: True
            crawl_sample.fetch_html = lambda url: '<html><a href="/not-a-campaign">noop</a></html>'
            result = crawl_sample.crawl_source(SOURCES["reviewnote"], limit=3)
        finally:
            crawl_sample.robots_allows = original_robots_allows
            crawl_sample.fetch_html = original_fetch_html

        self.assertEqual("empty_parse", result["status"])
        self.assertEqual([], result["items"])
        self.assertEqual("no campaign snippets matched parser reviewnote_homepage", result["reason"])


if __name__ == "__main__":
    unittest.main()
