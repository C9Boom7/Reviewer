# 체험단 소스 선정 및 크롤링 정책

조사 기준일: 2026-06-27.

공개된 실제 사용자 수나 트래픽 순위는 사이트별로 일관되게 공개되어 있지 않다. 따라서 `rank_overall`은 공개 인지도, 검색 노출, 캠페인 범위, 사이트 규모, 크롤링 가능성을 함께 본 실무 우선순위다. 실제 자동 수집 여부는 별도의 `crawl_policy`로 판단한다.

## Market Top 후보

| 순위 | 소스 | URL | 판단 | MVP 자동 수집 |
|---:|---|---|---|---|
| 1 | 레뷰 REVU | https://www.revu.net/ | 대표급 인지도. Angular 앱이라 초기 HTML에 캠페인 카드가 거의 없고 API/렌더링 분석 필요 | 비활성 |
| 2 | 리뷰노트 | https://www.reviewnote.co.kr/ | 홈 HTML에 캠페인 카드가 노출되고 카테고리 폭이 넓음 | 홈 화면 snippet만 활성 |
| 3 | 디너의여왕 | https://dinnerqueen.net/ | 맛집/지역 체험단 인지도 높고 robots는 일반 허용 | 현재 환경에서 TLS/body fetch 불안정, 비활성 |
| 4 | 강남맛집 체험단 | https://xn--939au0g4vj8sq.net/ | 서버 HTML에 인기/마감 캠페인 카드 노출 | 홈 화면 snippet 활성 |
| 5 | 리뷰플레이스 | https://www.reviewplace.co.kr/ | 제품/지역/기자단/구매평 등 범위 넓음 | 홈 화면 snippet 활성 |

## MVP Active Crawl Set

robots와 초기 HTML 접근성을 기준으로 1차 샘플 크롤러는 아래 5개만 활성화한다.

| 우선순위 | 소스 | 수집 URL | 수집 방식 | 주의 |
|---:|---|---|---|---|
| 10 | 리뷰노트 | `/` | 홈페이지에 이미 렌더링된 `/campaigns/{id}` 카드 텍스트만 추출 | `robots.txt`가 `/campaigns/`를 차단하므로 상세/목록 fetch 금지 |
| 20 | 강남맛집 체험단 | `/` | 홈페이지의 `/cp/?id=` 카드 텍스트 추출 | 상세 확장은 robots 재확인 후 진행 |
| 30 | 링블 | `/` | 홈페이지의 `detail.php?number=` 카드 텍스트 추출 | `detail.php` fetch 금지 |
| 40 | 리뷰플레이스 | `/` | 홈페이지의 `/pr/?id=` 카드 텍스트 추출 | `/pr` fetch 금지 |
| 50 | 티블 | `/` | 홈페이지의 `view.php?cp_id=` 카드 텍스트 추출 | `view.php`, `category.php` fetch 금지 |

## 운영 원칙

- 상세 페이지를 자동으로 열기 전에 반드시 `robots.txt`와 사이트 약관을 다시 확인한다.
- robots에서 차단된 경로는 DB에 링크로 저장할 수는 있어도 크롤러가 직접 요청하지 않는다.
- 최초 MVP는 각 사이트 홈 1회 요청으로 끝나는 `homepage_only_no_detail_fetch` 모드만 사용한다.
- 수집 주기는 모든 사이트 공통 10분이 아니라 소스별로 둔다. MVP 기본값은 120분이며, 안정화 후 핵심 소스만 30~60분으로 줄인다.
- GitHub Actions cron은 정각을 피한다. 예: `17 * * * *`, `47 */2 * * *`.
- 실패한 소스는 즉시 재시도하지 않고 다음 run으로 넘긴다. 3회 이상 실패하면 `sources.is_active=false` 후보로 본다.

## 확인한 robots URL

- 레뷰: https://www.revu.net/robots.txt
- 리뷰노트: https://www.reviewnote.co.kr/robots.txt
- 디너의여왕: https://dinnerqueen.net/robots.txt
- 강남맛집 체험단: https://xn--939au0g4vj8sq.net/robots.txt
- 리뷰플레이스: https://www.reviewplace.co.kr/robots.txt
- 링블: https://www.ringble.co.kr/robots.txt
- 티블: https://www.tble.kr/robots.txt
