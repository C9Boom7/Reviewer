# Supabase 데이터 모델

MVP는 서버 비용을 줄이기 위해 Supabase Postgres를 원천 DB로 사용하고, GitHub Actions Python 크롤러가 service role key로 upsert한다. React 앱은 Supabase anon key로 public read만 수행한다.

## 핵심 테이블

- `sources`: 체험단 플랫폼 메타데이터와 크롤링 정책.
- `source_listings`: 각 사이트에서 발견한 원본 캠페인 카드.
- `campaigns`: 화면에 보여줄 대표 캠페인 카드.
- `campaign_source_listings`: 대표 카드와 여러 원본 listing 연결.
- `crawler_runs`: GitHub Actions 수집 실행 이력.
- `raw_ingest_events`: 디버깅용 원본 이벤트. 저장 공간을 아끼려면 운영에서 비활성화 가능.

## 대표 카드 + 여러 출처

`source_listings`는 원본 사이트 단위로 안정적으로 upsert한다. 같은 캠페인이 여러 사이트에 있거나 제목이 유사한 경우, dedup 로직이 하나의 `campaigns` row를 만들고 `campaign_source_listings`로 연결한다.

```text
campaigns 1 ── n campaign_source_listings n ── 1 source_listings n ── 1 sources
```

이 구조의 장점은 다음과 같다.

- 크롤러는 원본 출처별 변경을 잃지 않는다.
- 대표 카드 병합 로직이 틀려도 원본 listing을 되돌릴 수 있다.
- 프론트는 `campaign_cards` view 하나만 읽으면 대표 카드와 출처 목록을 함께 받을 수 있다.

## Upsert 키

`source_listings`는 출처마다 안정적인 키가 다르므로 세 가지 unique key를 둔다.

- `(source_id, external_id)`: 사이트 내부 ID가 있는 경우 최우선.
- `(source_id, normalized_url)`: URL이 안정적인 경우.
- `(source_id, dedup_key)`: 외부 ID/URL이 불안정한 경우 fallback.

Python crawler는 보통 아래 순서로 처리한다.

1. `crawler_runs` insert.
2. `source_listings` upsert.
3. 기존 `campaigns` 후보 조회.
4. 유사도가 높으면 기존 대표 카드에 연결.
5. 후보가 없으면 새 `campaigns` 생성.
6. `campaign_source_listings` upsert.
7. `crawler_runs` finish update.

## Dedup 기준

초기 dedup은 보수적으로 한다. 잘못 병합하는 것보다 중복 카드가 잠깐 보이는 편이 안전하다.

- 강한 매칭: 같은 외부 URL, 같은 canonical URL, 같은 source listing.
- 중간 매칭: brand/title normalized 값이 유사하고 마감일 또는 reward가 유사.
- 약한 매칭: 제목만 비슷한 경우. 자동 병합하지 않고 후보로만 남긴다.

`campaigns.canonical_key`는 아래 형태의 hash로 시작한다.

```text
sha256(normalized_brand + "|" + normalized_title + "|" + deadline_date_or_empty)
```

## JSONB 사용 기준

자주 필터링하는 값은 컬럼으로 둔다.

- 컬럼: `status`, `title`, `brand_name`, `category`, `application_deadline_at`, `platform_tags`, `region_tags`, `benefit_tags`
- JSONB: `raw_payload`, `parsed_payload`, `details`, `dedup_meta`, `crawler_config`, `crawl_policy`

Supabase 무료 플랜에서는 DB 용량과 인덱스를 아껴야 하므로 JSONB GIN index는 화면 필터에 실제로 필요한 필드부터 추가한다.

## RLS

MVP 정책은 단순하다.

- public/anon: active campaign/source/listing select만 허용.
- GitHub Actions crawler: service role key 사용. service role은 RLS를 우회하므로 GitHub Secrets에만 저장한다.
- 일반 사용자 쓰기: MVP에서는 없음.

추후 관심 캠페인, 알림, 로그인 기능이 필요하면 `auth.users` 기반으로 `profiles`, `campaign_follows`, `notification_subscriptions`를 추가한다. 이번 MVP에서는 관심 캠페인을 제외한다.

## 프론트 조회 예시

React 앱은 우선 `campaign_cards` view를 읽는다.

```sql
select *
from public.campaign_cards
where status = 'active'
order by application_deadline_at nulls last, last_seen_at desc
limit 50;
```

검색은 초기에는 title/brand trigram index를 사용하고, 데이터가 커지면 generated `tsvector`를 별도로 추가한다.
