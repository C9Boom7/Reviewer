# 체험단 소스 선정 및 크롤링 정책

조사 기준일: 2026-07-01.

공개된 실제 사용자 수나 트래픽 순위는 사이트별로 일관되게 공개되어 있지 않다. 따라서 `rank_overall`은 공개 인지도, 검색 노출, 캠페인 범위, 사이트 규모, 크롤링 가능성을 함께 본 실무 우선순위다. 실제 자동 수집 여부는 별도의 `crawl_policy`로 판단한다.

## Market Top 후보

| 순위 | 소스 | URL | 판단 | MVP 자동 수집 |
|---:|---|---|---|---|
| 1 | 레뷰 REVU | https://www.revu.net/ | 대표급 인지도. Angular 앱이라 초기 HTML에 캠페인 카드가 거의 없고 API/렌더링 분석 필요 | 비활성 |
| 2 | 리뷰노트 | https://www.reviewnote.co.kr/ | 홈 HTML에 캠페인 카드가 노출되고 카테고리 폭이 넓음 | 홈 화면 snippet만 활성 |
| 3 | 서울오빠 | https://www.seoulouba.co.kr/ | 홈 HTML에 캠페인 링크와 제목이 노출됨. robots는 홈만 허용 | 홈 화면 snippet만 활성 |
| 4 | 디너의여왕 | https://dinnerqueen.net/ | 맛집/지역 체험단 인지도 높고 `/taste` 공개 목록에 캠페인 링크 노출 | `/taste` snippet 활성 |
| 5 | 모블 | https://www.modublog.co.kr/ | 로컬 홈 HTML에는 제품 캠페인 카드가 보이나 GitHub Actions에서는 `empty_parse` | 후보 |
| 6 | 강남맛집 체험단 | https://xn--939au0g4vj8sq.net/ | 서버 HTML에 카드가 보이지만 GitHub Actions robots check에서 차단 | 비활성 |
| 7 | 리뷰플레이스 | https://www.reviewplace.co.kr/ | 제품/지역/기자단/구매평 등 범위 넓음 | 홈 화면 snippet 활성 |

## MVP Active Crawl Set

robots와 GitHub Actions 실행 결과를 기준으로 현재 크롤러는 아래 6개를 `summary_only`로 활성화한다.

| 우선순위 | 소스 | 수집 URL | 수집 방식 | 주의 |
|---:|---|---|---|---|
| 10 | 리뷰노트 | `/` | 홈페이지에 이미 렌더링된 `/campaigns/{id}` 카드 텍스트만 추출 | `robots.txt`가 `/campaigns/`를 차단하므로 상세/목록 fetch 금지 |
| 20 | 서울오빠 | `/` | 홈페이지에 이미 렌더링된 `campaign/?c=` 링크와 제목만 추출 | `robots.txt`가 홈만 허용하므로 목록/상세 fetch 금지 |
| 30 | 디너의여왕 | `/taste` | 공개 목록의 `/taste/{id}` 링크와 제목만 추출 | query-filter URL과 상세 fetch 금지 |
| 40 | 링블 | `/` | 홈페이지의 `detail.php?number=` 카드 텍스트 추출 | `detail.php` fetch 금지 |
| 50 | 리뷰플레이스 | `/` | 홈페이지의 `/pr/?id=` 카드 텍스트 추출 | `/pr` fetch 금지 |
| 60 | 티블 | `/` | 홈페이지의 `view.php?cp_id=` 카드 텍스트 추출 | `view.php`, `category.php` fetch 금지 |

## 보류 후보

| 소스 | 상태 | 이유 |
|---|---|---|
| 모블 | `candidate` | 로컬 HTML에서는 `/product/{id}` 카드가 보이나 GitHub Actions에서는 0건 parse. User-Agent, CDN, HTML 변형 여부 확인 필요 |
| 강남맛집 체험단 | `blocked` | GitHub Actions robots check에서 target URL 차단. 허용 경로 또는 제휴/공식 데이터 경로 필요 |
| 리뷰쉐어 | `blocked` | `/project/`가 robots에서 차단되고 홈에 캠페인 snippet이 없음 |

## 운영 원칙

- 상세 페이지를 자동으로 열기 전에 반드시 `robots.txt`와 사이트 약관을 다시 확인한다.
- robots에서 차단된 경로는 DB에 링크로 저장할 수는 있어도 크롤러가 직접 요청하지 않는다.
- 기본 수집은 각 사이트의 허용 URL 1회 요청으로 끝나는 `summary_only` 모드만 사용한다.
- 수집 주기는 모든 사이트 공통 10분이 아니라 소스별로 둔다. MVP 기본값은 120분이며, 안정화 후 핵심 소스만 30~60분으로 줄인다.
- GitHub Actions cron은 정각을 피한다. 예: `17 * * * *`, `47 */2 * * *`.
- 실패한 소스는 즉시 재시도하지 않고 다음 run으로 넘긴다. 3회 이상 실패하면 `sources.is_active=false` 후보로 본다.

## 확인한 robots URL

- 레뷰: https://www.revu.net/robots.txt
- 리뷰노트: https://www.reviewnote.co.kr/robots.txt
- 디너의여왕: https://dinnerqueen.net/robots.txt
- 서울오빠: https://www.seoulouba.co.kr/robots.txt
- 모블: https://www.modublog.co.kr/robots.txt
- 강남맛집 체험단: https://xn--939au0g4vj8sq.net/robots.txt
- 리뷰플레이스: https://www.reviewplace.co.kr/robots.txt
- 링블: https://www.ringble.co.kr/robots.txt
- 티블: https://www.tble.kr/robots.txt
- 리뷰쉐어: https://reviewshare.io/robots.txt
