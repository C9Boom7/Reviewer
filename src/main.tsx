import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  ArrowUpRight,
  Bell,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  ExternalLink,
  Filter,
  Gift,
  Heart,
  Home,
  Inbox,
  List,
  Loader2,
  Map,
  MapPin,
  Package,
  Search,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Star,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { loadCampaigns } from "./data";
import type { CampaignCard } from "./types";
import "./styles.css";

type DataState = {
  campaigns: CampaignCard[];
  source: "supabase" | "sample";
  generatedAt: string | null;
  warning: string | null;
};

type ActiveTab = "home" | "schedule" | "saved" | "my";
type QuickFilter = "all" | "delivery" | "visit" | "multi" | "urgent";
type SortMode = "deadline" | "recent" | "sources";

type FilterState = {
  query: string;
  quick: QuickFilter;
  source: string;
};

type CampaignTone = "mint" | "amber" | "violet" | "slate" | "coral" | "blue";
type DeadlineTone = "open" | "urgent" | "today" | "closed" | "unknown";

type DeadlineInfo = {
  label: string;
  detail: string;
  days: number | null;
  tone: DeadlineTone;
};

const emptyFilters: FilterState = {
  query: "",
  quick: "all",
  source: "all",
};

const platformLabels: Record<string, string> = {
  blog: "블로그",
  instagram: "인스타",
  youtube: "유튜브",
  naver_clip: "클립",
  receipt: "영수증",
};

const benefitLabels: Record<string, string> = {
  delivery: "배송",
  visit: "방문",
  reporter: "기자단",
  purchase_review: "구매평",
};

const sourceStatusLabels: Record<string, string> = {
  active: "수집중",
  removed: "종료",
  draft: "대기",
  closed: "마감",
  archived: "보관",
};

const sourceModeLabels: Record<string, string> = {
  full: "전체수집",
  summary_only: "요약수집",
  blocked: "차단",
  candidate: "후보",
};

const quickFilters: Array<{ id: QuickFilter; label: string; icon: LucideIcon }> = [
  { id: "all", label: "전체", icon: Sparkles },
  { id: "delivery", label: "배송형", icon: Package },
  { id: "visit", label: "방문형", icon: MapPin },
  { id: "multi", label: "여러 출처", icon: Star },
  { id: "urgent", label: "마감임박", icon: CheckCircle2 },
];

const sortModes: Array<{ id: SortMode; label: string }> = [
  { id: "deadline", label: "마감순" },
  { id: "recent", label: "최신순" },
  { id: "sources", label: "출처순" },
];

const navItems: Array<{ id: ActiveTab; label: string; icon: LucideIcon }> = [
  { id: "home", label: "홈", icon: Search },
  { id: "schedule", label: "일정", icon: CalendarDays },
  { id: "saved", label: "관심", icon: Heart },
  { id: "my", label: "MY", icon: UserRound },
];

function formatDate(value: string | null): string {
  if (!value) return "마감일 미정";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "마감일 미정";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
  }).format(date);
}

function formatDateTime(value: string | null): string {
  if (!value) return "수집 시각 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, "ko"));
}

function labelFor(value: string, labels: Record<string, string>): string {
  return labels[value] ?? value;
}

function confirmedSources(campaign: CampaignCard) {
  const active = campaign.source_listings.filter((source) => source.status === "active");
  return active.length > 0 ? active : campaign.source_listings;
}

function confirmedSourceCount(campaign: CampaignCard): number {
  const count = confirmedSources(campaign).length;
  return count > 0 ? count : campaign.source_count;
}

function primarySource(campaign: CampaignCard) {
  return confirmedSources(campaign)[0] ?? null;
}

function sourceName(campaign: CampaignCard): string {
  return primarySource(campaign)?.source_name ?? "출처 미정";
}

function sourceUrl(campaign: CampaignCard): string | null {
  return primarySource(campaign)?.source_url ?? campaign.canonical_url ?? null;
}

