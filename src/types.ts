export type SourceListing = {
  source_code: string;
  source_name: string;
  source_url: string;
  external_id: string | null;
  status: string;
};

export type CampaignCard = {
  id: string;
  title: string;
  brand_name: string | null;
  summary: string | null;
  category: string | null;
  status: "active" | "draft" | "closed" | "archived";
  application_deadline_at: string | null;
  reward_summary: string | null;
  location_text: string | null;
  primary_image_url: string | null;
  canonical_url: string | null;
  platform_tags: string[];
  region_tags: string[];
  benefit_tags: string[];
  first_seen_at: string;
  last_seen_at: string;
  source_count: number;
  source_listings: SourceListing[];
};

export type SampleCampaign = {
  source_code: string;
  source_name: string;
  external_id: string | null;
  source_url: string;
  normalized_url: string;
  title: string;
  brand_name: string | null;
  status: "active" | "draft" | "closed" | "archived";
  image_url: string | null;
  reward_summary: string | null;
  location_text: string | null;
  dedup_key: string;
  parsed_payload?: {
    platform_tags?: string[];
    region_tags?: string[];
    benefit_tags?: string[];
  };
};

export type SamplePayload = {
  generated_at: string;
  crawl_mode: string;
  source_summaries: Array<{
    source_code: string;
    status: string;
    item_count: number;
    reason: string | null;
  }>;
  campaigns: SampleCampaign[];
};
