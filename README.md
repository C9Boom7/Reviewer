# Reviewer

체험단 캠페인 정보를 여러 사이트에서 수집해 한 화면에 모아보는 MVP입니다. GitHub Actions가 주기적으로 Python 크롤러를 실행하고, Supabase에 저장된 캠페인 카드를 React 프론트에서 보여줍니다.

## 구성

- `crawler/`: 체험단 사이트 수집 및 Supabase 동기화 스크립트
- `supabase/`: 테이블, 뷰, RLS 정책 SQL
- `src/`: React + Vite 프론트엔드
- `.github/workflows/`: 주기 수집 GitHub Action

## Frontend

```bash
pnpm install
cp .env.example .env.local
pnpm run dev
```

`.env.local`에는 브라우저에 노출 가능한 Supabase 키만 넣습니다.

```bash
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-or-publishable-key
```

서비스롤 키는 프론트엔드에 넣지 않습니다. GitHub Actions의 크롤러 동기화에만 사용합니다.

## Build

```bash
pnpm run build
```

Supabase env가 없으면 `public/data/campaigns.sample.json` 샘플 데이터로 동작합니다.

## Crawler

사이트별 parser 회귀 테스트:

```bash
python3 -m unittest discover -s crawler/tests
```

실제 수집은 GitHub Actions에서 주기적으로 실행합니다. 로컬에서 수집 로직만 확인할 때는 대상 사이트에 요청이 나가므로 필요한 경우에만 실행합니다.

## Deploy

`main` 브랜치에 프론트 변경이 push되면 GitHub Pages 배포 워크플로가 실행됩니다.

필요한 GitHub Secret:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

`SUPABASE_ANON_KEY`가 없으면 배포된 화면도 샘플 데이터로 동작합니다.