function getBenefitText(campaign: CampaignCard): string {
  if (campaign.reward_summary) return campaign.reward_summary;
  if (campaign.summary) return campaign.summary;
  if (campaign.benefit_tags.includes("delivery")) return "배송 제품 제공";
  if (campaign.benefit_tags.includes("visit")) return "방문 체험 제공";
  return "원문에서 제공 내역 확인";
}

function getLocationText(campaign: CampaignCard): string {
  if (campaign.location_text) return campaign.location_text;
  if (campaign.region_tags.length > 0) return `${campaign.region_tags[0]} 지역`;
  if (campaign.benefit_tags.includes("delivery")) return "전국 배송";
  return "지역 미정";
}

function getCategoryLabel(campaign: CampaignCard): string {
  if (campaign.benefit_tags.includes("delivery")) return "배송";
  if (campaign.benefit_tags.includes("visit")) return "방문";
  if (campaign.platform_tags.length > 0) return labelFor(campaign.platform_tags[0], platformLabels);
  return sourceName(campaign);
}

function getDeadlineDate(campaign: CampaignCard): Date | null {
  if (!campaign.application_deadline_at) return null;
  const date = new Date(campaign.application_deadline_at);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getDeadlineInfo(campaign: CampaignCard): DeadlineInfo {
  const deadline = getDeadlineDate(campaign);
  if (!deadline) {
    return {
      label: "상시",
      detail: "마감일 미정",
      days: null,
      tone: "unknown",
    };
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  deadline.setHours(0, 0, 0, 0);
  const days = Math.ceil((deadline.getTime() - today.getTime()) / 86_400_000);
  const dateLabel = formatDate(campaign.application_deadline_at);
  if (days < 0) {
    return {
      label: "마감",
      detail: `${dateLabel} 종료`,
      days,
      tone: "closed",
    };
  }
  if (days === 0) {
    return {
      label: "오늘마감",
      detail: `${dateLabel} 오늘 마감`,
      days,
      tone: "today",
    };
  }
  return {
    label: `D-${days}`,
    detail: `${dateLabel} 마감${days <= 3 ? " 임박" : ""}`,
    days,
    tone: days <= 3 ? "urgent" : "open",
  };
}

function getScheduleDate(campaign: CampaignCard): Date | null {
  return getDeadlineDate(campaign);
}

function getConditionText(campaign: CampaignCard): string {
  const benefits = campaign.benefit_tags.map((tag) => labelFor(tag, benefitLabels));
  const platforms = campaign.platform_tags.map((tag) => labelFor(tag, platformLabels));
  const labels = uniqueSorted([...benefits, ...platforms]);
  return labels.length > 0 ? labels.join(", ") : "원문에서 확인";
}

function sourceStatusLabel(status: string): string {
  return sourceStatusLabels[status] ?? status;
}

function sourceModeLabel(mode: string | null | undefined): string {
  if (!mode) return "요약수집";
  return sourceModeLabels[mode] ?? mode;
}

function hasSummaryOnlySource(campaign: CampaignCard): boolean {
  return confirmedSources(campaign).some((source) => !source.source_mode || source.source_mode === "summary_only");
}

function sourceDisclosureText(campaign: CampaignCard): string {
  const source = primarySource(campaign);
  if (!source) return "수집 출처에서 가져온 요약 정보예요. 세부 조건은 원본에서 확인하세요.";
  if (!source.source_mode || source.source_mode === "summary_only") {
    return `${source.source_name}의 공개 요약 영역에서 가져왔어요. 세부 조건과 신청 가능 여부는 원본에서 확인하세요.`;
  }
  return `${source.source_name}에서 가져왔어요. 세부 조건과 신청 가능 여부는 원본에서 확인하세요.`;
}

function dateTimeValue(value: string | null): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
}

function campaignSearchText(campaign: CampaignCard): string {
  return [
    campaign.title,
    campaign.brand_name,
    campaign.summary,
    campaign.reward_summary,
    campaign.location_text,
    campaign.category,
    campaign.platform_tags.join(" "),
    campaign.benefit_tags.join(" "),
    campaign.region_tags.join(" "),
    confirmedSources(campaign).map((source) => source.source_name).join(" "),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function applyFilters(campaigns: CampaignCard[], filters: FilterState): CampaignCard[] {
  const query = filters.query.trim().toLowerCase();
  return campaigns.filter((campaign) => {
    if (query && !campaignSearchText(campaign).includes(query)) return false;
    if (filters.source !== "all" && !confirmedSources(campaign).some((source) => source.source_code === filters.source)) {
      return false;
    }
    if (filters.quick === "delivery" && !campaign.benefit_tags.includes("delivery")) return false;
    if (filters.quick === "visit" && !campaign.benefit_tags.includes("visit")) return false;
    if (filters.quick === "multi" && confirmedSourceCount(campaign) < 2) return false;
    if (filters.quick === "urgent") {
      const days = getDeadlineInfo(campaign).days;
      if (days === null || days < 0 || days > 3) return false;
    }
    return true;
  });
}

function nextSortMode(current: SortMode): SortMode {
  const index = sortModes.findIndex((mode) => mode.id === current);
  return sortModes[(index + 1) % sortModes.length].id;
}

function sortLabel(mode: SortMode): string {
  return sortModes.find((sortMode) => sortMode.id === mode)?.label ?? "마감순";
}

function sortCampaigns(campaigns: CampaignCard[], mode: SortMode): CampaignCard[] {
  return [...campaigns].sort((a, b) => {
    if (mode === "recent") {
      const recentDiff = dateTimeValue(b.last_seen_at) - dateTimeValue(a.last_seen_at);
      if (recentDiff !== 0) return recentDiff;
    }

    if (mode === "sources") {
      const sourceDiff = confirmedSourceCount(b) - confirmedSourceCount(a);
      if (sourceDiff !== 0) return sourceDiff;
      const recentDiff = dateTimeValue(b.last_seen_at) - dateTimeValue(a.last_seen_at);
      if (recentDiff !== 0) return recentDiff;
    }

    const aDeadline = getDeadlineDate(a)?.getTime() ?? Number.POSITIVE_INFINITY;
    const bDeadline = getDeadlineDate(b)?.getTime() ?? Number.POSITIVE_INFINITY;
    if (aDeadline !== bDeadline) return aDeadline - bDeadline;
    return dateTimeValue(b.last_seen_at) - dateTimeValue(a.last_seen_at);
  });
}

function sourceTone(sourceCode: string): CampaignTone {
  const tones: Record<string, CampaignTone> = {
    reviewnote: "mint",
    gangnammatzip: "coral",
    ringble: "blue",
    reviewplace: "amber",
    tble: "slate",
  };
  return tones[sourceCode] ?? "violet";
}

function campaignTone(campaign: CampaignCard, index: number): CampaignTone {
  const source = primarySource(campaign);
  if (source) return sourceTone(source.source_code);
  const tones: CampaignTone[] = ["mint", "amber", "violet", "slate", "coral", "blue"];
  return tones[index % tones.length];
}

function CampaignArt({ campaign, large = false }: { campaign: CampaignCard; large?: boolean }) {
  const Icon = campaign.benefit_tags.includes("delivery") ? Package : campaign.benefit_tags.includes("visit") ? MapPin : Gift;
  return (
    <div className={`campaignArt ${large ? "large" : ""}`}>
      {campaign.primary_image_url ? <img src={campaign.primary_image_url} alt="" loading="lazy" /> : <Icon size={large ? 54 : 34} strokeWidth={1.8} />}
    </div>
  );
}

function Notice({ warning }: { warning: string | null }) {
  if (!warning) return null;
  const message = warning.includes("Supabase browser env is not configured")
    ? "Supabase 연결값이 없어 샘플 데이터를 보여줘요."
    : warning.includes("Supabase request failed")
      ? "Supabase 요청에 실패해 샘플 데이터를 보여줘요."
      : warning;
  return (
    <div className="inlineNotice">
      <AlertCircle size={15} />
      <span>{message}</span>
    </div>
  );
}

function AppHeader({ dataSource }: { dataSource: DataState["source"] }) {
  return (
    <header className="appHeader">
      <div>
        <h1>체험단 모아보기</h1>
        <p>{dataSource === "supabase" ? "실시간 수집 데이터" : "샘플 데이터 미리보기"}</p>
      </div>
      <div className="headerActions" aria-label="앱 메뉴">
        <button className="iconButton" type="button" aria-label="알림">
          <Bell size={21} />
        </button>
        <button className="iconButton" type="button" aria-label="설정">
          <Settings size={21} />
        </button>
      </div>
    </header>
  );
}

function CampaignTile({
  campaign,
  index,
  saved,
  onOpen,
  onToggleSave,
}: {
  campaign: CampaignCard;
  index: number;
  saved: boolean;
  onOpen: () => void;
  onToggleSave: () => void;
}) {
  const tone = campaignTone(campaign, index);
  const deadline = getDeadlineInfo(campaign);
  const sourceCount = confirmedSourceCount(campaign);
  return (
    <article className={`campaignTile tone-${tone}`} onClick={onOpen} role="button" tabIndex={0}>
      <div className="tileBanner">
        <CampaignArt campaign={campaign} />
        <span className={`dayPill deadline-${deadline.tone}`}>{deadline.label}</span>
      </div>
      <div className="tileBody">
        <div className="tileMeta">
          <span className="sourceChip">{getCategoryLabel(campaign)}</span>
          {hasSummaryOnlySource(campaign) && <span className="plainChip summary">요약수집</span>}
          {sourceCount > 1 && <span className="plainChip">출처 {sourceCount}</span>}
          <button
            className={`heartButton ${saved ? "isSaved" : ""}`}
            type="button"
            aria-label={saved ? "관심 해제" : "관심 추가"}
            onClick={(event) => {
              event.stopPropagation();
              onToggleSave();
            }}
          >
            <Heart size={20} fill={saved ? "currentColor" : "none"} />
          </button>
        </div>
        <h2>{campaign.title}</h2>
        <p>{getBenefitText(campaign)}</p>
        <span className="tileLocation">
          <MapPin size={14} />
          {getLocationText(campaign)}
        </span>
      </div>
    </article>
  );
}

function HomeView({
  data,
  filters,
  setFilters,
  sortMode,
  setSortMode,
  campaigns,
  options,
  savedIds,
  onOpenCampaign,
  onToggleSave,
}: {
  data: DataState;
  filters: FilterState;
  setFilters: React.Dispatch<React.SetStateAction<FilterState>>;
  sortMode: SortMode;
  setSortMode: React.Dispatch<React.SetStateAction<SortMode>>;
  campaigns: CampaignCard[];
  options: { sources: string[]; sourceLabels: Record<string, string> };
  savedIds: Set<string>;
  onOpenCampaign: (campaign: CampaignCard) => void;
  onToggleSave: (id: string) => void;
}) {
  return (
    <>
      <AppHeader dataSource={data.source} />
      <Notice warning={data.warning} />

      <section className="searchPanel">
        <label className="mobileSearch">
          <Search size={22} />
          <input
            value={filters.query}
            onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))}
            placeholder="맛집, 지역, 키워드 검색"
          />
        </label>
        <div className="chipScroller" aria-label="빠른 필터">
          {quickFilters.map((filter) => {
            const Icon = filter.icon;
            return (
              <button
                className={`filterChip ${filters.quick === filter.id ? "isActive" : ""}`}
                type="button"
                key={filter.id}
                onClick={() => setFilters((current) => ({ ...current, quick: filter.id }))}
              >
                <Icon size={16} />
                {filter.label}
              </button>
            );
          })}
          <button className="filterChip ghost" type="button" onClick={() => setFilters(emptyFilters)}>
            <Filter size={16} />
            초기화
          </button>
        </div>
        <div className="sourceScroller" aria-label="출처 필터">
          <button
            className={`sourceFilter ${filters.source === "all" ? "isActive" : ""}`}
            type="button"
            onClick={() => setFilters((current) => ({ ...current, source: "all" }))}
          >
            전체 출처
          </button>
          {options.sources.map((source) => (
            <button
              className={`sourceFilter ${filters.source === source ? "isActive" : ""}`}
              type="button"
              key={source}
              onClick={() => setFilters((current) => ({ ...current, source }))}
            >
              {options.sourceLabels[source] ?? source}
            </button>
          ))}
        </div>
        <div className="scrollRail" />
      </section>

      <section className="listToolbar">
        <strong>총 {campaigns.length}개</strong>
        <div>
          <button className="sortButton" type="button" onClick={() => setSortMode((current) => nextSortMode(current))}>
            {sortLabel(sortMode)}
            <SlidersHorizontal size={16} />
          </button>
          <button className="viewButton isActive" type="button" aria-label="리스트 보기">
            <List size={18} />
          </button>
          <button className="viewButton" type="button" aria-label="지도 보기">
            <Map size={18} />
          </button>
        </div>
      </section>

      {campaigns.length === 0 ? (
        <EmptyState title="조건에 맞는 캠페인이 없어요" action="필터 초기화" onAction={() => setFilters(emptyFilters)} />
      ) : (
        <section className="campaignGrid">
          {campaigns.map((campaign, index) => (
            <CampaignTile
              campaign={campaign}
              index={index}
              key={campaign.id}
              saved={savedIds.has(campaign.id)}
              onOpen={() => onOpenCampaign(campaign)}
              onToggleSave={() => onToggleSave(campaign.id)}
            />
          ))}
        </section>
      )}
    </>
  );
}

