# Frontend MVP

Reviewer frontend is a React + Vite single page app. It reads live campaign cards from the Supabase REST API when browser-safe env vars are present, and falls back to bundled sample data during local development.

## Local setup

```bash
npm install
cp .env.example .env.local
npm run dev
```

Set these values in `.env.local`:

```bash
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-or-publishable-key
```

Use the Supabase anon/publishable key only. Do not expose `SUPABASE_SERVICE_ROLE_KEY` to the frontend.

## MVP scope

- Campaign cards from `public.campaign_cards`
- Search by title, brand, reward, location, tags, and source name
- Filters for channel, campaign type, region, and source
- Detail panel with source links for the "representative card + multiple sources" model
- Bundled sample fallback from `public/data/campaigns.sample.json`
