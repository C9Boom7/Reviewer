-- Apply in Supabase SQL Editor.
-- Keeps campaign_cards source_count/source_listings aligned with active source_listings only.

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
  count(sl.id)::integer as source_count,
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
left join public.source_listings sl on sl.id = csl.source_listing_id and sl.status = 'active'
left join public.sources s on s.id = sl.source_id
group by c.id;

update public.campaigns c
set status = 'closed'
where c.status = 'active'
  and not exists (
    select 1
    from public.campaign_source_listings csl
    join public.source_listings sl on sl.id = csl.source_listing_id
    where csl.campaign_id = c.id
      and sl.status = 'active'
  );