function DetailView({
  campaign,
  index,
  saved,
  onBack,
  onToggleSave,
}: {
  campaign: CampaignCard;
  index: number;
  saved: boolean;
  onBack: () => void;
  onToggleSave: () => void;
}) {
  const tone = campaignTone(campaign, index);
  const link = sourceUrl(campaign);
  const source = primarySource(campaign);
  const sources = confirmedSources(campaign);
  const sourceCount = confirmedSourceCount(campaign);
  const deadline = getDeadlineInfo(campaign);
  return (
    <section className="detailScreen">
      <div className={`detailHeroMobile tone-${tone}`}>
        <button className="backButton" type="button" onClick={onBack} aria-label="뒤로">
          <ChevronLeft size={24} />
        </button>
        <CampaignArt campaign={campaign} large />
      </div>

      <div className="detailSheet">
        <div className="detailTitleRow">
          <span className="sourceChip">{getCategoryLabel(campaign)}</span>
          <button className={`heartButton large ${saved ? "isSaved" : ""}`} type="button" onClick={onToggleSave} aria-label="관심">
            <Heart size={23} fill={saved ? "currentColor" : "none"} />
          </button>
        </div>
        <h1>{campaign.title}</h1>

        <section className="statusCard">
          <div className="statusHeader">
            <ClipboardList size={20} />
            <strong>내 진행 상태</strong>
            <button type="button">변경</button>
          </div>
          <div className="statusLine">
            <Check size={17} />
            {hasSummaryOnlySource(campaign) ? "요약 수집 정보" : "원문 확인 가능"}
          </div>
          <div className="statusLine">
            <CalendarDays size={17} />
            신청 마감: {deadline.detail}
          </div>
        </section>

        <section className="infoPanel">
          <InfoRow icon={Gift} label="혜택" value={getBenefitText(campaign)} tone="green" />
          <InfoRow icon={MapPin} label="위치" value={getLocationText(campaign)} tone="blue" />
          <InfoRow icon={CalendarDays} label="마감" value={deadline.detail} tone="amber" />
          <InfoRow icon={Users} label="출처" value={`${sourceName(campaign)}${sourceCount > 1 ? ` 외 ${sourceCount - 1}곳` : ""}`} tone="violet" />
          <InfoRow icon={ClipboardList} label="조건" value={getConditionText(campaign)} tone="gray" />
        </section>

        <section className="detailSection">
          <h2>캠페인 소개</h2>
          <p>{campaign.summary || campaign.reward_summary || "수집된 캠페인 원문에서 상세 조건과 신청 방법을 확인할 수 있습니다."}</p>
        </section>

        <section className="sourceNotice">
          <Inbox size={17} />
          {sourceDisclosureText(campaign)}
        </section>

        {sources.length > 1 && (
          <section className="detailSection">
            <h2>다른 출처</h2>
            <div className="sourceLinkList">
              {sources.map((listing) => (
                <a href={listing.source_url} target="_blank" rel="noreferrer" key={`${listing.source_code}-${listing.source_url}`}>
                  <span>{listing.source_name}</span>
                  <small>{sourceStatusLabel(listing.status)} · {sourceModeLabel(listing.source_mode)}</small>
                  <ArrowUpRight size={15} />
                </a>
              ))}
            </div>
          </section>
        )}
      </div>

      <div className="stickyCta">
        {link ? (
          <a href={link} target="_blank" rel="noreferrer">
            원문에서 신청하러 가기
            <ExternalLink size={18} />
          </a>
        ) : (
          <button type="button" disabled>
            신청 링크 없음
          </button>
        )}
      </div>
    </section>
  );
}

