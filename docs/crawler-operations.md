# 크롤러 운영안

## 실행 모드

초기 크롤러는 `homepage_only_no_detail_fetch` 모드다.

- 각 소스의 허용된 홈페이지 URL만 요청한다.
- 홈페이지 HTML 안에 이미 노출된 캠페인 카드 snippet만 추출한다.
- 정보가 여러 anchor/sibling에 나뉜 소스는 캠페인 URL 기준 카드 컨테이너를 묶어서 추출한다.
- robots에서 막힌 상세/목록 경로는 요청하지 않는다.
- 소스 사이에 sleep을 두고 순차 실행한다.

현재 homepage snippet에서 추출하는 주요 필드:

- 카드 이미지 URL
- 캠페인 제목
- 제공/혜택 요약
- 지역/재택 표시
- 마감일 후보 (`오늘마감`, `D - N`, `N일 남음`)
- 신청/모집 인원
- 출처별 카테고리, 채널 태그, 혜택 태그

## 파서 구조

크롤러 실행 흐름은 `crawler/crawl_sample.py`가 담당하고, 사이트별 HTML 해석은 `crawler/parsers/` 아래로 분리한다.

- `crawler/parsers/common.py`: homepage anchor 기반 공통 추출, 이미지/마감/태그/해시 생성.
- `crawler/parsers/reviewnote.py`: 리뷰노트 카드 컨테이너, 제목/보상 class, campaign id 추출.
- `crawler/parsers/ringble.py`: 링블 table 카드 컨테이너, 제목/보상 table cell, number 추출.
- `crawler/parsers/reviewplace.py`: 리뷰플레이스 제목/보상 class, id 추출.
- `crawler/parsers/gangnammatzip.py`: 강남맛집 URL id 추출. robots 차단 시 parser는 호출되지 않는다.
- `crawler/parsers/tble.py`: 티블 제목/보상 class, cp_id 추출. robots 차단 시 parser는 호출되지 않는다.

새 소스를 추가할 때는 `crawler/sources.json`에 `parser` 값을 명시하고, 필요한 경우 `crawler/parsers/{source}.py`에 source별 hook만 추가한다. fetch, robots 확인, JSON payload 조립은 `crawl_sample.py`에 유지한다.

샘플 실행:

```bash
python3 crawler/crawl_sample.py --limit-per-source 12 --sleep 1.5
```

출력:

```text
data/samples/campaigns.sample.json
```

parser 회귀 테스트:

```bash
python3 -m unittest discover -s crawler/tests
```

GitHub Actions는 실제 크롤링 전에 이 테스트를 먼저 실행한다. 사이트별 HTML 해석 규칙이 깨지면 대상 사이트에 요청하거나 Supabase에 반영하기 전에 job이 중단된다.

## GitHub Actions 주기

MVP 권장값:

- 기본 수집: 2시간마다.
- 안정화 후 핵심 소스만 30~60분.
- 전체 재검증: 하루 1회.
- 10분 주기는 피한다. 대상 서버 부하와 GitHub Actions 지연/drop 리스크가 커진다.

cron 예시:

```yaml
schedule:
  - cron: "17 */2 * * *"
```

정각은 피한다. GitHub Actions scheduled workflow는 고부하 시간에 지연되거나 drop될 수 있으므로, 데이터 freshness는 best-effort로 봐야 한다.

## Supabase 연동 방향

GitHub Secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

최초 1회 Supabase SQL Editor에서 아래 파일을 순서대로 실행한다.

1. `supabase/schema.sql`
2. `supabase/seed_sources.sql`

스키마 변경 패치는 `supabase/migrations/` 아래 SQL 파일을 Supabase SQL Editor에서 실행한다.

Actions job 흐름:

1. checkout
2. Python setup
3. `python3 crawler/crawl_sample.py --out data/samples/campaigns.latest.json`
4. `python3 crawler/sync_supabase.py --input data/samples/campaigns.latest.json`
5. `python3 crawler/verify_supabase.py`로 최신 run과 Supabase 반영 지표 검증
6. 성공/실패와 관계없이 artifact로 `campaigns.latest.json` 업로드

현재 workflow는 `.github/workflows/crawl-campaigns.yml`에 있다.
검증 결과는 GitHub Actions run의 Summary에서 `Supabase crawl verification` 표로 확인한다.

로컬에서 Supabase 쓰기 없이 매핑만 확인하려면:

```bash
python3 crawler/sync_supabase.py --dry-run --input data/samples/campaigns.sample.json
```

Supabase secret이 있는 환경에서는 아래처럼 반영 상태만 직접 확인할 수 있다.

```bash
python3 crawler/verify_supabase.py
```

실제 Supabase 쓰기는 GitHub Actions에서 service role key로만 수행한다.

## 차단/실패 정책

- `robots.txt`가 대상 URL을 막으면 `blocked_by_robots`로 기록하고 요청하지 않는다.
- robots 차단은 기술적으로 항상 불가능하다는 뜻은 아니지만, 이 프로젝트에서는 우회하지 않는다. 허용 URL, 공식 API/RSS, 제휴, 수동 등록 같은 안전한 경로만 사용한다.
- `blocked_by_robots` source는 자동 비활성화하지 않고 `sources.crawl_policy.status=blocked_by_robots_candidate`로 기록한다.
- 1회 실패: 다음 run에서 재시도.
- 3회 연속 실패: `sources.is_active=false` 전환 후보.
- HTML 구조 변경으로 파싱 결과가 0건이면 실패가 아니라 `empty_parse`로 분리한다.
- 대량 상세 fetch가 필요해지면 사이트별 허가 또는 제휴/API를 먼저 검토한다.

## Stale 정리 정책

- 최신 run에서 `status=ok`이고 `item_count > 0`인 source만 stale 정리 대상이다.
- 해당 source의 기존 `active` listing 중 이번 run에 다시 보이지 않은 항목은 `removed`로 바꾼다.
- 연결된 active listing이 하나도 남지 않은 campaign은 `closed`로 바꾼다.
- 매 sync 후 전체 active campaign을 다시 검사해 active listing이 없는 orphan campaign도 `closed`로 바꾼다.
- `blocked_by_robots`, `error`, `skipped`, 0건 parse source는 stale 정리를 하지 않는다.
- source별 제거 수는 `crawler_runs.closed_count`에 기록한다.

## 현재 적용 필요 SQL 패치

기존 Supabase DB에는 아래 파일을 SQL Editor에서 1회 실행한다.

```text
supabase/migrations/20260701_campaign_cards_active_sources.sql
```

이 패치는 `campaign_cards.source_count`와 `source_listings` JSON을 active listing 기준으로 바꾸고,
active listing이 없는 campaign을 즉시 `closed` 처리한다.
