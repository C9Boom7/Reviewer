create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create type public.campaign_status as enum (
  'draft',
  'active',
  'closed',
  'archived'
);

create type public.listing_status as enum (
  'seen',
  'active',
  'closed',
  'removed',
  'error'
);

create table public.sources (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  homepage_url text not null,
  robots_url text,
  rank_overall integer,
  crawl_priority integer,
  is_active boolean not null default true,
  crawl_interval_minutes integer not null default 120,
  crawl_policy jsonb not null default '{}'::jsonb,
  crawler_config jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.campaigns (
  id uuid primary key default gen_random_uuid(),
  canonical_key text not null unique,
  title text not null,
  brand_name text,
  summary text,
  category text,
  status public.campaign_status not null default 'active',
  starts_at timestamptz,
  ends_at timestamptz,
  application_deadline_at timestamptz,
  reward_summary text,
  location_text text,
  target_text text,
  primary_image_url text,
  canonical_url text,
  platform_tags text[] not null default '{}',
  region_tags text[] not null default '{}',
  benefit_tags text[] not null default '{}',
  details jsonb not null default '{}'::jsonb,
  dedup_meta jsonb not null default '{}'::jsonb,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.source_listings (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id) on delete cascade,
  external_id text,
  source_url text not null,
  normalized_url text not null,
  title text not null,
  brand_name text,
  status public.listing_status not null default 'active',
  starts_at timestamptz,
  ends_at timestamptz,
  application_deadline_at timestamptz,
  image_url text,
  reward_summary text,
  location_text text,
  content_hash text,
  dedup_key text not null,
  raw_payload jsonb not null default '{}'::jsonb,
  parsed_payload jsonb not null default '{}'::jsonb,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  last_crawled_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint source_listings_external_unique unique (source_id, external_id),
  constraint source_listings_url_unique unique (source_id, normalized_url),
  constraint source_listings_dedup_unique unique (source_id, dedup_key)
);

create table public.campaign_source_listings (
  campaign_id uuid not null references public.campaigns(id) on delete cascade,
  source_listing_id uuid not null references public.source_listings(id) on delete cascade,
  is_primary boolean not null default false,
  match_confidence numeric(4, 3),
  match_reason text,
  created_at timestamptz not null default now(),
  primary key (campaign_id, source_listing_id),
  unique (source_listing_id)
);

create table public.crawler_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references public.sources(id) on delete set null,
  github_run_id text,
  git_sha text,
  status text not null default 'running',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  fetched_count integer not null default 0,
  upserted_count integer not null default 0,
  closed_count integer not null default 0,
  error_count integer not null default 0,
  error_message text,
  meta jsonb not null default '{}'::jsonb
);

create table public.raw_ingest_events (
  id bigserial primary key,
  crawler_run_id uuid references public.crawler_runs(id) on delete cascade,
  source_id uuid references public.sources(id) on delete cascade,
  source_url text,
  event_type text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger sources_set_updated_at
before update on public.sources
for each row execute function public.set_updated_at();

create trigger campaigns_set_updated_at
before update on public.campaigns
for each row execute function public.set_updated_at();

create trigger source_listings_set_updated_at
before update on public.source_listings
for each row execute function public.set_updated_at();

create index sources_active_priority_idx
  on public.sources (is_active, crawl_priority);

create index campaigns_status_deadline_idx
  on public.campaigns (status, application_deadline_at desc);

create index campaigns_last_seen_idx
  on public.campaigns (last_seen_at desc);

create index campaigns_category_idx
  on public.campaigns (category);

create index campaigns_platform_tags_gin_idx
  on public.campaigns using gin (platform_tags);

create index campaigns_region_tags_gin_idx
  on public.campaigns using gin (region_tags);

create index campaigns_benefit_tags_gin_idx
  on public.campaigns using gin (benefit_tags);

create index campaigns_details_gin_idx
  on public.campaigns using gin (details jsonb_path_ops);

create index campaigns_title_trgm_idx
  on public.campaigns using gin (title gin_trgm_ops);

create index campaigns_brand_trgm_idx
  on public.campaigns using gin (brand_name gin_trgm_ops);

create index source_listings_source_status_idx
  on public.source_listings (source_id, status);

create index source_listings_last_crawled_idx
  on public.source_listings (last_crawled_at desc);

create index source_listings_content_hash_idx
  on public.source_listings (content_hash);

create index source_listings_title_trgm_idx
  on public.source_listings using gin (title gin_trgm_ops);

create index campaign_source_listings_campaign_idx
  on public.campaign_source_listings (campaign_id);

create index crawler_runs_source_started_idx
  on public.crawler_runs (source_id, started_at desc);

create or replace view public.campaign_cards
with (security_invoker = true) as
select
  c.id,
  c.title,
  c.brand_name,
  c.summary,
  c.category,
  c.status,
  c.application_deadline_at,
  c.reward_summary,
  c.location_text,
  c.primary_image_url,
  c.canonical_url,
  c.platform_tags,
  c.region_tags,
  c.benefit_tags,
  c.first_seen_at,
  c.last_seen_at,
  count(csl.source_listing_id)::integer as source_count,
  coalesce(
    jsonb_agg(
      jsonb_build_object(
        'source_code', s.code,
        'source_name', s.name,
        'source_url', sl.source_url,
        'external_id', sl.external_id,
        'status', sl.status
      )
      order by csl.is_primary desc, s.crawl_priority nulls last
    ) filter (where sl.id is not null),
    '[]'::jsonb
  ) as source_listings
from public.campaigns c
left join public.campaign_source_listings csl on csl.campaign_id = c.id
left join public.source_listings sl on sl.id = csl.source_listing_id
left join public.sources s on s.id = sl.source_id
group by c.id;

alter table public.sources enable row level security;
alter table public.campaigns enable row level security;
alter table public.source_listings enable row level security;
alter table public.campaign_source_listings enable row level security;
alter table public.crawler_runs enable row level security;
alter table public.raw_ingest_events enable row level security;

create policy "public can read active sources"
on public.sources
for select
using (is_active = true);

create policy "public can read active campaigns"
on public.campaigns
for select
using (status = 'active');

create policy "public can read active source listings"
on public.source_listings
for select
using (status = 'active');

create policy "public can read campaign listing links"
on public.campaign_source_listings
for select
using (true);