function InfoRow({ icon: Icon, label, value, tone }: { icon: LucideIcon; label: string; value: string; tone: string }) {
  return (
    <div className="infoRow">
      <span className={`infoIcon ${tone}`}>
        <Icon size={19} />
      </span>
      <span>
        <small>{label}</small>
        <strong>{value}</strong>
      </span>
    </div>
  );
}

function ScheduleView({ campaigns, onOpenCampaign }: { campaigns: CampaignCard[]; onOpenCampaign: (campaign: CampaignCard) => void }) {
  const [monthCursor, setMonthCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState(() => new Date().getDate());

  const entries = useMemo(
    () =>
      campaigns.flatMap((campaign, index) => {
        const date = getScheduleDate(campaign);
        if (!date) return [];
        return [
          {
            campaign,
            index,
            date,
            deadline: getDeadlineInfo(campaign),
          },
        ];
      }),
    [campaigns],
  );

  const year = monthCursor.getFullYear();
  const month = monthCursor.getMonth();
  const monthEntries = entries.filter((entry) => entry.date.getFullYear() === year && entry.date.getMonth() === month);
  const selectedEntries = monthEntries.filter((entry) => entry.date.getDate() === selectedDay);
  const urgentCount = entries.filter((entry) => entry.deadline.days !== null && entry.deadline.days >= 0 && entry.deadline.days <= 3).length;
  const unknownDeadlineCount = Math.max(0, campaigns.length - entries.length);
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const calendarCells = [...Array.from({ length: firstDay }, () => null), ...Array.from({ length: daysInMonth }, (_, index) => index + 1)];

  return (
    <section className="scheduleScreen">
      <header className="sectionHeader">
        <h1>일정</h1>
      </header>

      <div className="scheduleSwitch">
        <button type="button">
          <ClockIcon />
          <span>신청한 캠페인</span>
          <small>발표일 관리</small>
        </button>
        <button className="isActive" type="button">
          <CalendarDays size={27} />
          <span>선정된 캠페인</span>
          <small>리뷰 마감일 관리</small>
        </button>
      </div>

      <div className="scheduleStats">
        <StatBox value={entries.length} label="마감 확인" active />
        <StatBox value={urgentCount} label="임박" />
        <StatBox value={unknownDeadlineCount} label="마감 미정" />
      </div>

      <section className="calendarPanel">
        <div className="calendarHeader">
          <button type="button" aria-label="이전 달" onClick={() => setMonthCursor((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}>
            <ChevronLeft size={23} />
          </button>
          <strong>{year}년 {month + 1}월</strong>
          <button type="button" aria-label="다음 달" onClick={() => setMonthCursor((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}>
            <ChevronRight size={23} />
          </button>
        </div>
        <div className="weekDays">
          {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
        <div className="calendarGrid">
          {calendarCells.map((day, cellIndex) => {
            if (!day) return <span className="emptyDay" key={`empty-${cellIndex}`} />;
            const dayEntries = monthEntries.filter((entry) => entry.date.getDate() === day);
            const isSelected = day === selectedDay;
            return (
              <button className={`dayCell ${isSelected ? "isSelected" : ""}`} type="button" key={day} onClick={() => setSelectedDay(day)}>
                <span>{day}</span>
                {dayEntries.length > 0 && <i className={dayEntries.some((entry) => entry.deadline.tone === "urgent" || entry.deadline.tone === "today") ? "deadlineDot" : "updateDot"} />}
              </button>
            );
          })}
        </div>
      </section>

      <section className="dayAgenda">
        <div className="agendaHeader">
          <strong>{month + 1}월 {selectedDay}일</strong>
          <span>{selectedEntries.length}개</span>
        </div>
        {selectedEntries.length === 0 ? (
          <div className="agendaEmpty">
            <CalendarDays size={44} />
            <p>등록된 일정이 없어요</p>
          </div>
        ) : (
          selectedEntries.map((entry) => (
            <button className="agendaItem" type="button" key={entry.campaign.id} onClick={() => onOpenCampaign(entry.campaign)}>
              <span className={`agendaMark tone-${campaignTone(entry.campaign, entry.index)}`} />
              <span>
                <strong>{entry.campaign.title}</strong>
                <small>{getBenefitText(entry.campaign)}</small>
              </span>
              <ArrowUpRight size={16} />
            </button>
          ))
        )}
      </section>
    </section>
  );
}

function ClockIcon() {
  return <CalendarDays size={27} />;
}

function StatBox({ value, label, active = false }: { value: number; label: string; active?: boolean }) {
  return (
    <div className={active ? "isActive" : ""}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function SavedView({
  campaigns,
  savedIds,
  onOpenCampaign,
}: {
  campaigns: CampaignCard[];
  savedIds: Set<string>;
  onOpenCampaign: (campaign: CampaignCard) => void;
}) {
  const savedCampaigns = campaigns.filter((campaign) => savedIds.has(campaign.id));
  return (
    <section className="simpleScreen">
      <header className="sectionHeader">
        <h1>관심</h1>
        <p>이 화면에서는 브라우저 세션 안에서만 보관됩니다.</p>
      </header>
      {savedCampaigns.length === 0 ? (
        <EmptyState title="관심 캠페인이 없어요" />
      ) : (
        <div className="savedList">
          {savedCampaigns.map((campaign, index) => (
            <button className="savedItem" type="button" key={campaign.id} onClick={() => onOpenCampaign(campaign)}>
              <span className={`savedThumb tone-${campaignTone(campaign, index)}`}>
                <CampaignArt campaign={campaign} />
              </span>
              <span>
                <strong>{campaign.title}</strong>
                <small>{getBenefitText(campaign)}</small>
              </span>
              <ArrowUpRight size={16} />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function MyView({ data, campaigns, sources }: { data: DataState; campaigns: CampaignCard[]; sources: string[] }) {
  return (
    <section className="simpleScreen">
      <header className="sectionHeader">
        <h1>MY</h1>
        <p>{data.source === "supabase" ? "Supabase live" : "Sample data"}</p>
      </header>
      <div className="profileCard">
        <div className="profileAvatar">
          <UserRound size={30} />
        </div>
        <div>
          <strong>Reviewer</strong>
          <span>최근 수집 {formatDateTime(data.generatedAt)}</span>
        </div>
      </div>
      <div className="myStats">
        <StatBox value={campaigns.length} label="캠페인" active />
        <StatBox value={sources.length} label="출처" />
        <StatBox value={campaigns.filter((campaign) => campaign.benefit_tags.includes("delivery")).length} label="배송형" />
      </div>
      <section className="sourceSummary">
        <h2>수집 출처</h2>
        {sources.map((source) => (
          <div className="sourceSummaryItem" key={source}>
            <span>{source}</span>
            <strong>{campaigns.filter((campaign) => confirmedSources(campaign).some((listing) => listing.source_name === source)).length}개</strong>
          </div>
        ))}
      </section>
    </section>
  );
}

function EmptyState({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return (
    <div className="emptyState">
      <Inbox size={38} />
      <h2>{title}</h2>
      {action && onAction && (
        <button type="button" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

function BottomNav({ activeTab, onChange }: { activeTab: ActiveTab; onChange: (tab: ActiveTab) => void }) {
  return (
    <nav className="bottomNav" aria-label="하단 탭">
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <button className={activeTab === item.id ? "isActive" : ""} type="button" key={item.id} onClick={() => onChange(item.id)}>
            <Icon size={24} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function App() {
  const [data, setData] = useState<DataState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>(emptyFilters);
  const [sortMode, setSortMode] = useState<SortMode>("deadline");
  const [activeTab, setActiveTab] = useState<ActiveTab>("home");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    let mounted = true;
    loadCampaigns()
      .then((result) => {
        if (!mounted) return;
        setData(result);
      })
      .catch((caught: unknown) => {
        if (!mounted) return;
        setError(caught instanceof Error ? caught.message : "데이터를 불러오지 못했습니다.");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const sortedCampaigns = useMemo(() => sortCampaigns(data?.campaigns ?? [], sortMode), [data, sortMode]);

  const visibleCampaigns = useMemo(() => applyFilters(sortedCampaigns, filters), [sortedCampaigns, filters]);

  const options = useMemo(() => {
    const campaigns = data?.campaigns ?? [];
    const sourceListings = campaigns.flatMap((campaign) => confirmedSources(campaign));
    return {
      sources: uniqueSorted(sourceListings.map((source) => source.source_code)),
      sourceLabels: Object.fromEntries(sourceListings.map((source) => [source.source_code, source.source_name])),
      sourceNames: uniqueSorted(sourceListings.map((source) => source.source_name)),
    };
  }, [data]);

  const selectedCampaign = sortedCampaigns.find((campaign) => campaign.id === selectedId) ?? null;
  const selectedIndex = selectedCampaign ? Math.max(0, sortedCampaigns.findIndex((campaign) => campaign.id === selectedCampaign.id)) : 0;

  function toggleSaved(id: string) {
    setSavedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (error) {
    return (
      <main className="appCanvas">
        <section className="phoneFrame centerState">
          <AlertCircle size={34} />
          <h1>데이터를 불러오지 못했습니다</h1>
          <p>{error}</p>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="appCanvas">
        <section className="phoneFrame centerState">
          <Loader2 className="spin" size={34} />
          <h1>캠페인 데이터를 불러오는 중</h1>
        </section>
      </main>
    );
  }

  return (
    <main className="appCanvas">
      <section className={`phoneFrame ${selectedCampaign ? "detailMode" : ""}`}>
        {selectedCampaign ? (
          <DetailView
            campaign={selectedCampaign}
            index={selectedIndex}
            saved={savedIds.has(selectedCampaign.id)}
            onBack={() => setSelectedId(null)}
            onToggleSave={() => toggleSaved(selectedCampaign.id)}
          />
        ) : (
          <>
            <div className="screenBody">
              {activeTab === "home" && (
                <HomeView
                  data={data}
                  filters={filters}
                  setFilters={setFilters}
                  sortMode={sortMode}
                  setSortMode={setSortMode}
                  campaigns={visibleCampaigns}
                  options={options}
                  savedIds={savedIds}
                  onOpenCampaign={(campaign) => setSelectedId(campaign.id)}
                  onToggleSave={toggleSaved}
                />
              )}
              {activeTab === "schedule" && <ScheduleView campaigns={sortedCampaigns} onOpenCampaign={(campaign) => setSelectedId(campaign.id)} />}
              {activeTab === "saved" && <SavedView campaigns={sortedCampaigns} savedIds={savedIds} onOpenCampaign={(campaign) => setSelectedId(campaign.id)} />}
              {activeTab === "my" && <MyView data={data} campaigns={sortedCampaigns} sources={options.sourceNames} />}
            </div>
            <BottomNav activeTab={activeTab} onChange={setActiveTab} />
          </>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
