import type { CampaignCard, SamplePayload } from "./types";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

type LoadResult = {
  campaigns: CampaignCard[];
  source: "supabase" | "sample";
  generatedAt: string | null;
  warning: string | null;
};

function activeOnly(card: CampaignCard): boolean {
  return card.status === "active";
}

function mapSampleCampaigns(payload: SamplePayload): CampaignCard[] {
  return payload.campaigns
    .filter((item) => item.status === "active")
    .map((item) => ({
      id: item.dedup_key || item.normalized_url,
      title: item.title,
      brand_name: item.brand_name ?? null,
      summary: item.reward_summary ?? null,
      category: null,
      status: item.status,
      application_deadline_at: item.application_deadline_at ?? null,
      reward_summary: item.reward_summary ?? null,
      location_text: item.location_text ?? null,
      primary_image_url: item.image_url ?? null,
      canonical_url: item.source_url,
      platform_tags: item.parsed_payload?.platform_tags ?? [],
      region_tags: item.parsed_payload?.region_tags ?? [],
      benefit_tags: item.parsed_payload?.benefit_tags ?? [],
      first_seen_at: payload.generated_at,
      last_seen_at: payload.generated_at,
      source_count: 1,
      source_listings: [
        {
          source_code: item.source_code,
          source_name: item.source_name,
          source_mode: "summary_only",
          crawl_policy_status: "crawlable",
          source_url: item.source_url,
          external_id: item.external_id ?? null,
          status: item.status,
        },
      ],
    }));
}

async function loadSample(reason: string | null = null): Promise<LoadResult> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/campaigns.sample.json`);
  if (!response.ok) {
    throw new Error(`Failed to load sample campaigns: ${response.status}`);
  }
  const payload = (await response.json()) as SamplePayload;
  return {
    campaigns: mapSampleCampaigns(payload),
    source: "sample",
    generatedAt: payload.generated_at,
    warning: reason,
  };
}

async function loadSupabase(): Promise<LoadResult> {
  if (!supabaseUrl || !supabaseAnonKey) {
    return loadSample("Supabase browser env is not configured. Showing bundled sample data.");
  }

  const params = new URLSearchParams();
  params.set("select", "*");
  params.set("status", "eq.active");
  params.set("order", "application_deadline_at.asc.nullslast,last_seen_at.desc");
  params.set("limit", "200");

  const response = await fetch(`${supabaseUrl.replace(/\/$/, "")}/rest/v1/campaign_cards?${params.toString()}`, {
    headers: {
      apikey: supabaseAnonKey,
      Authorization: `Bearer ${supabaseAnonKey}`,
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    return loadSample(`Supabase request failed (${response.status}). Showing bundled sample data.`);
  }

  const rows = (await response.json()) as CampaignCard[];
  return {
    campaigns: rows.filter(activeOnly),
    source: "supabase",
    generatedAt: rows[0]?.last_seen_at ?? null,
    warning: null,
  };
}

export async function loadCampaigns(): Promise<LoadResult> {
  return loadSupabase();
}
