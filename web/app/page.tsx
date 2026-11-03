"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import Image from "next/image";
import { BrainCircuit, Bot, ChartNoAxesCombined, ClipboardCheck, ClipboardList, Crosshair, FileChartColumn, LayoutDashboard, NotebookPen, Route, ShieldCheck, Target, WalletCards } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ApiError, apiRequest, getApiBaseUrl } from "./api";
import { AccountSwitcher, DetectedAccountsBanner, useDetectedAccounts } from "./multi-account";
import { EaSetupWizard } from "./ea-wizard";
import { ConnectionVerifier } from "./connection-verifier";
import { EditAccountModal } from "./edit-account-modal";
import { PnlCalendar } from "./components/pnl-calendar";
import { ReportsPage, AnalyticsWorkspace, DevelopmentRoadmap, RiskIntelligence, StrategyLab, AskAgentPanel, EdgeSnapshot, RoadmapWidget, fmtR, profitFactorTone, usePerformanceData } from "./components/performance-workspace";
import { LandingPage } from "./landing-page";
import { AgentPage } from "./components/agent-workspace";
type ViewId = "overview" | "journal" | "plans" | "reviews" | "analytics" | "intelligence" | "agent" | "strategies" | "risk" | "execution" | "roadmap" | "reports" | "accounts";
type TradeOutcome = "Win" | "Loss" | "Flat" | "Open" | "Planned" | "Discarded";
type Trade = {
  id: string;
  symbol: string;
  direction: "Long" | "Short";
  strategy: string;
  date: string;
  outcome: TradeOutcome;
  pnl: number | null;
  rMultiple: number | null;
  plan: string;
  entryPrice?: number | null;
  exitPrice?: number | null;
  stopLoss?: number | null;
  takeProfit?: number | null;
  size?: number | null;
  setupNotes?: string;
  setupEmotion?: string;
  setupName?: string;
  maeR?: number | null;
  mfeR?: number | null;
  emotionalState?: string | null;
  confluences?: string[];
  ruleBreaks?: string[];
  journalEntries?: TradeJournalEntry[];
  source?: "demo" | "manual" | "mt5";
  accountId?: string | null;
};
type TradeJournalEntry = {
  id: string;
  date: string;
  stage: "Setup" | "Execution" | "Management" | "Exit";
  emotion: string;
  note: string;
};
type TradeReview = {
  tradeId: string;
  planAdherence: "yes" | "partly" | "no";
  learning: string;
  nextAction: string;
};
type AccountSetup = {
  id: string;
  name: string;
  provider: "MT5" | "TradingView";
  server: string;
  loginId: string;
  connectorType?: string;
  lastError?: string | null;
  status?: string;
  openPositions?: number;
  balance?: number | null;
  equity?: number | null;
  currency?: string;
};
function userFirstName(user?: { full_name?: string | null; email: string } | null) {
  const fromName = user?.full_name?.trim().split(/\s+/)[0];
  const name = fromName || (user?.email ?? "").split("@")[0].split(/[^a-zA-Z]+/).find(Boolean) || "";
  return name ? name.charAt(0).toUpperCase() + name.slice(1) : "Trader";
}

function greeting(timezone?: string) {
  let hour = new Date().getHours();
  if (timezone && timezone !== "local") {
    try {
      hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: timezone }).format(new Date()));
    } catch {
      // Fall back to the device timezone for unsupported zones.
    }
  }
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

type ApiUser = { id: string; full_name: string | null; email: string; created_at: string };
type ApiAccount = {
  id: string;
  name: string;
  external_account_id: string | null;
  broker: string | null;
  server_name: string | null;
  account_type: string;
  environment: "demo" | "live" | "evaluation";
  currency: string;
};
type ApiTrade = {
  id: string;
  symbol: string;
  direction: "Long" | "Short";
  strategy: string;
  outcome: "win" | "loss" | "flat" | "open";
  pnl: number | null;
  r_multiple: number | null;
  entry_price: number | null;
  exit_price: number | null;
  size: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  setup?: string | null;
  mae_r?: number | null;
  mfe_r?: number | null;
  emotional_state?: string | null;
  confluences?: string[];
  rule_breaks?: string[];
  floating_pnl: number | null;
  account_id?: string | null;
  notes: string | null;
  source: "user" | "mt5";
  opened_at: string;
  closed_at: string | null;
};
type ApiPlan = {
  id: string;
  symbol: string;
  direction: "Long" | "Short";
  strategy: string;
  thesis: string;
  account_id?: string | null;
  state: "planned" | "discarded" | "invalidated";
  created_at: string;
};
type ApiReview = {
  trade_id: string;
  plan_adherence: "yes" | "partly" | "no";
  learning: string;
  next_action: string;
};
type ApiJournalSection = { section_key: string; content: unknown };
type OneTimeSecret = {
  heading: string;
  description: string;
  value: string;
  config?: string;
};
type DashboardRangePreset = "all" | "7d" | "30d" | "90d" | "custom";
type DashboardDateRange = {
  preset: DashboardRangePreset;
  startDate: string;
  endDate: string;
};

const navIcons: Record<ViewId, LucideIcon> = {
  overview: LayoutDashboard, journal: NotebookPen, plans: ClipboardList, reviews: ClipboardCheck, analytics: ChartNoAxesCombined,
  intelligence: BrainCircuit, agent: Bot, strategies: Target, execution: Crosshair, risk: ShieldCheck, roadmap: Route, reports: FileChartColumn, accounts: WalletCards,
};

const navigation: { id: ViewId; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "grid" },
  { id: "journal", label: "Trade journal", icon: "book" },
  { id: "plans", label: "Trade plans", icon: "target" },
  { id: "reviews", label: "Reviews", icon: "check" },
  { id: "analytics", label: "Analytics", icon: "chart" },
  { id: "intelligence", label: "Edge Intelligence", icon: "spark" },
  { id: "agent", label: "TradeIQ Agent", icon: "spark" },
  { id: "strategies", label: "Strategy Lab", icon: "target" },
  { id: "execution", label: "Execution Lab", icon: "check" },
  { id: "risk", label: "Risk Intelligence", icon: "wallet" },
  { id: "roadmap", label: "Development Roadmap", icon: "check" },
  { id: "reports", label: "Reports", icon: "book" },
  { id: "accounts", label: "Accounts", icon: "wallet" },
];

const STORAGE_KEY = "tradeiq.journal.v1";
const DRAFT_PREFIX = "tradeiq.draft.";

// Maps a FastAPI 422 body (JSON-encoded by apiRequest) to per-field messages.
function apiFieldErrors(error: unknown): Record<string, string> | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  try {
    const items: unknown = JSON.parse(error.message);
    if (!Array.isArray(items)) return null;
    const result: Record<string, string> = {};
    for (const item of items) {
      const loc = (item as { loc?: unknown[] }).loc;
      const field = Array.isArray(loc) ? String(loc[loc.length > 1 ? 1 : 0]) : "";
      const msg = String((item as { msg?: unknown }).msg ?? "Invalid value").replace(/^Value error, /, "");
      if (field && !(field in result)) result[field] = msg;
    }
    return Object.keys(result).length ? result : null;
  } catch {
    return null;
  }
}

// The API requires a timezone offset; treat offset-less timestamps as UTC.
function utcTimestamp(value: string): string {
  const normalized = /(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  const time = Date.parse(normalized);
  return new Date(Number.isNaN(time) ? Date.now() : time).toISOString();
}

// Like useState, but keeps the value in localStorage until clearDrafts() is called for its scope.
function useDraftState<T extends string = string>(scope: string, field: string, initialValue: string) {
  const initial = initialValue as T;
  const key = `${DRAFT_PREFIX}${scope}.${field}`;
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = window.localStorage.getItem(key);
      return saved === null ? initial : (JSON.parse(saved) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      if (value === initial) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage can be full or blocked; the form still works without a draft.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, key]);
  return [value, setValue] as const;
}

function clearDrafts(scope: string) {
  try {
    const prefix = `${DRAFT_PREFIX}${scope}.`;
    Object.keys(window.localStorage).filter((name) => name.startsWith(prefix)).forEach((name) => window.localStorage.removeItem(name));
  } catch {
    // Nothing to clear when storage is unavailable.
  }
}
const ACTIVE_VIEW_KEY = "tradeiq.activeView";

type SavedWorkspace = {
  version: 1;
  trades: Trade[];
  reviews: TradeReview[];
  timezone?: string;
  accounts?: AccountSetup[];
};

const viewCopy: Record<ViewId, { title: string; description: string }> = {
  overview: { title: "Overview", description: "A clear view of your process, performance, and next review." },
  journal: { title: "Trade journal", description: "A reconciled record of what happened and what you learned." },
  plans: { title: "Trade plans", description: "Capture your intent before the first fill changes the story." },
  reviews: { title: "Trade reviews", description: "Turn completed trades into one clear next action." },
  analytics: { title: "Performance analytics", description: "Read process and outcomes together, with context." },
  intelligence: { title: "Edge Intelligence", description: "What is happening, what your data reveals, what to work on, and whether you are improving." },
  agent: { title: "TradeIQ Agent", description: "Your personal coach: statistically guarded findings, rules to test, and a process score that tracks real progress." },
  strategies: { title: "Strategy Lab", description: "Rank and compare the setups you actually trade." },
  execution: { title: "Execution Lab", description: "Planned versus actual: how closely your execution followed the trade you planned." },
  risk: { title: "Risk Intelligence", description: "Drawdown, discipline and the cost of rule breaks." },
  roadmap: { title: "Development Roadmap", description: "Your focus areas and whether they are moving." },
  reports: { title: "Reports", description: "Compare a period with the one before it and download the evidence." },
  accounts: { title: "Trading accounts", description: "Keep each trading environment visible and distinct." },
};

function mapApiTrade(trade: ApiTrade): Trade {
  const outcome: Record<ApiTrade["outcome"], TradeOutcome> = {
    win: "Win",
    loss: "Loss",
    flat: "Flat",
    open: "Open",
  };
  return {
    id: trade.id,
    symbol: trade.symbol,
    direction: trade.direction,
    strategy: trade.strategy,
    date: trade.opened_at,
    outcome: outcome[trade.outcome],
    pnl: trade.pnl,
    rMultiple: trade.r_multiple,
    entryPrice: trade.entry_price,
    exitPrice: trade.exit_price,
    size: trade.size,
    stopLoss: trade.stop_loss,
    takeProfit: trade.take_profit,
    setupName: trade.setup ?? "",
    maeR: trade.mae_r ?? null,
    mfeR: trade.mfe_r ?? null,
    emotionalState: trade.emotional_state ?? null,
    confluences: trade.confluences ?? [],
    ruleBreaks: trade.rule_breaks ?? [],
    plan: trade.notes ?? "",
    source: trade.source === "mt5" ? "mt5" : "manual",
    accountId: trade.account_id ?? null,
  };
}

function v2Context(trade: Trade) {
  return {
    setup: trade.setupName?.trim() || undefined,
    mae_r: trade.maeR ?? null,
    mfe_r: trade.mfeR ?? null,
    emotional_state: trade.emotionalState ?? null,
    confluences: trade.confluences ?? [],
    rule_breaks: trade.ruleBreaks ?? [],
  };
}

function recordField(content: unknown, key: string): unknown {
  if (!content || typeof content !== "object" || Array.isArray(content)) return undefined;
  return (content as Record<string, unknown>)[key];
}

function mapApiPlan(plan: ApiPlan): Trade {
  return {
    id: plan.id,
    symbol: plan.symbol,
    direction: plan.direction,
    strategy: plan.strategy,
    date: plan.created_at,
    outcome: plan.state === "planned" ? "Planned" : "Discarded",
    pnl: null,
    rMultiple: null,
    plan: plan.thesis,
    source: "manual",
    accountId: plan.account_id ?? null,
  };
}

function isTradeJournalEntry(value: unknown): value is TradeJournalEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.id === "string"
    && typeof entry.date === "string"
    && (entry.stage === "Setup" || entry.stage === "Execution" || entry.stage === "Management" || entry.stage === "Exit")
    && typeof entry.emotion === "string"
    && typeof entry.note === "string";
}

async function loadBackendWorkspace(accountIds: string[] = []) {
  const scopes = accountIds.length ? accountIds.map((id) => `&account_id=${encodeURIComponent(id)}`) : [""];
  const [accountList, tradePages, planPages, preferences, tradingViewStatus] = await Promise.all([
    apiRequest<{ items: ApiAccount[] }>("/accounts?limit=100"),
    Promise.all(scopes.map((scope) => apiRequest<{ items: ApiTrade[] }>(`/trades?limit=100${scope}`))),
    Promise.all(scopes.map((scope) => apiRequest<{ items: ApiPlan[] }>(`/plans?limit=100${scope}`))),
    apiRequest<{ timezone: string }>("/preferences"),
    apiRequest<{ configured: boolean }>("/integrations/tradingview/token"),
  ]);
  const byNewest = <T extends { opened_at?: string; created_at?: string }>(a: T, b: T) =>
    (b.opened_at ?? b.created_at ?? "").localeCompare(a.opened_at ?? a.created_at ?? "");
  const tradeList = { items: tradePages.flatMap((page) => page.items).sort(byNewest) };
  const planList = { items: planPages.flatMap((page) => page.items).sort(byNewest) };
  const tradeRows = await Promise.all(tradeList.items.map(async (item) => {
    const [sections, review] = await Promise.all([
      apiRequest<ApiJournalSection[]>(`/trades/${item.id}/journal`),
      apiRequest<ApiReview>(`/trades/${item.id}/reviews`).catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }),
    ]);
    const timeline = sections.find((section) => section.section_key === "journal_entries");
    const entries = timeline?.content;
    const setup = sections.find((section) => section.section_key === "strategy_setup")?.content;
    const mapped = mapApiTrade(item);
    const setupNotes = recordField(setup, "setup_notes");
    const setupEmotion = recordField(setup, "setup_emotion");
    const stopLoss = recordField(setup, "stop_loss");
    const takeProfit = recordField(setup, "take_profit");
    mapped.setupNotes = typeof setupNotes === "string" ? setupNotes : "";
    mapped.setupEmotion = typeof setupEmotion === "string" ? setupEmotion : "Neutral";
    if (typeof stopLoss === "number") mapped.stopLoss = stopLoss;
    if (typeof takeProfit === "number") mapped.takeProfit = takeProfit;
    if (entries !== undefined) {
      if (!Array.isArray(entries) || !entries.every(isTradeJournalEntry)) {
        throw new Error(`Trade ${item.id} has an invalid saved journal timeline.`);
      }
      mapped.journalEntries = entries;
    }
    return {
      trade: mapped,
      review: review
        ? {
            tradeId: review.trade_id,
            planAdherence: review.plan_adherence,
            learning: review.learning,
            nextAction: review.next_action,
          }
        : null,
    };
  }));
  const accountRows: AccountSetup[] = await Promise.all(accountList.items.map(async (account) => {
    const [connection, positions] = await Promise.all([
      apiRequest<{ status: string; connector_type: string; last_error: string | null; balance: number | null; equity: number | null; currency: string }>(`/accounts/${account.id}/status`),
      apiRequest<unknown[]>(`/accounts/${account.id}/positions`),
    ]);
    return {
      id: account.id,
      name: account.name,
      provider: "MT5" as const,
      server: account.server_name ?? account.broker ?? "",
      loginId: account.external_account_id ?? "",
      connectorType: connection.connector_type,
      lastError: connection.last_error,
      status: connection.status,
      openPositions: positions.length,
      balance: connection.balance,
      equity: connection.equity,
      currency: connection.currency,
    };
  }));
  if (tradingViewStatus.configured) {
    accountRows.push({
      id: "tradingview-integration",
      name: "TradingView alerts",
      provider: "TradingView",
      server: "",
      loginId: "",
      status: "connected",
      openPositions: 0,
    });
  }
  return {
    accounts: accountRows,
    trades: [...tradeRows.map(({ trade }) => trade), ...planList.items.map(mapApiPlan)],
    reviews: tradeRows.flatMap(({ review }) => review ? [review] : []),
    timezone: isSupportedTimezone(preferences.timezone) ? preferences.timezone : "UTC",
  };
}

function connectionHint(account: AccountSetup): string {
  if (account.lastError) return account.lastError;
  if (account.connectorType === "ea") {
    if (account.status === "pending") return "Connecting… keep MetaTrader 5 open and logged into this account. This updates automatically.";
    if (account.status === "offline") return "No data received for over 10 minutes. Make sure MetaTrader 5 is open on your computer, or run the setup again.";
  }
  if (account.status === "pending" && account.connectorType === "mt5") {
    return "This account is on the legacy worker method. Disconnect, then Connect to use the current method.";
  }
  if (account.status === "provisioning" || account.status === "syncing") return "Connecting to your broker and importing data...";
  return "";
}

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true as const };
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></>,
    book: <><path d="M5 4.5h11a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3z" /><path d="M5 16.5a3 3 0 0 1 3-3h11M9 8h6M9 10.5h5" /></>,
    target: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><path d="m12 12 7-7m0 0h-4m4 0v4" /></>,
    check: <><path d="M7 4.5h10a2 2 0 0 1 2 2v13H5v-13a2 2 0 0 1 2-2Z" /><path d="M9 4.5v-1h6v1M8.5 11l2.1 2.1 5-5M8.5 17h7" /></>,
    chart: <><path d="M4 19.5h16M6.5 16V11M11 16V6M15.5 16V9M20 16V4" /></>,
    wallet: <><rect x="3.5" y="5.5" width="17" height="14" rx="2.5" /><path d="M3.5 9h17M15.5 14.5h2" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.3" /><path d="m15.5 15.5 4 4" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-2.5 7-2.5 8.5h17C20.5 16 18 16 18 9ZM10 21h4" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    arrow: <><path d="M5 12h14m-6-6 6 6-6 6" /></>,
    chevron: <><path d="m7 10 5 5 5-5" /></>,
    calendar: <><rect x="4" y="5.5" width="16" height="15" rx="2" /><path d="M8 3.5v4M16 3.5v4M4 10h16" /></>,
    filter: <><path d="M4 6h16M7 12h10m-7 6h4" /></>,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" /></>,
  };
  return <svg {...common}>{paths[name] ?? paths.grid}</svg>;
}

function formatMoney(value: number) {
  return `${value < 0 ? "−" : ""}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatTradeDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function matchesDateRange(value: string, range: DashboardDateRange) {
  if (range.preset === "all") return true;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return false;
  const key = localDateKey(date);
  return key >= range.startDate && key <= range.endDate;
}

function dashboardRangeLabel(range: DashboardDateRange) {
  if (range.preset === "all") return "All time";
  if (range.preset === "7d") return "Last 7 days";
  if (range.preset === "30d") return "Last 30 days";
  if (range.preset === "90d") return "Last 90 days";
  if (!range.startDate || !range.endDate) return "Custom range";
  const format = (value: string) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
  return `${format(range.startDate)} – ${format(range.endDate)}`;
}

function summarizeTrades(trades: Trade[]) {
  const closed = trades.filter((trade) => (trade.outcome === "Win" || trade.outcome === "Loss" || trade.outcome === "Flat") && trade.pnl !== null);
  const wins = closed.filter((trade) => (trade.pnl ?? 0) > 0);
  const losses = closed.filter((trade) => (trade.pnl ?? 0) < 0);
  const grossProfit = wins.reduce((total, trade) => total + (trade.pnl ?? 0), 0);
  const grossLoss = Math.abs(losses.reduce((total, trade) => total + (trade.pnl ?? 0), 0));
  const netPnl = closed.reduce((total, trade) => total + (trade.pnl ?? 0), 0);
  const rValues = closed.flatMap((trade) => trade.rMultiple === null ? [] : [trade.rMultiple]);
  return {
    closed,
    wins,
    losses,
    netPnl,
    profitFactor: grossLoss === 0 ? null : grossProfit / grossLoss,
    winRate: closed.length ? (wins.length / closed.length) * 100 : 0,
    averageR: rValues.length ? rValues.reduce((total, value) => total + value, 0) / rValues.length : null,
  };
}

function cumulativePnlValues(trades: Trade[]) {
  const values: number[] = [];
  let total = 0;
  for (const trade of trades) {
    total += trade.pnl ?? 0;
    values.push(total);
  }
  return values;
}

function csvEscape(value: string | number | null | undefined) {
  let text = value === null || value === undefined ? "" : String(value);
  if (typeof value === "string" && /^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

const csvColumns = ["id", "symbol", "direction", "strategy", "date", "outcome", "pnl", "rMultiple", "entryPrice", "stopLoss", "takeProfit", "exitPrice", "size", "source", "plan", "setupNotes", "setupEmotion", "journalEntries", "reviewPlanAdherence", "reviewLearning", "reviewNextAction"] as const;

function exportTradesCsv(trades: Trade[], reviews: TradeReview[]) {
  const reviewsByTrade = new Map(reviews.map((review) => [review.tradeId, review]));
  const csv = [csvColumns.join(","), ...trades.map((trade) => {
    const review = reviewsByTrade.get(trade.id);
    const values: Record<(typeof csvColumns)[number], string | number | null | undefined> = {
      id: trade.id,
      symbol: trade.symbol,
      direction: trade.direction,
      strategy: trade.strategy,
      date: trade.date,
      outcome: trade.outcome,
      pnl: trade.pnl,
      rMultiple: trade.rMultiple,
      entryPrice: trade.entryPrice,
      stopLoss: trade.stopLoss,
      takeProfit: trade.takeProfit,
      exitPrice: trade.exitPrice,
      size: trade.size,
      source: trade.source,
      plan: trade.plan,
      setupNotes: trade.setupNotes,
      setupEmotion: trade.setupEmotion,
      journalEntries: JSON.stringify(trade.journalEntries ?? []),
      reviewPlanAdherence: review?.planAdherence,
      reviewLearning: review?.learning,
      reviewNextAction: review?.nextAction,
    };
    return csvColumns.map((column) => csvEscape(values[column])).join(",");
  })].join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `tradeiq-journal-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function parseCsvRows(text: string) {
  const input = text.replace(/^\uFEFF/, "");
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < input.length; index += 1) {
    const character = input[index];
    if (quoted) {
      if (character === '"' && input[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        cell += character;
      }
    } else if (character === '"' && cell.length === 0) {
      quoted = true;
    } else if (character === ",") {
      row.push(cell);
      cell = "";
    } else if (character === "\n" || character === "\r") {
      if (character === "\r" && input[index + 1] === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += character;
    }
  }

  if (quoted) throw new Error("CSV contains an unclosed quoted field.");
  row.push(cell);
  if (row.some((value) => value.length > 0)) rows.push(row);
  return rows;
}

function importTradesCsv(text: string) {
  const rows = parseCsvRows(text);
  if (rows.length < 2) throw new Error("CSV must contain a header and at least one trade row.");
  const headers = rows[0].map((header) => header.trim());
  const required = ["id", "symbol", "direction", "strategy", "date", "outcome", "pnl", "rMultiple", "plan"];
  const headerIndex = new Map(headers.map((header, index) => [header, index]));
  const missing = required.filter((header) => !headerIndex.has(header));
  if (missing.length) throw new Error(`CSV is missing required columns: ${missing.join(", ")}.`);
  const field = (row: string[], name: string) => row[headerIndex.get(name) ?? -1] ?? "";
  const numberField = (row: string[], name: string, rowNumber: number) => {
    const raw = field(row, name);
    if (raw === "") return null;
    const value = Number(raw);
    if (!Number.isFinite(value)) throw new Error(`Row ${rowNumber}: ${name} must be a valid number.`);
    return value;
  };
  const outcomes: TradeOutcome[] = ["Win", "Loss", "Flat", "Open", "Planned", "Discarded"];
  const trades: Trade[] = [];
  const reviews: TradeReview[] = [];
  const seenIds = new Set<string>();
  for (const [index, row] of rows.slice(1).entries()) {
    const rowNumber = index + 2;
    const id = field(row, "id").trim();
    const symbol = field(row, "symbol").trim().toUpperCase();
    const direction = field(row, "direction");
    const strategy = field(row, "strategy").trim();
    const date = field(row, "date").trim();
    const outcome = field(row, "outcome") as TradeOutcome;
    const plan = field(row, "plan");
    if (!id || !symbol || !strategy || !plan || !Number.isFinite(Date.parse(date))) throw new Error(`Row ${rowNumber}: id, symbol, strategy, a valid date, and plan are required.`);
    if (seenIds.has(id)) throw new Error(`Row ${rowNumber}: duplicate trade ID "${id}".`);
    seenIds.add(id);
    if (direction !== "Long" && direction !== "Short") throw new Error(`Row ${rowNumber}: direction must be Long or Short.`);
    if (!outcomes.includes(outcome)) throw new Error(`Row ${rowNumber}: unsupported trade outcome.`);
    const pnl = numberField(row, "pnl", rowNumber);
    const rMultiple = numberField(row, "rMultiple", rowNumber);
    const entryPrice = numberField(row, "entryPrice", rowNumber);
    const stopLoss = numberField(row, "stopLoss", rowNumber);
    const takeProfit = numberField(row, "takeProfit", rowNumber);
    const exitPrice = numberField(row, "exitPrice", rowNumber);
    const size = numberField(row, "size", rowNumber);
    if (outcome === "Win" && (pnl === null || pnl <= 0)) throw new Error(`Row ${rowNumber}: a win must have positive realized P&L.`);
    if (outcome === "Loss" && (pnl === null || pnl >= 0)) throw new Error(`Row ${rowNumber}: a loss must have negative realized P&L.`);
    if (outcome === "Flat" && pnl !== 0) throw new Error(`Row ${rowNumber}: a flat result must have zero realized P&L.`);
    if ((outcome === "Open" || outcome === "Planned" || outcome === "Discarded") && pnl !== null) throw new Error(`Row ${rowNumber}: ${outcome.toLowerCase()} records cannot contain realized P&L.`);
    if ([entryPrice, stopLoss, takeProfit, exitPrice, size].some((value) => value !== null && value <= 0)) throw new Error(`Row ${rowNumber}: prices and position size must be positive.`);
    const sourceValue = field(row, "source");
    if (sourceValue && sourceValue !== "demo" && sourceValue !== "manual" && sourceValue !== "mt5") throw new Error(`Row ${rowNumber}: unsupported source type.`);
    const source: Trade["source"] = sourceValue === "demo" || sourceValue === "manual" || sourceValue === "mt5" ? sourceValue : "manual";
    let journalEntries: TradeJournalEntry[] = [];
    const rawJournalEntries = field(row, "journalEntries");
    if (rawJournalEntries) {
      try {
        const parsed: unknown = JSON.parse(rawJournalEntries);
        if (!Array.isArray(parsed) || parsed.some((entry) => !entry || typeof entry.id !== "string" || typeof entry.date !== "string" || !["Setup", "Execution", "Management", "Exit"].includes(entry.stage) || typeof entry.emotion !== "string" || typeof entry.note !== "string")) {
          throw new Error("Journal timeline must be a list of valid timestamped entries.");
        }
        journalEntries = parsed as TradeJournalEntry[];
      } catch (error) {
        throw new Error(`Row ${rowNumber}: invalid journal timeline${error instanceof Error ? ` (${error.message})` : ""}.`);
      }
    }
    trades.push({
      id, symbol, direction, strategy, date, outcome, pnl, rMultiple, entryPrice, stopLoss, takeProfit, exitPrice, size, source, plan,
      setupNotes: field(row, "setupNotes"),
      setupEmotion: field(row, "setupEmotion") || undefined,
      journalEntries,
    });
    const adherence = field(row, "reviewPlanAdherence");
    const learning = field(row, "reviewLearning");
    const nextAction = field(row, "reviewNextAction");
    if (adherence || learning || nextAction) {
      if (adherence !== "yes" && adherence !== "partly" && adherence !== "no") throw new Error(`Row ${rowNumber}: review plan adherence must be yes, partly, or no.`);
      if (!learning.trim() || !nextAction.trim()) throw new Error(`Row ${rowNumber}: completed reviews need learning and next-action fields.`);
      if (outcome !== "Win" && outcome !== "Loss" && outcome !== "Flat") throw new Error(`Row ${rowNumber}: only closed trades can include reviews.`);
      reviews.push({ tradeId: id, planAdherence: adherence, learning, nextAction });
    }
  }
  if (!trades.length) throw new Error("CSV contains no trade records.");
  return { trades, reviews };
}

function AppLogo() {
  return (
    <div className="brand-lockup">
      <div className="brand-mark"><Image src="/brand-mark.jpg" alt="" width={36} height={36} priority /></div>
      <div><strong>TradeIQ</strong><span>JOURNAL</span></div>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: TradeOutcome }) {
  return <span className={`outcome-badge outcome-${outcome.toLowerCase()}`}><i />{outcome}</span>;
}

function TradeTable({ trades, compact = false, onManageTrade, selected, onToggleSelect }: { trades: Trade[]; compact?: boolean; onManageTrade?: (trade: Trade) => void; selected?: string[]; onToggleSelect?: (id: string) => void }) {
  const visibleTrades = compact ? trades.slice(0, 4) : trades;
  return (
    <div className="table-scroll">
      <table className="trade-table">
        <thead><tr>{onToggleSelect && <th><span className="sr-only">Select</span></th>}<th>Instrument</th><th>Strategy</th><th>Time</th><th>Outcome</th><th className="align-right">P&amp;L</th>{onManageTrade && <th><span className="sr-only">Journal actions</span></th>}</tr></thead>
        <tbody>
          {visibleTrades.map((trade) => (
            <tr key={trade.id}>
              {onToggleSelect && <td><input type="checkbox" aria-label={`Select ${trade.symbol} ${trade.id}`} checked={selected?.includes(trade.id) ?? false} onChange={() => onToggleSelect(trade.id)} /></td>}
              <td><div className="instrument-cell"><span className={`direction-dot ${trade.direction.toLowerCase()}`} /> <div><strong>{trade.symbol}</strong><small>{trade.direction} · {trade.id}</small></div></div></td>
              <td className="muted-cell">{trade.strategy}</td>
              <td className="muted-cell">{formatTradeDate(trade.date)}</td>
              <td><OutcomeBadge outcome={trade.outcome} /></td>
              <td className={`align-right pnl-cell ${trade.pnl === null ? "" : trade.pnl >= 0 ? "positive" : "negative"}`}>{trade.pnl === null ? "—" : formatMoney(trade.pnl)}</td>
              {onManageTrade && <td><button className="button button-outline table-journal-button" onClick={() => onManageTrade(trade)}>{trade.outcome === "Open" ? "Update trade" : "Journal"}</button></td>}
            </tr>
          ))}
        </tbody>
      </table>
      {!visibleTrades.length && <div className="empty-state">No trades match this search. Try a different symbol or filter.</div>}
    </div>
  );
}

function BulkBar({ trades, strategy, busy, askOpen, onStrategy, onAsk, onClear, onApply, onRemove }: { trades: Trade[]; strategy: string; busy: boolean; askOpen: boolean; onStrategy: (value: string) => void; onAsk: () => void; onClear: () => void; onApply: () => void; onRemove: (mode: "delete" | "clear") => void }) {
  const closed = trades.filter((trade) => trade.pnl !== null);
  const rs = trades.map((trade) => trade.rMultiple).filter((value): value is number => typeof value === "number");
  const wins = closed.filter((trade) => (trade.pnl ?? 0) > 0).length;
  const net = closed.reduce((sum, trade) => sum + (trade.pnl ?? 0), 0);
  const byStrategy = trades.reduce<Record<string, number>>((acc, trade) => ({ ...acc, [trade.strategy]: (acc[trade.strategy] ?? 0) + 1 }), {});
  return (
    <div className="bulk-bar">
      <div className="bulk-actions">
        <strong>{trades.length} selected</strong>
        <input aria-label="Strategy for selected trades" placeholder="Set strategy / setup tag" value={strategy} maxLength={120} onChange={(event) => onStrategy(event.target.value)} />
        <button className="button" disabled={busy || !strategy.trim()} onClick={onApply}>{busy ? "Applying…" : "Apply tag"}</button>
        <button className="button button-outline" onClick={onAsk}>Ask Agent about these trades</button>
        <button className="button button-outline" onClick={onClear}>Clear</button>
      </div>
      <div className="bulk-actions bulk-danger" role="group" aria-label="Remove selected trades or journals">
        <span>Remove</span>
        <button className="button button-outline" disabled={busy} onClick={() => onRemove("clear")}>Clear journal notes</button>
        <button className="button button-danger" disabled={busy} onClick={() => onRemove("delete")}>Delete trades</button>
      </div>
      {askOpen && (
        <div className="bulk-summary">
          <p><strong>{closed.length}</strong> closed of {trades.length} selected · {closed.length ? `${wins} wins (${Math.round((wins / closed.length) * 100)}%)` : "no closed trades"} · net {formatMoney(net)} (mixed currencies are not converted).</p>
          <p>{rs.length ? `Recorded R on ${rs.length} trades: average ${(rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2)}R, total ${rs.reduce((a, b) => a + b, 0).toFixed(2)}R.` : "No R-multiples recorded for these trades."}</p>
          <p>Strategies: {Object.entries(byStrategy).map(([name, count]) => `${name} (${count})`).join(", ")}.</p>
          <small>{closed.length < 30 ? "Small sample: treat this as description, not evidence of edge." : "Descriptive summary of your own selection; it does not show causation."}</small>
        </div>
      )}
    </div>
  );
}

function PerformanceChart({ period, trades, showDrawdown = false, unit = "money" }: { period: string; trades: Trade[]; showDrawdown?: boolean; unit?: "money" | "r" }) {
  const days = period === "7D" ? 7 : period === "90D" ? 90 : 30;
  const allClosedTrades = trades.filter((trade) => (trade.outcome === "Win" || trade.outcome === "Loss" || trade.outcome === "Flat") && trade.pnl !== null);
  const latestTradeTime = allClosedTrades.reduce((latest, trade) => Math.max(latest, Date.parse(trade.date)), 0);
  const cutoff = latestTradeTime - days * 24 * 60 * 60 * 1000;
  const closedTrades = allClosedTrades
    .filter((trade) => Number.isFinite(Date.parse(trade.date)) && (period === "ALL" || Date.parse(trade.date) >= cutoff))
    .slice()
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  const values = cumulativePnlValues(closedTrades);
  const rangeMin = Math.min(0, ...values);
  const rangeMax = Math.max(0, ...values);
  const range = rangeMax - rangeMin || 1;
  const pointValues = values.length ? values : [0];
  const points = pointValues.map((value, index) => {
    const x = pointValues.length === 1 ? 50 : (index / (pointValues.length - 1)) * 100;
    const y = 90 - ((value - rangeMin) / range) * 80;
    return `${x},${y}`;
  }).join(" ");
  const toY = (value: number) => 90 - ((value - rangeMin) / range) * 80;
  const toX = (index: number) => (pointValues.length === 1 ? 50 : (index / (pointValues.length - 1)) * 100);
  const peaks = pointValues.reduce<number[]>((acc, value) => [...acc, Math.max(acc.at(-1) ?? 0, value)], []);
  const underwater = pointValues.reduce<number[][]>((segments, value, index) => {
    if (value >= peaks[index]) return [...segments, []];
    const last = segments.length ? segments[segments.length - 1] : [];
    return [...segments.slice(0, -1), [...last, index]];
  }, [[]]).filter((segment) => segment.length > 0);
  const shadePolygons = showDrawdown ? underwater.map((segment) => {
    const lower = segment.map((index) => `${toX(index)},${toY(pointValues[index])}`);
    const upper = [...segment].reverse().map((index) => `${toX(index)},${toY(peaks[index])}`);
    return [...lower, ...upper].join(" ");
  }) : [];
  const drawdowns = pointValues.map((value, index) => peaks[index] - value);
  const deepest = drawdowns.reduce((best, value, index) => (value > drawdowns[best] ? index : best), 0);
  const bestIndex = closedTrades.reduce((best, trade, index) => ((trade.pnl ?? 0) > (closedTrades[best].pnl ?? 0) ? index : best), 0);
  const fmtValue = (value: number) => (unit === "r" ? fmtR(value) : formatMoney(value));
  const annotations = closedTrades.length > 2 ? [
    drawdowns[deepest] > 0 ? { key: "dd", index: deepest, label: `Deepest drawdown: ${fmtValue(-drawdowns[deepest])} below peak (${formatTradeDate(closedTrades[deepest].date)})`, tone: "negative" } : null,
    (closedTrades[bestIndex].pnl ?? 0) > 0 ? { key: "best", index: bestIndex, label: `Best single trade: ${closedTrades[bestIndex].symbol} ${fmtValue(closedTrades[bestIndex].pnl ?? 0)} (${formatTradeDate(closedTrades[bestIndex].date)})`, tone: "positive" } : null,
  ].filter((item): item is { key: string; index: number; label: string; tone: string } => item !== null) : [];
  const zeroY = 90 - ((0 - rangeMin) / range) * 80;
  const areaPoints = `0,${zeroY} ${points} 100,${zeroY}`;
  const firstDate = closedTrades.length ? formatTradeDate(closedTrades[0].date) : "No closed trades";
  const lastDate = closedTrades.length ? formatTradeDate(closedTrades[closedTrades.length - 1].date) : "";
  return (
    <div className="chart-wrap" role="img" aria-label={period === "ALL" ? "Cumulative recorded P and L for the selected date range" : `Cumulative recorded P and L for the last ${period}`}>
      <div className="chart-y-labels"><span>{formatMoney(rangeMax)}</span><span>{formatMoney(rangeMax * .66)}</span><span>{formatMoney(rangeMax * .33)}</span><span>{formatMoney(rangeMin)}</span></div>
      <div className="chart-canvas">
        <div className="chart-grid"><span /><span /><span /><span /></div>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs><linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#c59a48" stopOpacity=".23" /><stop offset="100%" stopColor="#c59a48" stopOpacity="0" /></linearGradient></defs>
          <polygon points={areaPoints} fill="url(#chart-fill)" />
          {shadePolygons.map((polygon, index) => <polygon key={index} points={polygon} className="chart-drawdown-shade" />)}
          <polyline points={points} fill="none" stroke="#bd9142" strokeWidth="1.35" vectorEffect="non-scaling-stroke" />
        </svg>
        {annotations.map((item) => <span key={item.key} className={`chart-annotation ${item.tone}`} style={{ left: `${toX(item.index)}%`, top: `${toY(pointValues[item.index])}%` }} title={item.label} tabIndex={0} role="note" aria-label={item.label} />)}
        <div className="chart-x-labels"><span>{firstDate}</span><span>{lastDate}</span></div>
      </div>
    </div>
  );
}

function isSupportedTimezone(value: string) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value });
    return true;
  } catch {
    return false;
  }
}

function QuickCaptureModal({ onClose, onSave }: { onClose: () => void; onSave: (trade: Trade) => void }) {
  const [symbol, setSymbol] = useDraftState("capture", "symbol", "");
  const [direction, setDirection] = useDraftState<"Long" | "Short">("capture", "direction", "Long");
  const [strategy, setStrategy] = useDraftState("capture", "strategy", "");
  const [plan, setPlan] = useDraftState("capture", "plan", "");
  const [setupNotes, setSetupNotes] = useDraftState("capture", "setupNotes", "");
  const [setupEmotion, setSetupEmotion] = useDraftState("capture", "setupEmotion", "Neutral");
  const [error, setError] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!symbol.trim() || !plan.trim()) {
      setError("Add an instrument and a brief plan before saving.");
      return;
    }
    const date = new Date().toISOString();
    const tradeId = `PLAN-${Date.now().toString().slice(-5)}`;
    const initialEntry: TradeJournalEntry = {
      id: `${tradeId}-SETUP`,
      date,
      stage: "Setup",
      emotion: setupEmotion,
      note: setupNotes.trim() || plan.trim(),
    };
    onSave({
      id: tradeId,
      symbol: symbol.trim().toUpperCase(),
      direction,
      strategy: strategy.trim() || "Uncategorized",
      date,
      outcome: "Planned",
      pnl: null,
      rMultiple: null,
      plan: plan.trim(),
      setupNotes: setupNotes.trim(),
      setupEmotion,
      journalEntries: [initialEntry],
      source: "manual",
    });
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="capture-modal" role="dialog" aria-modal="true" aria-labelledby="capture-title">
        <div className="modal-heading"><div><span className="eyebrow">DECISION CAPTURE</span><h2 id="capture-title">Create a trade plan</h2><p>Record your intent before any execution. No exposure is implied.</p></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close" /></button></div>
        <form onSubmit={submit}>
          <div className="form-row">
            <label>Instrument<input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="e.g. XAUUSD" autoFocus /></label>
            <label>Direction<select value={direction} onChange={(event) => setDirection(event.target.value as "Long" | "Short")}><option>Long</option><option>Short</option></select></label>
          </div>
          <label>Strategy <span className="optional-label">Optional</span><input value={strategy} onChange={(event) => setStrategy(event.target.value)} placeholder="e.g. London breakout" /></label>
          <label>Trade setup<textarea value={setupNotes} onChange={(event) => setSetupNotes(event.target.value)} placeholder="Describe the setup, market context, and why it fits your strategy..." rows={3} /></label>
          <label>What is the plan?<textarea value={plan} onChange={(event) => setPlan(event.target.value)} placeholder="Entry idea, trigger, invalidation, and risk..." rows={4} /></label>
          <label>How are you feeling before the trade?<select value={setupEmotion} onChange={(event) => setSetupEmotion(event.target.value)}><option>Neutral</option><option>Calm</option><option>Confident</option><option>Anxious</option><option>Fearful</option><option>Frustrated</option><option>Excited</option><option>Other</option></select></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="form-note"><Icon name="check" size={16} /><span>Your plan will be time-stamped and kept separate from terminal facts.</span></div>
          <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button type="submit" className="button button-primary">Save plan <Icon name="arrow" size={16} /></button></div>
        </form>
      </section>
    </div>
  );
}

function ExecutionModal({ plan, serverErrors, onClose, onSave }: { plan: Trade; serverErrors: Record<string, string>; onClose: () => void; onSave: (trade: Trade) => void }) {
  const isPlanned = plan.outcome === "Planned";
  const wasClosed = plan.outcome === "Win" || plan.outcome === "Loss" || plan.outcome === "Flat";
  const draft = `exec.${plan.id}`;
  const [entryPrice, setEntryPrice] = useDraftState(draft, "entryPrice", plan.entryPrice?.toString() ?? "");
  const [stopLoss, setStopLoss] = useDraftState(draft, "stopLoss", plan.stopLoss?.toString() ?? "");
  const [takeProfit, setTakeProfit] = useDraftState(draft, "takeProfit", plan.takeProfit?.toString() ?? "");
  const [exitPrice, setExitPrice] = useDraftState(draft, "exitPrice", plan.exitPrice?.toString() ?? "");
  const [size, setSize] = useDraftState(draft, "size", plan.size?.toString() ?? "");
  const [pnl, setPnl] = useDraftState(draft, "pnl", plan.pnl?.toString() ?? "");
  const [rMultiple, setRMultiple] = useDraftState(draft, "rMultiple", plan.rMultiple?.toString() ?? "");
  const [setupNotes, setSetupNotes] = useDraftState(draft, "setupNotes", plan.setupNotes ?? "");
  const [setupEmotion, setSetupEmotion] = useDraftState(draft, "setupEmotion", plan.setupEmotion ?? "Neutral");
  const [stage, setStage] = useDraftState<TradeJournalEntry["stage"]>(draft, "stage", isPlanned ? "Execution" : wasClosed ? "Exit" : "Management");
  const [emotion, setEmotion] = useDraftState(draft, "emotion", "Neutral");
  const [journalNote, setJournalNote] = useDraftState(draft, "journalNote", "");
  const [isClosedDraft, setIsClosedDraft] = useDraftState<"yes" | "no">(draft, "isClosed", wasClosed ? "yes" : "no");
  const isClosed = isClosedDraft === "yes";
  const setIsClosed = (value: boolean) => setIsClosedDraft(value ? "yes" : "no");
  const [setupName, setSetupName] = useDraftState(draft, "setupName", plan.setupName ?? "");
  const [maeR, setMaeR] = useDraftState(draft, "maeR", plan.maeR?.toString() ?? "");
  const [mfeR, setMfeR] = useDraftState(draft, "mfeR", plan.mfeR?.toString() ?? "");
  const [emotionalState, setEmotionalState] = useDraftState(draft, "emotionalState", plan.emotionalState ?? "");
  const [confluences, setConfluences] = useDraftState(draft, "confluences", (plan.confluences ?? []).join(", "));
  const [ruleBreaks, setRuleBreaks] = useDraftState(draft, "ruleBreaks", (plan.ruleBreaks ?? []).join(", "));
  const [error, setError] = useState("");
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});
  const fieldErrors = { ...serverErrors, ...localErrors };
  const fieldError = (name: string) => fieldErrors[name] ? <span className="form-error" role="alert">{fieldErrors[name]}</span> : null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const labelLimit = (value: string, name: string) => value.split(",").some((item) => item.trim().length > 120) ? { [name]: "Each item must be 120 characters or fewer; separate items with commas." } : {};
    const found = { ...labelLimit(confluences, "confluences"), ...labelLimit(ruleBreaks, "rule_breaks") };
    setLocalErrors(found);
    if (Object.keys(found).length) return;
    const parsedEntry = entryPrice.trim() ? Number(entryPrice) : null;
    const parsedSize = size.trim() ? Number(size) : null;
    const parsedStopLoss = stopLoss.trim() ? Number(stopLoss) : null;
    const parsedTakeProfit = takeProfit.trim() ? Number(takeProfit) : null;
    const parsedPnl = Number(pnl);
    const parsedR = rMultiple === "" ? null : Number(rMultiple);
    const parsedExit = exitPrice.trim() ? Number(exitPrice) : null;
    if (isPlanned && (parsedEntry === null || !Number.isFinite(parsedEntry) || parsedEntry <= 0 || parsedSize === null || !Number.isFinite(parsedSize) || parsedSize <= 0)) {
      setError("Enter a positive average fill price and position size.");
      return;
    }
    if (isClosed && (pnl.trim() === "" || !Number.isFinite(parsedPnl))) {
      setError("Enter the realized P&L reported by your broker for a closed trade.");
      return;
    }
    if (parsedExit !== null && (!Number.isFinite(parsedExit) || parsedExit <= 0)) {
      setError("Exit price must be a positive number.");
      return;
    }
    if ([parsedEntry, parsedSize, parsedStopLoss, parsedTakeProfit].some((value) => value !== null && (!Number.isFinite(value) || value <= 0))) {
      setError("Entry, position size, stop loss, and take profit must be positive numbers.");
      return;
    }
    if (parsedR !== null && !Number.isFinite(parsedR)) {
      setError("R multiple must be a valid number.");
      return;
    }
    const parsedMae = maeR.trim() ? Number(maeR) : null;
    const parsedMfe = mfeR.trim() ? Number(mfeR) : null;
    if ([parsedMae, parsedMfe].some((value) => value !== null && (!Number.isFinite(value) || value < 0))) {
      setError("MAE and MFE must be zero or positive R values.");
      return;
    }
    const splitList = (value: string) => Array.from(new Set(value.split(",").map((item) => item.trim()).filter(Boolean))).slice(0, 30);
    const date = new Date().toISOString();
    const outcome: TradeOutcome = wasClosed ? parsedPnl > 0 ? "Win" : parsedPnl < 0 ? "Loss" : "Flat" : !isClosed ? "Open" : parsedPnl > 0 ? "Win" : parsedPnl < 0 ? "Loss" : "Flat";
    const journalEntry: TradeJournalEntry = {
      id: `${plan.id}-${Date.now()}`,
      date,
      stage: isClosed ? "Exit" : stage,
      emotion,
      note: journalNote.trim(),
    };
    onSave({
      ...plan,
      outcome,
      pnl: isClosed ? parsedPnl : null,
      rMultiple: isClosed ? parsedR ?? plan.rMultiple ?? null : null,
      entryPrice: parsedEntry ?? plan.entryPrice ?? null,
      stopLoss: parsedStopLoss ?? plan.stopLoss ?? null,
      takeProfit: parsedTakeProfit ?? plan.takeProfit ?? null,
      exitPrice: parsedExit ?? plan.exitPrice ?? null,
      size: parsedSize ?? plan.size ?? null,
      setupNotes: setupNotes.trim(),
      setupEmotion,
      setupName: setupName.trim(),
      maeR: parsedMae,
      mfeR: parsedMfe,
      emotionalState: emotionalState.trim() || null,
      confluences: splitList(confluences),
      ruleBreaks: splitList(ruleBreaks),
      journalEntries: [...(plan.journalEntries ?? []), journalEntry],
      source: plan.source === "mt5" ? "mt5" : "manual",
    });
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="capture-modal trade-journal-modal" role="dialog" aria-modal="true" aria-labelledby="execution-title">
    <div className="modal-heading"><div><span className="eyebrow">TRADE JOURNAL · {plan.source === "mt5" ? "BROKER-SYNCED" : "MANUAL ENTRY"}</span><h2 id="execution-title">{isPlanned ? `Record ${plan.symbol} fill` : `Journal ${plan.symbol} trade`}</h2><p>{plan.source === "mt5" ? "Imported execution facts are read-only. Your notes and review remain editable." : "Record setup, emotion, and execution details in your account."}</p></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close" /></button></div>
    <div className="execution-plan"><span>{isPlanned ? "PRE-TRADE PLAN" : `CURRENT STATUS · ${plan.outcome.toUpperCase()}`}</span><p>{plan.plan}</p></div>
    <form onSubmit={submit}>
      <label>Trade setup<textarea value={setupNotes} onChange={(event) => setSetupNotes(event.target.value)} placeholder="Market context, setup confirmation, and what would invalidate it..." rows={2} /></label>
      <div className="form-row"><label>Setup emotion<select value={setupEmotion} onChange={(event) => setSetupEmotion(event.target.value)}><option>Neutral</option><option>Calm</option><option>Confident</option><option>Anxious</option><option>Fearful</option><option>Frustrated</option><option>Excited</option><option>Other</option></select></label><label>Position size<input disabled={plan.source === "mt5"} inputMode="decimal" value={size} onChange={(event) => setSize(event.target.value)} placeholder="e.g. 0.10 lots" />{fieldError("size")}</label></div>
      <div className="form-row"><label>Average fill price<input disabled={plan.source === "mt5"} inputMode="decimal" value={entryPrice} onChange={(event) => setEntryPrice(event.target.value)} placeholder="e.g. 2348.50" />{fieldError("entry_price")}</label><label>Stop loss<input disabled={plan.source === "mt5"} inputMode="decimal" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)} placeholder="Optional" />{fieldError("stop_loss")}</label></div>
      <div className="form-row"><label>Take profit<input disabled={plan.source === "mt5"} inputMode="decimal" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} placeholder="Optional" />{fieldError("take_profit")}</label>{!wasClosed && <label>Journal stage<select value={stage} onChange={(event) => setStage(event.target.value as TradeJournalEntry["stage"])}><option>Execution</option><option>Management</option><option>Exit</option></select></label>}</div>
      {!wasClosed && plan.source !== "mt5" && <label className="checkbox-label"><input type="checkbox" checked={isClosed} onChange={(event) => setIsClosed(event.target.checked)} /> This exposure is closed</label>}
      {isClosed && <div className="form-row"><label>{plan.source === "mt5" ? "Broker-reported realized P&L" : "Realized P&L"}<input disabled={plan.source === "mt5"} inputMode="decimal" value={pnl} onChange={(event) => setPnl(event.target.value)} placeholder="e.g. 120.00 or -45.00" /></label><label>Exit price <span className="optional-label">Optional</span><input disabled={plan.source === "mt5"} inputMode="decimal" value={exitPrice} onChange={(event) => setExitPrice(event.target.value)} placeholder="e.g. 2353.10" /></label></div>}
      {isClosed && <label>Outcome in R <span className="optional-label">Optional</span><input disabled={plan.source === "mt5"} inputMode="decimal" value={rMultiple} onChange={(event) => setRMultiple(event.target.value)} placeholder="e.g. 1.5" /></label>}
      <div className="v2-context-fields"><span className="custom-range-label">Performance Agent context</span><div className="form-note v2-optional-note"><Icon name="check" size={16} /><span><strong>Optional.</strong> These fields unlock setup, behavior and exit-efficiency analytics from your own trades.</span></div>
        <div className="form-row"><label>Setup name<input value={setupName} onChange={(event) => setSetupName(event.target.value)} maxLength={120} placeholder="e.g. London sweep reclaim" />{fieldError("setup")}</label><label>Emotional state<select value={emotionalState} onChange={(event) => setEmotionalState(event.target.value)}><option value="">Not recorded</option><option>Calm</option><option>Confident</option><option>Neutral</option><option>Anxious</option><option>Fearful</option><option>Frustrated</option><option>Excited</option><option>Revenge</option><option>FOMO</option></select></label></div>
        <div className="form-row"><label>MAE (R) <span className="optional-label">Optional</span><input inputMode="decimal" value={maeR} onChange={(event) => setMaeR(event.target.value)} placeholder="Max adverse, e.g. 0.6" />{fieldError("mae_r")}</label><label>MFE (R) <span className="optional-label">Optional</span><input inputMode="decimal" value={mfeR} onChange={(event) => setMfeR(event.target.value)} placeholder="Max favorable, e.g. 2.1" />{fieldError("mfe_r")}</label></div>
        <div className="form-row"><label>Confluences<input value={confluences} onChange={(event) => setConfluences(event.target.value)} placeholder="Comma-separated, e.g. HTF trend, FVG" />{fieldError("confluences")}</label><label>Rule breaks<input value={ruleBreaks} onChange={(event) => setRuleBreaks(event.target.value)} placeholder="Comma-separated, e.g. moved stop" />{fieldError("rule_breaks")}</label></div>
      </div>
      <div className="journal-entry-fields"><span className="custom-range-label">Add a time-stamped journal update</span><div className="form-row"><label>How are you feeling now?<select value={emotion} onChange={(event) => setEmotion(event.target.value)}><option>Neutral</option><option>Calm</option><option>Confident</option><option>Anxious</option><option>Fearful</option><option>Frustrated</option><option>Excited</option><option>Other</option></select></label><label>What is happening?<textarea value={journalNote} onChange={(event) => setJournalNote(event.target.value)} placeholder="Describe your execution, emotion, or management decision..." rows={2} /></label></div></div>
      {(plan.journalEntries ?? []).length > 0 && <div className="journal-timeline"><span className="custom-range-label">Journal timeline</span>{plan.journalEntries?.slice().reverse().map((entry) => <article className="journal-timeline-entry" key={entry.id}><strong>{entry.stage} · {entry.emotion}</strong><time>{formatTradeDate(entry.date)}</time>{entry.note && <p>{entry.note}</p>}</article>)}</div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-note"><Icon name="check" size={16} /><span>{plan.source === "mt5" ? "Broker facts remain unchanged; only journal notes are sent to the API." : isClosed ? "Closed status is retained. Realized P&L remains user-entered and unverified." : "An executed fill stays open until you explicitly close it with realized P&L."}</span></div>
      <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button type="submit" className="button button-primary">{isPlanned ? "Record fill" : wasClosed ? "Save journal update" : isClosed ? "Close trade & save" : "Save trade update"} <Icon name="arrow" size={16} /></button></div>
    </form>
  </section></div>;
}

function isWorkspace(value: unknown): value is SavedWorkspace {
  if (!value || typeof value !== "object") return false;
  const workspace = value as Partial<SavedWorkspace>;
  if (workspace.version !== 1 || !Array.isArray(workspace.trades) || !Array.isArray(workspace.reviews)) return false;
  if (workspace.timezone !== undefined && typeof workspace.timezone !== "string") return false;
  const validOutcomes: TradeOutcome[] = ["Win", "Loss", "Flat", "Open", "Planned", "Discarded"];
  const validTrades = workspace.trades.every((trade) =>
    trade && typeof trade.id === "string" &&
    typeof trade.symbol === "string" &&
    (trade.direction === "Long" || trade.direction === "Short") &&
    typeof trade.strategy === "string" && typeof trade.date === "string" &&
    validOutcomes.includes(trade.outcome) &&
    (trade.pnl === null || typeof trade.pnl === "number") &&
    (trade.rMultiple === null || typeof trade.rMultiple === "number") &&
    typeof trade.plan === "string" &&
    (trade.setupNotes === undefined || typeof trade.setupNotes === "string") &&
    (trade.setupEmotion === undefined || typeof trade.setupEmotion === "string") &&
    [trade.entryPrice, trade.stopLoss, trade.takeProfit, trade.exitPrice, trade.size].every((value) => value === undefined || value === null || typeof value === "number") &&
    (trade.journalEntries === undefined || Array.isArray(trade.journalEntries) && trade.journalEntries.every((entry) =>
      entry && typeof entry.id === "string" && typeof entry.date === "string" &&
      (entry.stage === "Setup" || entry.stage === "Execution" || entry.stage === "Management" || entry.stage === "Exit") &&
      typeof entry.emotion === "string" && typeof entry.note === "string",
    )),
  );
  const validReviews = workspace.reviews.every((review) =>
    review && typeof review.tradeId === "string" &&
    (review.planAdherence === "yes" || review.planAdherence === "partly" || review.planAdherence === "no") &&
    typeof review.learning === "string" && typeof review.nextAction === "string",
  );
  const validAccounts = workspace.accounts === undefined || Array.isArray(workspace.accounts) && workspace.accounts.every((account) =>
    account && typeof account.id === "string" && typeof account.name === "string" &&
    (account.provider === "MT5" || account.provider === "TradingView") &&
    typeof account.server === "string" && typeof account.loginId === "string",
  );
  return validTrades && validReviews && validAccounts;
}

function ViewContent({ view, trades, reviews, reviewedIds, timezone, dateRange, accounts, viewIds, onToggleView, onClearView, onTimezoneChange, onQuickCapture, onNavigate, onReviewStart, onReportEvidenceOpen, onRecordFill, onManageTrade, onDiscardPlan, onOpenAccountSetup, onConnectAccount, onRevokeAccount, onDeleteAccount, onEditAccount, onExport, onImportCsv, onBulkStrategy, onBulkRemove }: { view: ViewId; trades: Trade[]; reviews: TradeReview[]; reviewedIds: string[]; timezone: string; dateRange: DashboardDateRange; accounts: AccountSetup[]; viewIds: string[]; onToggleView: (id: string) => void; onClearView: () => void; onTimezoneChange: (timezone: string) => void; onQuickCapture: () => void; onNavigate: (view: ViewId) => void; onReviewStart: (trade: Trade) => void; onReportEvidenceOpen: (tradeId: string) => void; onRecordFill: (trade: Trade) => void; onManageTrade: (trade: Trade) => void; onDiscardPlan: (tradeId: string) => void; onOpenAccountSetup: () => void; onConnectAccount: (account: AccountSetup) => void; onSyncAccount: (account: AccountSetup) => void; onRevokeAccount: (account: AccountSetup) => void; onDeleteAccount: (account: AccountSetup) => void; onEditAccount: (account: AccountSetup) => void; onRefreshAccount: (account: AccountSetup) => void; onExport: (trades: Trade[]) => void; onImportCsv: (file: File) => void; onBulkRemove: (ids: string[], mode: "delete" | "clear") => Promise<void>; onBulkStrategy: (ids: string[], strategy: string) => Promise<void> }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkStrategy, setBulkStrategy] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All trades");
  const filteredTrades = useMemo(() => trades.filter((trade) => {
    const matchesSearch = `${trade.symbol} ${trade.strategy} ${trade.id}`.toLowerCase().includes(search.toLowerCase());
    const matchesFilter = filter === "All trades" || trade.outcome === filter;
    return matchesSearch && matchesFilter;
  }), [filter, search, trades]);

  if (view === "overview") {
    return <OverviewContent accounts={viewIds.length ? accounts.filter((item) => viewIds.includes(item.id)) : accounts} trades={trades} reviewedIds={reviewedIds} dateRange={dateRange} timezone={timezone} accountId={viewIds.length === 1 ? viewIds[0] : null} reviews={reviews} onQuickCapture={onQuickCapture} onNavigate={onNavigate} />;
  }
  if (view === "journal") {
    return <div className="content-stack">
      <section className="panel">
        <div className="panel-heading journal-toolbar"><div><span className="eyebrow">EXECUTION RECORD</span><h2>All trades</h2><p>Terminal facts and your notes stay distinct.</p></div><div className="toolbar-actions"><label className="button button-outline file-button"><Icon name="upload" size={16} /> Import CSV<input type="file" accept=".csv,text/csv" onChange={(event) => { const file = event.target.files?.[0]; if (file) onImportCsv(file); event.currentTarget.value = ""; }} /></label><button className="button button-outline" onClick={() => onExport(filteredTrades)}><Icon name="upload" size={16} /> Export CSV</button><button className="button button-primary" onClick={onQuickCapture}><Icon name="plus" size={17} /> New plan</button></div></div>
        <div className="table-controls"><label className="search-field"><Icon name="search" size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search symbol or strategy" /></label><label className="select-control"><Icon name="filter" size={17} /><select value={filter} onChange={(event) => setFilter(event.target.value)}><option>All trades</option><option>Win</option><option>Loss</option><option>Flat</option><option>Open</option><option>Planned</option><option>Discarded</option></select></label></div>
        {selected.length > 0 && <BulkBar trades={trades.filter((trade) => selected.includes(trade.id))} strategy={bulkStrategy} busy={bulkBusy} askOpen={askOpen} onStrategy={setBulkStrategy} onAsk={() => setAskOpen((open) => !open)} onClear={() => setSelected([])} onApply={async () => { setBulkBusy(true); await onBulkStrategy(selected, bulkStrategy.trim()); setBulkBusy(false); setBulkStrategy(""); setSelected([]); }} onRemove={async (mode) => {
          const removable = trades.filter((trade) => selected.includes(trade.id) && trade.outcome !== "Planned" && trade.outcome !== "Discarded");
          if (!removable.length) return;
          const message = mode === "delete" ? `Permanently delete ${removable.length} trade(s)? This cannot be undone. Broker-synced trades are kept and only their journal is cleared.` : `Clear the journal notes, review and tags on ${removable.length} trade(s)? This cannot be undone.`;
          if (!window.confirm(message)) return;
          setBulkBusy(true); await onBulkRemove(removable.map((trade) => trade.id), mode); setBulkBusy(false); setSelected([]);
        }} />}
        <TradeTable trades={filteredTrades} onManageTrade={onManageTrade} selected={selected} onToggleSelect={(id) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])} />
      </section>
    </div>;
  }
  if (view === "plans") {
    const plans = trades.filter((trade) => trade.outcome === "Planned");
    return <div className="content-stack"><section className="panel">
      <div className="panel-heading"><div><span className="eyebrow">TRADER INTENT</span><h2>Plans before fills</h2><p>Unfilled ideas are not counted as executed trades.</p></div><button className="button button-primary" onClick={onQuickCapture}><Icon name="plus" size={17} /> New plan</button></div>
      {plans.length ?       <div className="plan-list">{plans.map((plan) => <article className="plan-card" key={plan.id}><div className={`plan-direction ${plan.direction.toLowerCase()}`}>{plan.direction === "Long" ? "↗" : "↘"}</div><div className="plan-main"><div className="plan-topline"><strong>{plan.symbol}</strong><span>{formatTradeDate(plan.date)}</span></div><p>{plan.plan}</p><div className="plan-meta"><span>{plan.strategy}</span><OutcomeBadge outcome="Planned" />{(() => { const past = trades.filter((item) => item.strategy === plan.strategy && (item.outcome === "Win" || item.outcome === "Loss" || item.outcome === "Flat")); const r = past.flatMap((item) => item.rMultiple === null ? [] : [item.rMultiple]); return <span className="plan-stats">{past.length ? `${past.length} past trades · ${Math.round(past.filter((item) => item.outcome === "Win").length / past.length * 100)}% win${r.length ? ` · ${fmtR(r.reduce((t, v) => t + v, 0) / r.length)} avg` : ""}` : "No history for this strategy yet"}</span>; })()}</div><div className="plan-actions"><button className="button button-primary" onClick={() => onRecordFill(plan)}>Record fill</button><button className="button button-quiet" onClick={() => onDiscardPlan(plan.id)}>Discard idea</button></div></div></article>)}</div> : <div className="empty-state spacious">No open plans yet. Capture an idea before you enter your next trade.</div>}
    </section></div>;
  }
  if (view === "reviews") {
    return <div className="content-stack"><section className="panel">
      <div className="panel-heading"><div><span className="eyebrow">REFLECT & IMPROVE</span><h2>Review queue</h2><p>Complete a review with one specific action for next time.</p></div></div>
      <div className="review-list">{trades.filter((trade) => trade.outcome === "Win" || trade.outcome === "Loss" || trade.outcome === "Flat").map((trade) => {
        const review = reviews.find((item) => item.tradeId === trade.id);
        return <article className={`review-entry ${review ? "is-reviewed" : ""}`} key={trade.id}>
          <div className="review-row"><div className="review-symbol"><strong>{trade.symbol}</strong><span>{formatTradeDate(trade.date)} · {trade.strategy}</span></div><div className="review-result"><OutcomeBadge outcome={trade.outcome} /><strong className={trade.pnl !== null && trade.pnl >= 0 ? "positive" : "negative"}>{trade.pnl === null ? "—" : formatMoney(trade.pnl)}</strong></div><button className="button button-outline" onClick={() => onReviewStart(trade)}>{review ? "Edit review" : "Start review"} <Icon name="arrow" size={15} /></button></div>
          {review && <div className="saved-review"><span>PLAN ADHERENCE · {review.planAdherence.toUpperCase()}</span><p>{review.learning}</p><strong>Next action: {review.nextAction}</strong></div>}
        </article>;
      })}</div>
    </section><ReviewsAgent accountId={viewIds.length === 1 ? viewIds[0] : null} dateRange={dateRange} timezone={timezone} /><section className="callout-panel"><div className="callout-icon"><Icon name="check" /></div><div><strong>Make the review useful, not long.</strong><p>Capture what happened, whether the plan held, and one next action. Process quality is not the same as P&amp;L.</p></div></section></div>;
  }
  if (view === "strategies" || view === "risk" || view === "roadmap") {
    const ordered = trades.filter((trade) => matchesDateRange(trade.date, dateRange) && trade.rMultiple !== null).sort((x, y) => x.date.localeCompare(y.date)).map((trade) => trade.rMultiple as number);
    return <ScopedLab view={view} accountId={viewIds.length === 1 ? viewIds[0] : null} dateRange={dateRange} timezone={timezone} rValues={ordered} />;
  }
  if (view === "execution") return <ExecutionLab trades={trades.filter((trade) => matchesDateRange(trade.date, dateRange))} />;
  if (view === "reports") return <ReportsPage accountId={viewIds.length === 1 ? viewIds[0] : null} timezone={timezone} onOpenTrade={onReportEvidenceOpen} />;
  if (view === "agent") return <AgentPage accountId={viewIds.length === 1 ? viewIds[0] : null} dateRange={dateRange} timezone={timezone} />;
  if (view === "intelligence") {
    const closedR = trades.filter((trade) => matchesDateRange(trade.date, dateRange)).flatMap((trade) => trade.rMultiple === null ? [] : [trade.rMultiple]);
    return <IntelligencePage accountId={viewIds.length === 1 ? viewIds[0] : null} dateRange={dateRange} timezone={timezone} rValues={closedR} />;
  }
  if (view === "analytics") {
    const summary = summarizeTrades(trades);
    const strategyRows = [...new Set(summary.closed.map((trade) => trade.strategy))].map((name) => {
      const records = summary.closed.filter((trade) => trade.strategy === name);
      return { name, count: records.length, pnl: records.reduce((total, trade) => total + (trade.pnl ?? 0), 0) };
    }).sort((a, b) => b.pnl - a.pnl);
    const largestStrategyPnl = Math.max(1, ...strategyRows.map((row) => Math.abs(row.pnl)));
    return <div className="content-stack">
      <section className="stats-grid analytics-stats"><MetricCard label="Net P&L" value={formatMoney(summary.netPnl)} change={`${summary.closed.length} closed trades`} positive={summary.netPnl >= 0} /><MetricCard label="Win rate" value={`${summary.winRate.toFixed(1)}%`} change={`${summary.wins.length} wins · ${summary.losses.length} losses`} /><MetricCard label="Profit factor" value={summary.profitFactor === null ? "—" : summary.profitFactor.toFixed(2)} change="Gross profit ÷ gross loss" /><MetricCard label="Avg. R multiple" value={summary.averageR === null ? "—" : `${summary.averageR >= 0 ? "+" : ""}${summary.averageR.toFixed(2)}R`} change="Only trades with recorded R" positive={summary.averageR !== null && summary.averageR >= 0} /></section>
      <PnlCalendar trades={trades} timezone={timezone} onTimezoneChange={onTimezoneChange} />
      <section className="panel intelligence-link"><div><span className="eyebrow">EDGE INTELLIGENCE</span><h2>Edge Intelligence</h2><p>Strategy ranking, time and behavior analysis, MAE/MFE and your roadmap now have their own page.</p></div><button className="button button-primary" onClick={() => onNavigate("intelligence")}>Open Edge Intelligence <Icon name="arrow" size={15} /></button></section>
      <section className="panel"><div className="panel-heading"><div><span className="eyebrow">OUTCOMES, WITH CONTEXT</span><h2>Cumulative P&amp;L</h2><p>Calculated from closed records in this browser workspace.</p></div></div><PerformanceChart period="30D" trades={trades} /></section>
      <section className="panel"><div className="panel-heading"><div><span className="eyebrow">PROCESS BREAKDOWN</span><h2>Performance by strategy</h2><p>Recorded outcomes are descriptive and do not establish causation.</p></div></div>{strategyRows.length ? <div className="strategy-list">{strategyRows.map((row) => <StrategyBar key={row.name} name={row.name} trades={`${row.count} ${row.count === 1 ? "trade" : "trades"}`} value={Math.max(4, Math.abs(row.pnl) / largestStrategyPnl * 100)} result={formatMoney(row.pnl)} positive={row.pnl >= 0} />)}</div> : <div className="empty-state">Close a trade to begin building strategy analytics.</div>}</section>
    </div>;
  }
  return <div className="content-stack">
      <section className="panel"><div className="panel-heading"><div><span className="eyebrow">SECURE PLATFORM SETUP</span><h2>Trading platform connections</h2><p>Connect an MT5 account with its login, password and server, or receive TradingView signals through your personal webhook.</p></div><button className="button button-primary" onClick={onOpenAccountSetup}><Icon name="plus" size={16} /> Add platform</button></div>
      <div className="connection-safety"><span className="status-dot amber" /><div><strong>Connect with your MT5 login.</strong><p>Balance, open positions and trade history import automatically after you add an account.</p></div></div>
      <div className="view-switch-row"><AccountSwitcher accounts={accounts} viewIds={viewIds} onToggle={onToggleView} onAll={onClearView} /></div>
      {accounts.length > 0 ? <div className="connection-list">{accounts.map((account) => <article className="connection-card" key={account.id}><div className="account-avatar"><Icon name={account.provider === "MT5" ? "chart" : "calendar"} size={18} /></div><div className="connection-card-copy"><strong>{account.name}</strong><span>{account.provider}{account.server ? ` · ${account.server}` : ""}{account.loginId ? ` · Login ${account.loginId}` : ""}{account.provider === "MT5" ? ` · ${account.openPositions ?? 0} open positions` : ""}</span>{account.provider === "MT5" && connectionHint(account) ? <em className="connection-hint">{connectionHint(account)}</em> : null}</div><span className={`connection-status${account.status === "connected" ? " is-live" : ""}`}><i />{account.status === "connected" ? "Account connected" : account.status ?? "not configured"}</span><div className="account-connection-actions">{account.provider === "MT5" ? <>{account.status !== "connected" && account.connectorType !== "metaapi" ? <button className="button button-primary" onClick={() => onConnectAccount(account)}>{account.status === "offline" ? "Reconnect" : "Connect account"}</button> : null}{account.status !== "connected" && account.connectorType === "metaapi" ? <button className="button button-outline" onClick={() => onConnectAccount(account)}>{account.status === "error" ? "Retry connection" : "Connect"}</button> : null}<button className="button button-quiet" onClick={() => onEditAccount(account)}>Edit account</button><button className="button button-danger" onClick={() => onDeleteAccount(account)}>Delete</button></> : <button className="button button-quiet" onClick={() => onRevokeAccount(account)}>Revoke webhook</button>}</div></article>)}</div> : <div className="empty-state">No platform setups yet. Add an MT5 account or TradingView alert connection setup.</div>}
    </section>
  </div>;
}

function DashboardDateRangePicker({ value, onChange }: { value: DashboardDateRange; onChange: (range: DashboardDateRange) => void }) {
  const [open, setOpen] = useState(false);
  const [startDate, setStartDate] = useState(value.startDate);
  const [endDate, setEndDate] = useState(value.endDate);
  const [error, setError] = useState("");
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: PointerEvent) {
      if (event.target instanceof Node && !pickerRef.current?.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function choosePreset(preset: Exclude<DashboardRangePreset, "custom">) {
    if (preset === "all") {
      onChange({ preset, startDate: "", endDate: "" });
      setError("");
      setOpen(false);
      return;
    }
    const end = new Date();
    const start = new Date(end);
    start.setDate(end.getDate() - (preset === "7d" ? 6 : preset === "30d" ? 29 : 89));
    onChange({ preset, startDate: localDateKey(start), endDate: localDateKey(end) });
    setError("");
    setOpen(false);
  }

  function applyCustomRange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!startDate || !endDate) {
      setError("Choose both a start date and an end date.");
      return;
    }
    if (startDate > endDate) {
      setError("The start date must be on or before the end date.");
      return;
    }
    onChange({ preset: "custom", startDate, endDate });
    setError("");
    setOpen(false);
  }

  return <div className="date-range-picker" ref={pickerRef}>
    <button type="button" className="button button-outline date-range-trigger" aria-label={`Date range: ${dashboardRangeLabel(value)}`} aria-expanded={open} aria-haspopup="dialog" onClick={() => {
      setStartDate(value.startDate);
      setEndDate(value.endDate);
      setError("");
      setOpen((current) => !current);
    }}><Icon name="calendar" size={16} /><span>{dashboardRangeLabel(value)}</span><Icon name="chevron" size={14} /></button>
    {open && <section className="date-range-popover" role="dialog" aria-label="Choose dashboard date range">
      <span className="eyebrow">DASHBOARD DATE RANGE</span>
      <div className="date-range-presets" role="group" aria-label="Date range presets">
        {([
          ["all", "All time"],
          ["7d", "Last 7 days"],
          ["30d", "Last 30 days"],
          ["90d", "Last 90 days"],
        ] as const).map(([preset, label]) => <button type="button" key={preset} className={`date-range-option ${value.preset === preset ? "selected" : ""}`} aria-pressed={value.preset === preset} onClick={() => choosePreset(preset)}>{label}</button>)}
      </div>
      <form className="custom-date-range" onSubmit={applyCustomRange}>
        <span className="custom-range-label">Custom dates</span>
        <div className="custom-date-fields">
          <label>From<input type="date" value={startDate} max={endDate || undefined} onChange={(event) => setStartDate(event.target.value)} /></label>
          <label>To<input type="date" value={endDate} min={startDate || undefined} onChange={(event) => setEndDate(event.target.value)} /></label>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" className="button button-primary custom-range-apply">Apply dates</button>
      </form>
    </section>}
  </div>;
}

type TimelineEvent = { kind: string; label: string; source: string; at: string; detail: Record<string, number | string | null> };

function ExecutionTimeline({ tradeId }: { tradeId: string }) {
  const [state, setState] = useState<{ loading: boolean; error: string; events: TimelineEvent[]; terminal: boolean }>({ loading: true, error: "", events: [], terminal: false });
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await apiRequest<{ events: TimelineEvent[]; has_terminal_data: boolean }>(`/performance/execution-timeline/${tradeId}`);
        if (!cancelled) setState({ loading: false, error: "", events: result.events, terminal: result.has_terminal_data });
      } catch {
        if (!cancelled) setState({ loading: false, error: "Timeline unavailable for this trade.", events: [], terminal: false });
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [tradeId]);
  if (state.loading) return <p className="muted-small">Loading timeline…</p>;
  if (state.error) return <p className="muted-small">{state.error}</p>;
  if (!state.events.length) return <p className="muted-small">No terminal orders, deals or events are linked to this trade. Manually logged trades show only what you recorded.</p>;
  return <ol className="exec-timeline">{state.events.map((event, index) => <li key={`${event.at}-${index}`}><time>{new Date(event.at).toLocaleString()}</time><strong>{event.label}</strong><span className="muted-small">{event.kind} · {event.source}{Object.entries(event.detail).filter(([, value]) => value !== null && typeof value !== "object").map(([key, value]) => ` · ${key.replaceAll("_", " ")} ${value}`).join("")}</span></li>)}{!state.terminal && <li className="muted-small">No MT5 orders or deals are linked, so this is limited to journal events.</li>}</ol>;
}

function ExecutionLab({ trades }: { trades: Trade[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const rows = trades.filter((trade) => trade.pnl !== null).map((trade) => {
    const { entryPrice: entry, stopLoss: stop, takeProfit: target } = trade;
    const risk = entry != null && stop != null ? Math.abs(entry - stop) : null;
    const plannedR = risk && target != null && entry != null ? Math.abs(target - entry) / risk : null;
    const capture = plannedR && trade.rMultiple !== null ? trade.rMultiple / plannedR : null;
    const leftOnTable = trade.mfeR != null && trade.rMultiple !== null ? trade.mfeR - trade.rMultiple : null;
    const hasPlan = risk !== null && risk > 0;
    return { trade, plannedR, capture, leftOnTable, hasPlan, breaks: trade.ruleBreaks?.length ?? 0 };
  });
  const planned = rows.filter((row) => row.hasPlan);
  const withCapture = rows.filter((row) => row.capture !== null);
  const withExit = rows.filter((row) => row.leftOnTable !== null);
  const avg = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);
  const clean = rows.filter((row) => row.breaks === 0).length;
  const stats: Array<[string, string, string]> = [
    ["Trades with a defined plan", `${planned.length}/${rows.length}`, "entry and stop recorded"],
    ["Average planned R:R", avg(planned.flatMap((row) => (row.plannedR === null ? [] : [row.plannedR]))) === null ? "—" : `${avg(planned.flatMap((row) => (row.plannedR === null ? [] : [row.plannedR])))!.toFixed(2)}R`, "target distance ÷ stop distance"],
    ["Average target capture", avg(withCapture.map((row) => row.capture as number)) === null ? "—" : `${Math.round(avg(withCapture.map((row) => row.capture as number))! * 100)}%`, "realised R ÷ planned R"],
    ["Average R left after exit", avg(withExit.map((row) => row.leftOnTable as number)) === null ? "—" : `${avg(withExit.map((row) => row.leftOnTable as number))!.toFixed(2)}R`, `from ${withExit.length} trades with recorded MFE`],
    ["Rule-clean trades", rows.length ? `${Math.round((clean / rows.length) * 100)}%` : "—", "no rule break recorded"],
  ];
  return <div className="content-stack">
    <section className="panel intelligence-workspace intelligence-metrics">{stats.map(([label, value, note]) => <div key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>)}</section>
    <section className="panel intelligence-workspace">
      <div className="subsection-heading"><div><span className="eyebrow">PLANNED VS ACTUAL</span><h3>Execution by trade</h3></div></div>
      <div className="table-scroll"><table className="trade-table">
        <thead><tr><th>Trade</th><th>Planned R:R</th><th>Realised R</th><th>Capture</th><th>R left (MFE)</th><th>Rule breaks</th><th><span className="sr-only">Timeline</span></th></tr></thead>
        <tbody>{rows.slice(0, 50).map(({ trade, plannedR, capture, leftOnTable, breaks }) => <Fragment key={trade.id}><tr>
          <td><strong>{trade.symbol}</strong><small> {trade.direction} · {trade.strategy}</small></td>
          <td>{plannedR === null ? "—" : plannedR.toFixed(2)}</td>
          <td>{trade.rMultiple === null ? "—" : `${trade.rMultiple.toFixed(2)}R`}</td>
          <td>{capture === null ? "—" : `${Math.round(capture * 100)}%`}</td>
          <td>{leftOnTable === null ? "—" : `${leftOnTable.toFixed(2)}R`}</td>
          <td>{breaks ? trade.ruleBreaks?.join(", ") : "None recorded"}</td>
        <td><button type="button" className="button button-outline table-journal-button" aria-expanded={openId === trade.id} onClick={() => setOpenId(openId === trade.id ? null : trade.id)}>{openId === trade.id ? "Hide" : "Timeline"}</button></td></tr>{openId === trade.id && <tr><td colSpan={7}><ExecutionTimeline tradeId={trade.id} /></td></tr>}</Fragment>)}</tbody>
      </table>{!rows.length && <div className="empty-state">Close and journal trades with entry, stop and target to compare plan against execution.</div>}</div>
      <p className="muted-small">Only values you or your terminal recorded are used. Missing entry, stop, target or MFE shows as “—” and is never estimated.</p>
    </section>
  </div>;
}

function ScopedLab({ view, accountId, dateRange, timezone, rValues }: { view: "strategies" | "risk" | "roadmap"; accountId: string | null; dateRange: DashboardDateRange; timezone: string; rValues: number[] }) {
  const data = usePerformanceData(accountId, dateRange, timezone);
  if (data.loading) return <div className="panel"><div className="intelligence-loading" /></div>;
  if (data.error) return <p className="form-error" role="alert">{data.error}</p>;
  if (view === "strategies") return <StrategyLab data={data} />;
  if (view === "risk") return <RiskIntelligence data={data} rValues={rValues} accountId={accountId} />;
  return <DevelopmentRoadmap data={data} />;
}

function IntelligencePage({ accountId, dateRange, timezone, rValues }: { accountId: string | null; dateRange: DashboardDateRange; timezone: string; rValues: number[] }) {
  const data = usePerformanceData(accountId, dateRange, timezone);
  const [askOpen, setAskOpen] = useState(false);
  const pm = data.metrics;
  const questions = [
    ["What is happening?", `${pm?.trade_count ?? 0} closed trades in scope`],
    ["What does my data reveal?", pm ? `Expectancy ${fmtR(pm.expectancy_r)}` : "Loading…"],
    ["What should I work on?", data.roadmap?.recommendations[0]?.focus ?? "Keep logging trades"],
    ["Am I improving?", data.roadmap?.id ? `Roadmap: ${data.roadmap.progress_status.replace("_", " ")}` : "Save a roadmap to track progress"],
  ];
  return <div className="content-stack">
    <section className="question-row">{questions.map(([title, answer]) => <article className="question-card" key={title}><span>{title}</span><strong>{answer}</strong></article>)}</section>
    <EdgeSnapshot data={data} onViewAnalysis={() => undefined} onAsk={() => setAskOpen(true)} hideViewLink />
    {askOpen && <AskAgentPanel data={data} onClose={() => setAskOpen(false)} />}
    <AnalyticsWorkspace data={data} rValues={rValues} />
  </div>;
}

function ReviewsAgent({ accountId, dateRange, timezone }: { accountId: string | null; dateRange: DashboardDateRange; timezone: string }) {
  const data = usePerformanceData(accountId, dateRange, timezone);
  return <section className="panel"><div className="panel-heading"><div><span className="eyebrow">WEEKLY AGENT REPORT</span><h2>What to carry into your next review</h2><p>Generated from your own records. Save it to track progress.</p></div></div>{data.loading ? <div className="intelligence-loading" /> : <RoadmapWidget data={data} />}</section>;
}

function OverviewContent({ accounts, trades, reviewedIds, dateRange, timezone, accountId, reviews, onQuickCapture, onNavigate }: { accounts: AccountSetup[]; trades: Trade[]; reviewedIds: string[]; dateRange: DashboardDateRange; timezone: string; accountId: string | null; reviews: TradeReview[]; onQuickCapture: () => void; onNavigate: (view: ViewId) => void }) {
  const rangeTrades = useMemo(() => trades.filter((trade) => matchesDateRange(trade.date, dateRange)), [dateRange, trades]);
  const summary = summarizeTrades(rangeTrades);
  const reviewCount = summary.closed.filter((trade) => !reviewedIds.includes(trade.id)).length;
  const coverage = summary.closed.length ? Math.round((reviewedIds.filter((id) => summary.closed.some((trade) => trade.id === id)).length / summary.closed.length) * 100) : 0;
  const nextReview = rangeTrades.find((trade) =>
    (trade.outcome === "Win" || trade.outcome === "Loss" || trade.outcome === "Flat") && !reviewedIds.includes(trade.id),
  );
  const perf = usePerformanceData(accountId, dateRange, timezone);
  const [askOpen, setAskOpen] = useState(false);
  const pm = perf.metrics;
  const closedIds = new Set(summary.closed.map((trade) => trade.id));
  const closedReviews = reviews.filter((review) => closedIds.has(review.tradeId));
  const adherence = closedReviews.length ? Math.round((closedReviews.filter((review) => review.planAdherence === "yes").length / closedReviews.length) * 100) : 0;
  const completeness = summary.closed.length ? Math.round((summary.closed.filter((trade) => Boolean(trade.setupNotes?.trim() || trade.emotionalState) && Boolean(trade.strategy)).length / summary.closed.length) * 100) : 0;
  const live = accounts.filter((item) => item.provider === "MT5" && item.equity != null);
  const liveBalance = live.reduce((sum, item) => sum + (item.balance ?? 0), 0);
  const liveEquity = live.reduce((sum, item) => sum + (item.equity ?? 0), 0);
  const livePositions = live.reduce((sum, item) => sum + (item.openPositions ?? 0), 0);
  const liveLabel = live.length === 1 ? live[0].name : `${live.length} connected accounts`;
  return (
    <>
      {live.length > 0 && <section className="stats-grid live-accounts">
        <MetricCard label="Account balance" value={formatMoney(liveBalance)} change={liveLabel} positive icon="wallet" />
        <MetricCard label="Equity" value={formatMoney(liveEquity)} change="Balance + floating P&L" positive={liveEquity >= liveBalance} icon="chart" />
        <MetricCard label="Floating P&L" value={formatMoney(liveEquity - liveBalance)} change="Open positions, live" positive={liveEquity >= liveBalance} icon="target" />
        <MetricCard label="Open positions" value={String(livePositions)} change="Synced from MT5" icon="check" />
      </section>}
      <section className="stats-grid metrics-five">
        <MetricCard label="Net P&L" value={formatMoney(summary.netPnl)} change={`${summary.closed.length} closed trades${summary.averageR === null ? "" : ` · ${fmtR(summary.averageR * summary.closed.filter((trade) => trade.rMultiple !== null).length)}`} · ${dashboardRangeLabel(dateRange)}`} positive={summary.netPnl >= 0} icon="chart" />
        <MetricCard label="Win rate" value={`${summary.winRate.toFixed(1)}%`} change={`Sample: ${summary.closed.length} trades · ${summary.wins.length}W ${summary.losses.length}L`} icon="target" />
        <MetricCard label="Profit factor" tone={profitFactorTone(summary.profitFactor)} value={summary.profitFactor === null ? "—" : summary.profitFactor.toFixed(2)} change="Gross profit ÷ gross loss" icon="wallet" />
        <MetricCard label="Expectancy" value={fmtR(pm?.expectancy_r)} change={pm ? `Average edge per trade · ${pm.r_sample_count} with R` : "Average edge per trade"} positive={(pm?.expectancy_r ?? 0) > 0} icon="target" />
        <MetricCard label="Review coverage" value={`${coverage}%`} change={`${reviewedIds.filter((id) => summary.closed.some((trade) => trade.id === id)).length} of ${summary.closed.length} closed trades`} icon="check" />
      </section>
      <EdgeSnapshot data={perf} onViewAnalysis={() => onNavigate("intelligence")} onAsk={() => setAskOpen(true)} />
      {askOpen && <AskAgentPanel data={perf} onClose={() => setAskOpen(false)} />}
      <section className="overview-grid">
        <div className="panel performance-panel">
          <div className="panel-heading"><div><span className="eyebrow">PERFORMANCE</span><h2>Results over time</h2><p>Profit is an outcome, not a process score.</p></div><span className="chart-subtitle">{dashboardRangeLabel(dateRange).toUpperCase()} · USD</span></div>
          <ChartState trades={rangeTrades} />
        </div>
        <div className="panel coverage-panel">
          <div className="panel-heading"><div><span className="eyebrow">PROCESS SCORE</span><h2>Close the loop</h2></div><button className="icon-button" aria-label="More coverage options"><Icon name="more" /></button></div>
          <div className="coverage-meter"><div className="coverage-ring" style={{ background: `conic-gradient(#b78a3a 0 ${coverage}%, #eeeae1 ${coverage}% 100%)` }}><div><strong>{coverage}<span>%</span></strong><small>reviewed</small></div></div><div className="coverage-copy"><strong>{reviewCount ? "Keep the review habit" : "All caught up"}</strong><p>Review coverage counts closed journal records with a completed reflection.</p></div></div>
          <div className="coverage-legend"><span><i className="legend-complete" /> Reviewed <strong>{summary.closed.length - reviewCount}</strong></span><span><i className="legend-open" /> To review <strong>{reviewCount}</strong></span></div>
          <div className="process-bars"><div><span>Rule adherence</span><div className="progress-track"><span style={{ width: `${adherence}%` }} /></div><b>{adherence}%</b></div><div><span>Journal completeness</span><div className="progress-track"><span style={{ width: `${completeness}%` }} /></div><b>{completeness}%</b></div></div>
          {perf.insights[0] && <p className="process-insight">{perf.insights[0].text}</p>}
          <button className="text-link" onClick={() => onNavigate("reviews")}>Open review queue <Icon name="arrow" size={15} /></button>
        </div>
      </section>
      <section className="panel recent-panel">
        <div className="panel-heading"><div><span className="eyebrow">LATEST ACTIVITY</span><h2>Recent trades</h2><p>Broker-reported outcomes are separate from trader interpretation.</p></div><button className="text-link" onClick={() => onNavigate("journal")}>View journal <Icon name="arrow" size={15} /></button></div>
        <TradeTable trades={rangeTrades} compact />
      </section>
      <section className="bottom-grid">
        <div className="panel review-card">
          <div className="panel-heading"><div><span className="eyebrow">NEXT BEST ACTION</span><h2>Review queue</h2></div><span className="count-pill">{reviewCount} pending</span></div>
          {nextReview ? <div className="next-review"><div className="review-date"><Icon name="check" size={17} /></div><div className="review-copy"><strong>Review your {nextReview.symbol} {nextReview.direction.toLowerCase()}</strong><p>{nextReview.outcome} · {nextReview.strategy} · {formatTradeDate(nextReview.date)}</p></div><button className="icon-button soft-button" aria-label="Open review queue" onClick={() => onNavigate("reviews")}><Icon name="arrow" size={17} /></button></div> : <div className="empty-review"><Icon name="check" size={16} /> You are all caught up on trade reviews.</div>}
        </div>
        <div className="panel quick-capture-card">
          <div className="capture-orbit"><Icon name="plus" size={20} /></div><div><span className="eyebrow">BEFORE THE FIRST FILL</span><h2>Capture your intent</h2><p>A quick plan now makes the review more honest later.</p><button className="button button-primary" onClick={onQuickCapture}>Create trade plan <Icon name="arrow" size={16} /></button></div>
        </div>
      </section>
      <p className="demo-disclaimer"><span className="status-dot amber" /> Local workspace · Starter records are illustrative; manually entered figures are not connected to MetaTrader 5.</p>
    </>
  );
}

function ChartState({ trades }: { trades: Trade[] }) {
  const [period, setPeriod] = useState("30D");
  const [mode, setMode] = useState<"pnl" | "r">("pnl");
  const [showDd, setShowDd] = useState(true);
  const summary = summarizeTrades(trades);
  const shown = useMemo(() => mode === "pnl" ? trades : trades.filter((trade) => trade.rMultiple !== null).map((trade) => ({ ...trade, pnl: trade.rMultiple })), [mode, trades]);
  const totalR = shown.reduce((total, trade) => total + (trade.pnl ?? 0), 0);
  return <><div className="period-toggle" role="group" aria-label="Chart metric">{(["pnl", "r"] as const).map((item) => <button type="button" key={item} className={mode === item ? "active" : ""} aria-pressed={mode === item} onClick={() => setMode(item)}>{item === "pnl" ? "Net P&L" : "Cumulative R"}</button>)}</div><label className="chart-overlay-toggle"><input type="checkbox" checked={showDd} onChange={(event) => setShowDd(event.target.checked)} /> Shade drawdowns</label><PerformanceChart period={period} trades={shown} showDrawdown={showDd} unit={mode === "r" ? "r" : "money"} /><div className="chart-footer"><span><i className="chart-legend-dot" /> {mode === "pnl" ? "Net cumulative P&L" : "Cumulative R (recorded only)"}</span><strong className={(mode === "pnl" ? summary.netPnl : totalR) >= 0 ? "positive" : "negative"}>{mode === "pnl" ? formatMoney(summary.netPnl) : fmtR(totalR)}</strong></div><PeriodState period={period} setPeriod={setPeriod} /></>;
}

function PeriodState({ period, setPeriod }: { period: string; setPeriod: (period: string) => void }) {
  return <div className="period-toggle" role="group" aria-label="Chart time range">{["7D", "30D", "90D"].map((item) => <button type="button" key={item} className={period === item ? "active" : ""} aria-pressed={period === item} onClick={() => setPeriod(item)}>{item}</button>)}</div>;
}

function MetricCard({ label, value, change, positive = false, icon, tone = "" }: { label: string; value: string; change: string; positive?: boolean; icon?: string; tone?: string }) {
  return <article className="metric-card"><div className="metric-topline"><span>{label}</span>{icon && <span className="metric-icon"><Icon name={icon} size={17} /></span>}</div><strong className={`metric-value ${tone}`}>{value}</strong><div className={`metric-change ${positive ? "positive" : ""}`}><span className={positive ? "trend-up" : "trend-neutral"}>{positive ? "↗" : "•"}</span>{change}</div></article>;
}

function StrategyBar({ name, trades, value, result, positive }: { name: string; trades: string; value: number; result: string; positive: boolean }) {
  return <div className="strategy-row"><div className="strategy-info"><div><strong>{name}</strong><span>{trades}</span></div><strong className={positive ? "positive" : "negative"}>{result}</strong></div><div className="strategy-track"><span className={positive ? "" : "negative-fill"} style={{ width: `${value}%` }} /></div></div>;
}

function AccountSetupModal({ onClose, onSave, method }: { method: string; onClose: () => void; onSave: (account: AccountSetup, password: string) => void | Promise<void> }) {
  const [provider, setProvider] = useState<AccountSetup["provider"]>("MT5");
  const [name, setName] = useState("");
  const [server, setServer] = useState("");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Enter a name for this platform setup.");
      return;
    }
    if (provider === "MT5" && (!server.trim() || !loginId.trim())) {
      setError("Enter the MT5 login (account number), password and server.");
      return;
    }
    if (provider === "MT5" && method !== "ea" && !password) {
      setError("Enter the MT5 account password.");
      return;
    }
    if (provider === "MT5" && !/^\d+$/.test(loginId.trim())) {
      setError("The MT5 login ID must contain digits only.");
      return;
    }
    setSubmitting(true);
    try {
      await onSave({
        id: `ACCOUNT-${Date.now()}`,
        name: name.trim(),
        provider,
        server: server.trim(),
        loginId: provider === "MT5" ? loginId.trim() : "",
      }, password);
    } finally {
      setPassword("");
      setSubmitting(false);
    }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="capture-modal account-setup-modal" role="dialog" aria-modal="true" aria-labelledby="account-setup-title">
    <div className="modal-heading"><div><span className="eyebrow">PLATFORM SETUP</span><h2 id="account-setup-title">Add a trading platform</h2><p>{provider === "MT5" ? "Enter your MT5 login, password and server exactly as they appear in your terminal." : "Receive TradingView alerts through your personal webhook."}</p></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close" /></button></div>
    <form onSubmit={submit}>
      <label>Platform<select value={provider} onChange={(event) => { setProvider(event.target.value as AccountSetup["provider"]); setError(""); }}><option value="MT5">MetaTrader 5</option><option value="TradingView">TradingView alerts</option></select></label>
      <label>Account label<input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. FTMO evaluation" autoFocus /></label>
      {provider === "MT5" ? <><div className="form-row"><label>MT5 login<input value={loginId} onChange={(event) => setLoginId(event.target.value)} inputMode="numeric" placeholder="Account number" /></label><label>Server<input value={server} onChange={(event) => setServer(event.target.value)} placeholder="e.g. FxPro-MT5 Demo" /></label></div>{method !== "ea" && <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" maxLength={256} placeholder="MT5 account password" /></label>}</> : <label>Broker / alert label <span className="optional-label">Optional</span><input value={server} onChange={(event) => setServer(event.target.value)} placeholder="e.g. Connected broker or alert group" /></label>}
      <div className="connection-safety modal-safety"><span className="status-dot amber" /><div><strong>{provider === "MT5" ? (method === "ea" ? "No password needed — you install a small EA." : "Your balance, positions and history sync automatically.") : "No password needed."}</strong><p>{provider === "MT5" ? "TradeIQ links this MT5 login securely and imports your balance, open positions and full trade history automatically. An investor (read-only) password is enough." : "TradingView alerts use a server-side, secret-protected webhook. Your TradingView password is not needed."}</p></div></div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button type="submit" className="button button-primary" disabled={submitting}>{submitting ? "Connecting…" : provider === "MT5" ? "Save & connect" : "Save setup"}</button></div>
    </form>
  </section></div>;
}

function MT5ConnectModal({
  method,
  account,
  onClose,
  onConnect,
}: {
  method: string;
  account: AccountSetup;
  onClose: () => void;
  onConnect: (account: AccountSetup, login: string, password: string, server: string) => Promise<void>;
}) {
  const [login, setLogin] = useState(account.loginId);
  const [server, setServer] = useState(account.server);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!/^\d+$/.test(login.trim())) {
      setError("The MT5 login must be the numeric account number.");
      return;
    }
    setSubmitting(true);
    try {
      await onConnect(account, login.trim(), password, server.trim());
    } catch (connectError) {
      setError(connectError instanceof ApiError && connectError.status === 404
        ? "This account isn't available in the current session. If you signed in as admin in this browser, sign out of /admin, sign back in as this user and retry."
        : connectError instanceof Error ? connectError.message : "Could not connect this account.");
    } finally {
      setPassword("");
      setSubmitting(false);
    }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="capture-modal account-setup-modal" role="dialog" aria-modal="true" aria-labelledby="mt5-connect-title">
    <div className="modal-heading"><div><span className="eyebrow">METATRADER 5 LOGIN</span><h2 id="mt5-connect-title">Connect {account.name}</h2><p>Enter the credentials used to log in to your MT5 terminal.</p></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close" /></button></div>
    <form onSubmit={(event) => void submit(event)}>
      <div className="form-row"><label>MT5 login<input value={login} onChange={(event) => setLogin(event.target.value)} inputMode="numeric" required /></label><label>Server<input value={server} onChange={(event) => setServer(event.target.value)} required maxLength={120} /></label></div>
      {method !== "ea" && <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required maxLength={256} /></label>}
      <div className="connection-safety modal-safety"><span className="status-dot amber" /><div><strong>Imports your balance, open positions and trade history.</strong><p>An investor (read-only) password is enough. Data refreshes automatically.</p></div></div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose} disabled={submitting}>Cancel</button><button type="submit" className="button button-primary" disabled={submitting || (method !== "ea" && !password) || !login || !server}>{submitting ? "Connecting…" : "Connect account"}</button></div>
    </form>
  </section></div>;
}

function DeleteAccountModal({ account, onClose, onConfirm }: { account: AccountSetup; onClose: () => void; onConfirm: (account: AccountSetup) => Promise<void> }) {
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await onConfirm(account);
      onClose();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete this account.");
      setBusy(false);
    }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}><section className="capture-modal account-setup-modal" role="dialog" aria-modal="true" aria-labelledby="delete-account-title">
    <div className="modal-heading"><div><span className="eyebrow">DELETE ACCOUNT</span><h2 id="delete-account-title">Delete {account.name}?</h2></div></div>
    <div className="connection-safety modal-safety"><span className="status-dot amber" /><div><strong>This permanently deletes the account from this section.</strong><p>The broker connection will be removed and syncing will stop. To use this account again you will have to set it up from scratch.</p></div></div>
    <label className={`consent-check${agreed ? " is-checked" : ""}`}><input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} /><span className="consent-box" aria-hidden="true"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 8.5l3 3 6-7" /></svg></span><span className="consent-text">I understand and agree to permanently delete this account.</span></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose} disabled={busy}>Cancel</button><button type="button" className="button button-danger" onClick={() => void confirm()} disabled={!agreed || busy}>{busy ? "Deleting..." : "Delete permanently"}</button></div>
  </section></div>;
}

function ReviewModal({ trade, existingReview, onClose, onSave }: { trade: Trade; existingReview?: TradeReview; onClose: () => void; onSave: (review: TradeReview) => void }) {
  const [matchedPlan, setMatchedPlan] = useDraftState<"yes" | "partly" | "no" | "">(`review.${trade.id}`, "matchedPlan", existingReview?.planAdherence ?? "");
  const [learning, setLearning] = useDraftState(`review.${trade.id}`, "learning", existingReview?.learning ?? "");
  const [nextAction, setNextAction] = useDraftState(`review.${trade.id}`, "nextAction", existingReview?.nextAction ?? "");
  const [error, setError] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!matchedPlan || !learning.trim() || !nextAction.trim()) {
      setError("Choose how the trade matched your plan and add a learning plus one next action.");
      return;
    }
    onSave({ tradeId: trade.id, planAdherence: matchedPlan, learning: learning.trim(), nextAction: nextAction.trim() });
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="capture-modal review-modal" role="dialog" aria-modal="true" aria-labelledby="review-title">
    <div className="modal-heading"><div><span className="eyebrow">POST-TRADE REVIEW · {trade.symbol}</span><h2 id="review-title">{existingReview ? "Update your review" : "What did this trade teach you?"}</h2><p>Outcome and execution quality are separate parts of the record.</p></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close" /></button></div>
    <div className="review-context"><div><span>TERMINAL OUTCOME</span><strong className={trade.pnl !== null && trade.pnl >= 0 ? "positive" : "negative"}>{trade.pnl === null ? "—" : formatMoney(trade.pnl)} · {trade.rMultiple ?? "—"}R</strong></div><div><span>TRADER PLAN</span><strong>{trade.plan}</strong></div></div>
    <form onSubmit={submit}>
      <fieldset className="choice-field"><legend>Did execution match the plan?</legend><div className="choice-options">{(["yes", "partly", "no"] as const).map((choice) => <button type="button" key={choice} className={`choice-button ${matchedPlan === choice ? "chosen" : ""}`} onClick={() => setMatchedPlan(choice)}>{choice === "yes" ? "Yes" : choice === "partly" ? "Partly" : "No"}</button>)}</div></fieldset>
      <label>What did you learn?<textarea value={learning} onChange={(event) => setLearning(event.target.value)} placeholder="Describe what happened without judging the outcome..." rows={3} /></label>
      <label>One next action<textarea value={nextAction} onChange={(event) => setNextAction(event.target.value)} placeholder="What will you do differently or repeat next time?" rows={2} /></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button type="submit" className="button button-primary">{existingReview ? "Save changes" : "Complete review"} <Icon name="check" size={16} /></button></div>
    </form>
  </section></div>;
}

function OneTimeSecretDialog({
  secret,
  onClose,
}: {
  secret: OneTimeSecret;
  onClose: () => void;
}) {
  const [copyError, setCopyError] = useState("");

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyError("");
    } catch {
      setCopyError("Clipboard access is unavailable. Select and copy the value manually.");
    }
  }

  return (
    <div className="modal-backdrop">
      <section className="capture-modal secret-modal" role="dialog" aria-modal="true" aria-labelledby="secret-title">
        <div className="modal-heading">
          <div>
            <span className="eyebrow">ONE-TIME CREDENTIAL</span>
            <h2 id="secret-title">{secret.heading}</h2>
            <p>{secret.description}</p>
          </div>
        </div>
        {secret.config && <label>Webhook URL<input readOnly value={secret.config} /></label>}
        <label>Secret token<input readOnly value={secret.value} onFocus={(event) => event.currentTarget.select()} /></label>
        {copyError && <p className="form-error" role="alert">{copyError}</p>}
        <div className="modal-actions">
          <button type="button" className="button button-outline" onClick={() => void copy(secret.value)}>Copy token</button>
          {secret.config && <button type="button" className="button button-outline" onClick={() => void copy(`${secret.config}\n${secret.value}`)}>Copy URL and token</button>}
          <button type="button" className="button button-primary" onClick={onClose}>Done</button>
        </div>
      </section>
    </div>
  );
}

export default function Home() {
  const [view, setView] = useState<ViewId>("overview");
  const [viewRestored, setViewRestored] = useState(false);
  const [apiUser, setApiUser] = useState<ApiUser | null>(null);
  const [apiStatus, setApiStatus] = useState<"checking" | "signed-out" | "loading" | "ready" | "error">("checking");
  const [apiError, setApiError] = useState("");
  const sessionRequestVersion = useRef(0);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [reviews, setReviews] = useState<TradeReview[]>([]);
  const [accounts, setAccounts] = useState<AccountSetup[]>([]);
  const [timezone, setTimezone] = useState("local");
  const [dateRange, setDateRange] = useState<DashboardDateRange>({ preset: "all", startDate: "", endDate: "" });
  const [legacyDataAvailable, setLegacyDataAvailable] = useState(false);
  const reviewedIds = reviews.map((review) => review.tradeId);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [accountSetupOpen, setAccountSetupOpen] = useState(false);
  const [connectingAccount, setConnectingAccount] = useState<AccountSetup | null>(null);
  const [deletingAccount, setDeletingAccount] = useState<AccountSetup | null>(null);
  const [editingAccount, setEditingAccount] = useState<AccountSetup | null>(null);
  const [oneTimeSecret, setOneTimeSecret] = useState<OneTimeSecret | null>(null);
  const [verifying, setVerifying] = useState<{ id: string; name: string } | null>(null);
  const [eaWizard, setEaWizard] = useState<{ accountId?: string; accountName: string; webhookUrl: string } | null>(null);
  const [viewIds, setViewIds] = useState<string[]>([]);
  const detected = useDetectedAccounts(apiStatus === "ready");
  const [mt5Method, setMt5Method] = useState("metaapi");
  useEffect(() => {
    apiRequest<{ method: string }>("/platform/mt5-method").then((r) => setMt5Method(r.method)).catch(() => undefined);
  }, []);
  const [activePlan, setActivePlan] = useState<Trade | null>(null);
  const [activeReview, setActiveReview] = useState<Trade | null>(null);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [fillErrors, setFillErrors] = useState<Record<string, string>>({});
  const currentView = viewCopy[view];
  const pendingReviewCount = trades.filter((trade) =>
    (trade.outcome === "Win" || trade.outcome === "Loss" || trade.outcome === "Flat") && !reviewedIds.includes(trade.id),
  ).length;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const savedView = window.localStorage.getItem(ACTIVE_VIEW_KEY);
      if (savedView && navigation.some((item) => item.id === savedView)) {
        setView(savedView as ViewId);
      }
      setViewRestored(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (viewRestored) window.localStorage.setItem(ACTIVE_VIEW_KEY, view);
  }, [view, viewRestored]);

  useEffect(() => {
    let cancelled = false;
    const requestVersion = ++sessionRequestVersion.current;
    apiRequest<ApiUser>("/auth/me")
      .then((user) => {
        if (cancelled || requestVersion !== sessionRequestVersion.current) return;
        setApiUser(user);
        setApiStatus("loading");
      })
      .catch((error: unknown) => {
        if (cancelled || requestVersion !== sessionRequestVersion.current) return;
        if (error instanceof ApiError && error.status === 401) {
          setApiStatus("signed-out");
          return;
        }
        setApiError(error instanceof Error ? error.message : "The TradeIQ API is unavailable.");
        setApiStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const mt5Accounts = accounts.filter((item) => item.provider === "MT5" && item.status !== "pending");
  const scopeIds = mt5Accounts.length > 1 ? viewIds.filter((id) => mt5Accounts.some((item) => item.id === id)) : [];
  const scopeKey = scopeIds.join(",");
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      try {
        const saved: unknown = JSON.parse(window.localStorage.getItem("tradeiq.viewAccounts") ?? "[]");
        if (Array.isArray(saved)) setViewIds(saved.filter((id): id is string => typeof id === "string"));
      } catch {
        setViewIds([]);
      }
    }, 0);
    return () => window.clearTimeout(timeout);
  }, []);
  function saveView(ids: string[]) {
    setViewIds(ids);
    window.localStorage.setItem("tradeiq.viewAccounts", JSON.stringify(ids));
  }
  function toggleView(id: string) {
    saveView(scopeIds.includes(id) ? scopeIds.filter((item) => item !== id) : [...scopeIds, id]);
  }

  useEffect(() => {
    if (!apiUser) return;
    let cancelled = false;
    loadBackendWorkspace(scopeKey ? scopeKey.split(",") : [])
      .then((workspace) => {
        if (cancelled) return;
        setAccounts(workspace.accounts);
        setTrades(workspace.trades);
        setReviews(workspace.reviews);
        setTimezone(workspace.timezone);
        setApiStatus("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          setApiError("Your sign-in session could not access the journal. Please sign in again.");
          setApiUser(null);
          setApiStatus("signed-out");
          return;
        }
        setApiError(error instanceof Error ? error.message : "Unable to load your TradeIQ records.");
        setApiStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [apiUser, scopeKey]);

  const waitingOnBroker = accounts.some((item) =>
    (item.connectorType === "metaapi" || item.connectorType === "ea") && ["provisioning", "pending", "syncing"].includes(item.status ?? ""));
  const hasLiveAccount = accounts.some((item) => (item.connectorType === "metaapi" || item.connectorType === "ea") && ["connected", "offline"].includes(item.status ?? ""));
  const accountIds = accounts.filter((item) => item.provider === "MT5").map((item) => item.id).join(",");

  useEffect(() => {
    if (apiStatus !== "ready" || !accountIds || (!waitingOnBroker && !hasLiveAccount)) return;
    let cancelled = false;
    let inFlight = false;
    const refreshStatuses = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const statuses = await Promise.all(accountIds.split(",").map(async (accountId) => {
          const [connection, positions] = await Promise.all([
            apiRequest<{ status: string; connector_type: string; last_error: string | null; balance: number | null; equity: number | null }>(`/accounts/${accountId}/status`),
            apiRequest<unknown[]>(`/accounts/${accountId}/positions`),
          ]);
          return { accountId, connection, openPositions: positions.length };
        }));
        if (cancelled) return;
        const byId = new Map(statuses.map((item) => [item.accountId, item]));
        setAccounts((current) => current.map((account) => {
          const next = byId.get(account.id);
          return next ? {
            ...account,
            connectorType: next.connection.connector_type,
            lastError: next.connection.last_error,
            status: next.connection.status,
            openPositions: next.openPositions,
            balance: next.connection.balance,
            equity: next.connection.equity,
          } : account;
        }));
      } catch {
        // Keep the last known account status when a refresh briefly fails.
      } finally {
        inFlight = false;
      }
    };
    void refreshStatuses();
    const interval = window.setInterval(refreshStatuses, waitingOnBroker ? 3000 : 20000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [apiStatus, accountIds, waitingOnBroker, hasLiveAccount]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved !== null) setLegacyDataAvailable(isWorkspace(JSON.parse(saved)));
      } catch (error) {
        console.error("Unable to inspect the saved browser workspace.", error);
      }
    }, 0);
    return () => window.clearTimeout(timeout);
  }, []);

  async function checkApiSession() {
    const requestVersion = ++sessionRequestVersion.current;
    setApiStatus("checking");
    setApiError("");
    try {
      const user = await apiRequest<ApiUser>("/auth/me");
      if (requestVersion !== sessionRequestVersion.current) return;
      setApiUser(user);
      setApiStatus("loading");
    } catch (error) {
      if (requestVersion !== sessionRequestVersion.current) return;
      if (error instanceof ApiError && error.status === 401) {
        setApiUser(null);
        setApiStatus("signed-out");
        return;
      }
      setApiError(error instanceof Error ? error.message : "The TradeIQ API is unavailable.");
      setApiStatus("error");
    }
  }

  async function signOut() {
    try {
      await apiRequest<void>("/auth/logout", { method: "POST" });
      setApiUser(null);
      setApiStatus("signed-out");
      setTrades([]);
      setReviews([]);
      setAccounts([]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not sign out.");
    }
  }

  async function savePlan(trade: Trade) {
    setActionError("");
    try {
      const saved = await apiRequest<ApiPlan>("/plans", {
        method: "POST",
        body: JSON.stringify({
          symbol: trade.symbol,
          direction: trade.direction,
          strategy: trade.strategy,
          thesis: trade.plan,
          account_id: scopeIds.length === 1 ? scopeIds[0] : null,
        }),
      });
      const mapped = mapApiPlan(saved);
      setTrades((current) => [mapped, ...current]);
      clearDrafts("capture");
      setCaptureOpen(false);
      setView("plans");
      setNotice(`${trade.symbol} plan saved to your TradeIQ account. It is not an executed trade.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not save the trade plan.");
    }
    window.setTimeout(() => setNotice(""), 5000);
  }

  async function recordFill(executedTrade: Trade) {
    setActionError("");
    setFillErrors({});
    try {
      const isPlan = activePlan?.outcome === "Planned";
      const existing = isPlan ? null : activePlan;
      const updatePayload = existing?.source === "mt5"
        ? { notes: executedTrade.plan, ...v2Context(executedTrade) }
        : {
            ...v2Context(executedTrade),
            take_profit: executedTrade.takeProfit,
            stop_loss: executedTrade.stopLoss,
            outcome: executedTrade.outcome.toLowerCase(),
            pnl: executedTrade.pnl,
            r_multiple: executedTrade.rMultiple,
            entry_price: executedTrade.entryPrice,
            exit_price: executedTrade.exitPrice,
            size: executedTrade.size,
            notes: executedTrade.plan,
            closed_at: ["Win", "Loss", "Flat"].includes(executedTrade.outcome)
              ? new Date().toISOString()
              : null,
          };
      const saved = isPlan
        ? await apiRequest<ApiTrade>("/trades", {
            method: "POST",
            body: JSON.stringify({
              plan_id: activePlan.id,
              account_id: activePlan.accountId ?? (scopeIds.length === 1 ? scopeIds[0] : null),
              symbol: executedTrade.symbol,
              direction: executedTrade.direction,
              strategy: executedTrade.strategy,
              outcome: executedTrade.outcome.toLowerCase(),
              pnl: executedTrade.pnl,
              r_multiple: executedTrade.rMultiple,
              entry_price: executedTrade.entryPrice,
              exit_price: executedTrade.exitPrice,
              size: executedTrade.size,
              notes: executedTrade.plan,
              ...v2Context(executedTrade),
              stop_loss: executedTrade.stopLoss,
              take_profit: executedTrade.takeProfit,
              opened_at: utcTimestamp(executedTrade.date),
              closed_at: ["Win", "Loss", "Flat"].includes(executedTrade.outcome)
                ? new Date(Math.max(Date.now(), Date.parse(utcTimestamp(executedTrade.date)))).toISOString()
                : null,
            }),
          })
        : await apiRequest<ApiTrade>(`/trades/${executedTrade.id}`, {
            method: "PATCH",
            body: JSON.stringify(updatePayload),
          });
      const journalEntries = executedTrade.journalEntries ?? [];
      await Promise.all([
        apiRequest(`/trades/${saved.id}/journal/strategy_setup`, {
          method: "PATCH",
          body: JSON.stringify({
            content: {
              setup_notes: executedTrade.setupNotes ?? "",
              setup_emotion: executedTrade.setupEmotion ?? "Neutral",
              stop_loss: executedTrade.stopLoss ?? null,
              take_profit: executedTrade.takeProfit ?? null,
            },
          }),
        }),
        apiRequest(`/trades/${saved.id}/journal/journal_entries`, {
          method: "PATCH",
          body: JSON.stringify({ content: journalEntries }),
        }),
      ]);
      const mapped = mapApiTrade(saved);
      mapped.journalEntries = journalEntries;
      setTrades((current) => [
        mapped,
        ...current.filter((trade) => trade.id !== (existing?.id ?? activePlan?.id)),
      ]);
      clearDrafts(`exec.${executedTrade.id}`);
      setActivePlan(null);
      setNotice(`${executedTrade.symbol} journal update saved to your TradeIQ account.`);
    } catch (error) {
      const fields = apiFieldErrors(error);
      if (fields) setFillErrors(fields);
      else setActionError(error instanceof Error ? error.message : "Could not save the trade journal.");
    }
    window.setTimeout(() => setNotice(""), 5000);
  }

  async function bulkRemove(ids: string[], mode: "delete" | "clear") {
    setActionError("");
    const target = new Map(trades.map((trade) => [trade.id, trade]));
    const results = await Promise.allSettled(ids.map((id) => {
      const brokerSynced = target.get(id)?.source === "mt5";
      if (mode === "delete" && !brokerSynced) return apiRequest<void>(`/trades/${id}`, { method: "DELETE" }).then(() => "deleted" as const);
      return apiRequest<ApiTrade>(`/trades/${id}/journal`, { method: "DELETE" }).then(() => "cleared" as const);
    }));
    const deleted = new Set<string>();
    const cleared = new Set<string>();
    results.forEach((result, index) => {
      if (result.status !== "fulfilled") return;
      (result.value === "deleted" ? deleted : cleared).add(ids[index]);
    });
    setTrades((current) => current.filter((trade) => !deleted.has(trade.id)).map((trade) => cleared.has(trade.id)
      ? { ...trade, strategy: "Uncategorized", setupNotes: "", setupEmotion: "", setupName: undefined, emotionalState: null, confluences: [], ruleBreaks: [], maeR: null, mfeR: null, journalEntries: [] }
      : trade));
    setReviews((current) => current.filter((review) => !deleted.has(review.tradeId) && !cleared.has(review.tradeId)));
    const failed = ids.length - deleted.size - cleared.size;
    const parts = [deleted.size ? `Deleted ${deleted.size} trade${deleted.size === 1 ? "" : "s"}` : "", cleared.size ? `cleared the journal on ${cleared.size}` : ""].filter(Boolean).join(" and ");
    if (failed) setActionError(`${failed} trade${failed === 1 ? "" : "s"} could not be updated.`);
    setNotice(parts ? `${parts}.` : "Nothing was changed.");
    window.setTimeout(() => setNotice(""), 5000);
  }

  async function bulkStrategy(ids: string[], strategy: string) {
    if (!strategy) return;
    setActionError("");
    const results = await Promise.allSettled(ids.map((id) => apiRequest<ApiTrade>(`/trades/${id}`, { method: "PATCH", body: JSON.stringify({ strategy }) })));
    const updated = new Map<string, Trade>();
    results.forEach((result, index) => { if (result.status === "fulfilled") updated.set(ids[index], mapApiTrade(result.value)); });
    setTrades((current) => current.map((trade) => {
      const next = updated.get(trade.id);
      return next ? { ...next, journalEntries: trade.journalEntries } : trade;
    }));
    const failed = ids.length - updated.size;
    setNotice(failed ? `Tagged ${updated.size} trades; ${failed} could not be updated.` : `Tagged ${updated.size} trades as "${strategy}".`);
    window.setTimeout(() => setNotice(""), 5000);
  }

  async function saveAccountSetup(account: AccountSetup, password: string) {
    setActionError("");
    try {
      if (account.provider === "TradingView") {
        const credential = await apiRequest<{ webhook_token: string; webhook_path: string }>(
          "/integrations/tradingview/token",
          { method: "POST" },
        );
        setAccounts((current) => [
          ...current.filter((item) => item.provider !== "TradingView"),
          {
            id: "tradingview-integration",
            name: account.name,
            provider: "TradingView",
            server: account.server,
            loginId: "",
            status: "connected",
            openPositions: 0,
          },
        ]);
        setOneTimeSecret({
          heading: "Save the TradingView webhook token",
          description: "This token is shown once. Put it in the JSON alert body as webhook_token; rotating it invalidates the previous token.",
          value: credential.webhook_token,
          config: `${getApiBaseUrl() || "http://localhost:8000"}${credential.webhook_path}`,
        });
        setAccountSetupOpen(false);
        return;
      }
      const saved = await apiRequest<ApiAccount>("/accounts", {
        method: "POST",
        body: JSON.stringify({
          name: account.name,
          external_account_id: account.loginId || null,
          broker: null,
          server_name: account.server || null,
          environment: "demo",
          currency: "USD",
        }),
      });
      const mapped: AccountSetup = {
        id: saved.id,
        name: saved.name,
        provider: "MT5",
        server: saved.server_name ?? saved.broker ?? "",
        loginId: saved.external_account_id ?? "",
        connectorType: "mt5",
        status: "not_configured",
        openPositions: 0,
      };
      setAccounts((current) => [mapped, ...current]);
      setAccountSetupOpen(false);
      try {
        await connectMt5Account(mapped, account.loginId, password, account.server);
      } catch (connectError) {
        setActionError(connectError instanceof Error ? connectError.message : "Saved, but could not store the MT5 credentials. Use Connect to retry.");
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not save this account.");
    }
    window.setTimeout(() => setNotice(""), 6000);
  }

  function connectAccount(account: AccountSetup) {
    setConnectingAccount(account);
  }

  async function updateEaSetup(accountId: string, accountName: string) {
    setActionError("");
    try {
      const setup = await apiRequest<{ webhook_url: string }>(`/accounts/${accountId}/ea/connect`, { method: "POST" });
      setVerifying(null);
      setEaWizard({ accountId, accountName, webhookUrl: setup.webhook_url });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not refresh the EA setup.");
    }
  }

  async function connectMt5Account(
    account: AccountSetup,
    login: string,
    password: string,
    server: string,
  ) {
    setActionError("");
    if (mt5Method === "ea") {
      const ea = await apiRequest<{ already_installed: boolean; webhook_url?: string }>(`/accounts/${account.id}/ea/connect`, { method: "POST" });
      setAccounts((current) => current.map((item) =>
        item.id === account.id ? { ...item, connectorType: "ea", status: "pending", loginId: login, server } : item,
      ));
      setConnectingAccount(null);
      if (ea.already_installed || !ea.webhook_url) {
        setVerifying({ id: account.id, name: account.name });
        return;
      }
      setEaWizard({ accountId: account.id, accountName: account.name, webhookUrl: ea.webhook_url });
      return;
    }
    const result = await apiRequest<{ status: string; message: string }>(
      `/accounts/${account.id}/metaapi/connect`,
      {
        method: "POST",
        body: JSON.stringify({ login: Number(login), password, server }),
      },
    );
    setAccounts((current) => current.map((item) =>
      item.id === account.id
        ? { ...item, connectorType: "metaapi", status: result.status, loginId: login, server }
        : item,
    ));
    setConnectingAccount(null);
    setNotice(result.message);
    window.setTimeout(() => setNotice(""), 8000);
  }

  async function syncAccount(account: AccountSetup) {
    setActionError("");
    try {
      await apiRequest(`/accounts/${account.id}/sync`, { method: "POST" });
      setNotice(`A sync was queued for ${account.name}.`);
      await refreshAccount(account);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not queue an account sync.");
    }
  }

  async function refreshAccount(account: AccountSetup) {
    setActionError("");
    try {
      const [connection, positions] = await Promise.all([
        apiRequest<{ status: string; connector_type: string; balance: number | null; equity: number | null }>(`/accounts/${account.id}/status`),
        apiRequest<unknown[]>(`/accounts/${account.id}/positions`),
      ]);
      setAccounts((current) => current.map((item) =>
        item.id === account.id
          ? {
              ...item,
              connectorType: connection.connector_type,
              status: connection.status,
              openPositions: positions.length,
              balance: connection.balance,
              equity: connection.equity,
            }
          : item,
      ));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not refresh account status.");
    }
  }

  async function revokeAccount(account: AccountSetup) {
    setActionError("");
    try {
      if (account.provider === "TradingView") {
        await apiRequest<void>("/integrations/tradingview/token", { method: "DELETE" });
      } else {
        await apiRequest<void>(`/accounts/${account.id}/metaapi/disconnect`, { method: "POST" });
      }
      setAccounts((current) => current
        .filter((item) => account.provider !== "TradingView" || item.id !== account.id)
        .map((item) => item.id === account.id ? { ...item, status: "disconnected" } : item));
      setNotice(`${account.name} connection credential was revoked.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not revoke this connection.");
    }
  }

  async function renameAccount(account: AccountSetup, name: string) {
    await apiRequest(`/accounts/${account.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
    setAccounts((current) => current.map((item) => item.id === account.id ? { ...item, name } : item));
    setNotice(`Account renamed to ${name}.`);
  }

  async function deleteAccount(account: AccountSetup) {
    await apiRequest<void>(`/accounts/${account.id}`, { method: "DELETE" });
    setAccounts((current) => current.filter((item) => item.id !== account.id));
    setNotice(`${account.name} was permanently deleted.`);
  }

  async function discardPlan(tradeId: string) {
    setActionError("");
    try {
      await apiRequest(`/plans/${tradeId}/discard`, { method: "POST" });
      setTrades((current) => current.map((trade) =>
        trade.id === tradeId && trade.outcome === "Planned"
          ? { ...trade, outcome: "Discarded" }
          : trade,
      ));
      setNotice("Idea marked as discarded in your account.");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not discard the plan.");
    }
    window.setTimeout(() => setNotice(""), 5000);
  }

  async function completeReview(review: TradeReview) {
    setActionError("");
    try {
      const existingReview = reviews.some((item) => item.tradeId === review.tradeId);
      await apiRequest(`/trades/${review.tradeId}/reviews`, {
        method: existingReview ? "PATCH" : "POST",
        body: JSON.stringify({
          plan_adherence: review.planAdherence,
          learning: review.learning,
          next_action: review.nextAction,
        }),
      });
      setReviews((current) => [...current.filter((item) => item.tradeId !== review.tradeId), review]);
      clearDrafts(`review.${review.tradeId}`);
      setActiveReview(null);
      setNotice("Review saved to your TradeIQ account.");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not save this review.");
    }
    window.setTimeout(() => setNotice(""), 5000);
  }

  async function openReportEvidence(tradeId: string) {
    try {
      const trade = trades.find((item) => item.id === tradeId)
        ?? mapApiTrade(await apiRequest<ApiTrade>(`/trades/${tradeId}`));
      let review = reviews.find((item) => item.tradeId === tradeId) ?? null;
      if (!review) {
        const saved = await apiRequest<ApiReview>(`/trades/${tradeId}/reviews`).catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 404) return null;
          throw error;
        });
        if (saved) {
          review = {
            tradeId: saved.trade_id,
            planAdherence: saved.plan_adherence,
            learning: saved.learning,
            nextAction: saved.next_action,
          };
          setReviews((current) => [...current.filter((item) => item.tradeId !== tradeId), review as TradeReview]);
        }
      }
      setView("reviews");
      setActiveReview(trade);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not open this report evidence.");
    }
  }

  async function updateTimezone(value: string) {
    const previous = timezone;
    setTimezone(value);
    try {
      await apiRequest("/preferences", {
        method: "PATCH",
        body: JSON.stringify({ timezone: value }),
      });
    } catch (error) {
      setTimezone(previous);
      setActionError(error instanceof Error ? error.message : "Could not save the timezone preference.");
    }
  }

  async function importCsvFile(file: File) {
    setActionError("");
    if (file.size > 10 * 1024 * 1024) {
      setActionError("CSV import failed: the file must be 10 MB or smaller.");
      return;
    }
    try {
      const imported = importTradesCsv(await file.text());
      const createdIds = new Map<string, string>();
      for (const trade of imported.trades) {
        if (trade.outcome === "Planned" || trade.outcome === "Discarded") {
          const plan = await apiRequest<ApiPlan>("/plans", {
            method: "POST",
            body: JSON.stringify({
              symbol: trade.symbol,
              direction: trade.direction,
              strategy: trade.strategy,
              thesis: trade.plan,
            }),
          });
          if (trade.outcome === "Discarded") {
            await apiRequest(`/plans/${plan.id}/discard`, { method: "POST" });
          }
          createdIds.set(trade.id, plan.id);
          continue;
        }
        const isClosed = ["Win", "Loss", "Flat"].includes(trade.outcome);
        if (isClosed && trade.pnl === null) {
          throw new Error(`Trade ${trade.id} is closed but has no realized P&L.`);
        }
        const saved = await apiRequest<ApiTrade>("/trades", {
          method: "POST",
          body: JSON.stringify({
            symbol: trade.symbol,
            direction: trade.direction,
            strategy: trade.strategy,
            outcome: trade.outcome.toLowerCase(),
            pnl: trade.pnl,
            r_multiple: trade.rMultiple,
            entry_price: trade.entryPrice,
            exit_price: trade.exitPrice,
            size: trade.size,
            notes: trade.plan,
            opened_at: trade.date,
            closed_at: isClosed ? trade.date : null,
          }),
        });
        createdIds.set(trade.id, saved.id);
        await Promise.all([
          apiRequest(`/trades/${saved.id}/journal/strategy_setup`, {
            method: "PATCH",
            body: JSON.stringify({
              content: {
                setup_notes: trade.setupNotes ?? "",
                setup_emotion: trade.setupEmotion ?? "Neutral",
              },
            }),
          }),
          apiRequest(`/trades/${saved.id}/journal/journal_entries`, {
            method: "PATCH",
            body: JSON.stringify({ content: trade.journalEntries ?? [] }),
          }),
        ]);
      }
      for (const review of imported.reviews) {
        const tradeId = createdIds.get(review.tradeId);
        if (!tradeId) continue;
        await apiRequest(`/trades/${tradeId}/reviews`, {
          method: "POST",
          body: JSON.stringify({
            plan_adherence: review.planAdherence,
            learning: review.learning,
            next_action: review.nextAction,
          }),
        });
      }
      const workspace = await loadBackendWorkspace(scopeIds);
      setAccounts(workspace.accounts);
      setTrades(workspace.trades);
      setReviews(workspace.reviews);
      setNotice(`Uploaded ${imported.trades.length} records to your TradeIQ account.`);
      window.setTimeout(() => setNotice(""), 6000);
    } catch (error) {
      console.error("Unable to import the TradeIQ journal CSV.", error);
      setActionError(`CSV import stopped. Some earlier records may already be saved; refresh before retrying. ${error instanceof Error ? error.message : "The file could not be read."}`);
    }
  }

  function exportVisibleTrades(exportedTrades: Trade[]) {
    exportTradesCsv(exportedTrades, reviews);
  }

  if (apiStatus === "loading") {
    return <main className="auth-shell"><p className="auth-loading">Connecting to your TradeIQ account…</p></main>;
  }
  if (apiStatus === "checking" || apiStatus === "signed-out" || (apiStatus === "error" && !apiUser)) {
    return (
      <LandingPage
        apiError={apiError}
        onAuthenticated={(user) => {
          sessionRequestVersion.current += 1;
          setApiUser(user);
          setApiStatus("loading");
          setApiError("");
        }}
        onRetry={() => void checkApiSession()}
      />
    );
  }
  if (apiStatus === "error") {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <span className="eyebrow">TRADEIQ · DATA UNAVAILABLE</span>
          <h1>Could not load your workspace</h1>
          <p role="alert">{apiError}</p>
          <button className="button button-primary auth-submit" onClick={() => void checkApiSession()}>
            Retry
          </button>
          <button className="auth-mode-toggle" onClick={() => void signOut()}>Sign out</button>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <AppLogo />
        <div className="workspace-switcher"><div className="workspace-avatar">{userFirstName(apiUser).slice(0, 1)}</div><div><strong>{userFirstName(apiUser)}</strong><span>Personal workspace</span></div><Icon name="chevron" size={16} /></div>
        <span className="nav-section-label">WORKSPACE</span>
        <nav className="primary-nav" aria-label="Main navigation">{navigation.map((item) => <button key={item.id} aria-label={item.label} title={item.label} className={`nav-item ${view === item.id ? "selected" : ""}`} onClick={() => setView(item.id)}>{(() => { const NavIcon = navIcons[item.id]; return <NavIcon className="nav-icon" size={18} strokeWidth={1.85} aria-hidden="true" />; })()}<span>{item.label}</span>{item.id === "reviews" && pendingReviewCount > 0 && <span className="nav-count">{pendingReviewCount}</span>}</button>)}</nav>
        <div className="sidebar-bottom"><div className="sidebar-help"><span className="help-mark">i</span><div><strong>Built for better reviews</strong><p>Your data, intent, and insights in one place.</p></div></div><button className="profile-button" onClick={() => void signOut()}><div className="profile-avatar">{userFirstName(apiUser).slice(0, 1)}</div><div><strong>{userFirstName(apiUser)}</strong><span>Sign out</span></div><Icon name="more" size={17} /></button></div>
      </aside>
      <main className="main-area">
        <header className="topbar"><div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-divider">/</span><strong>{view === "overview" ? "Overview" : currentView.title}</strong></div><div className="topbar-actions"><div className="sync-state"><span className="status-dot" />Account synced</div><button className="icon-button notification-button" aria-label="Notifications"><Icon name="bell" size={18} /><i /></button><div className="topbar-divider" /><div className="topbar-user"><div className="profile-avatar">{userFirstName(apiUser).slice(0, 1)}</div><Icon name="chevron" size={15} /></div></div></header>
        <div className="page-content"><div className="page-heading"><div><span className="welcome-label">{view === "overview" ? "YOUR TRADING WORKSPACE" : "TRADEIQ WORKSPACE"}</span><h1>{view === "overview" ? `${greeting(timezone)}, ${userFirstName(apiUser)}` : currentView.title}</h1><p>{currentView.description}</p></div><div className="heading-actions">{view === "overview" && <DashboardDateRangePicker value={dateRange} onChange={setDateRange} />}<button className="button button-primary" onClick={() => setCaptureOpen(true)}><Icon name="plus" size={17} /> Quick capture</button></div></div>
          {legacyDataAvailable && <div className="success-notice" role="status"><span>Your earlier browser workspace is still preserved on this device. Export its CSV and import it into this account to migrate records.</span><button className="button button-quiet" onClick={() => setLegacyDataAvailable(false)}>Dismiss</button></div>}
          {actionError && <div className="action-alert" role="alert"><Icon name="close" size={16} /><span>{actionError}</span><button className="icon-button" onClick={() => setActionError("")} aria-label="Dismiss error"><Icon name="close" size={14} /></button></div>}
          {notice && <div className="success-notice" role="status"><Icon name="check" size={17} />{notice}<button onClick={() => setNotice("")} aria-label="Dismiss notification"><Icon name="close" size={15} /></button></div>}
          <DetectedAccountsBanner
            items={detected.items}
            onDismissed={detected.remove}
            onConnected={(id, accountId) => {
              detected.remove(id);
              saveView([...scopeIds, accountId]);
              setNotice("Account connected and added to your journal view.");
              loadBackendWorkspace([...scopeIds, accountId]).then((workspace) => {
                setAccounts(workspace.accounts);
                setTrades(workspace.trades);
                setReviews(workspace.reviews);
              }).catch(() => undefined);
            }}
          />
          <ViewContent key={view} view={view} trades={trades} reviews={reviews} reviewedIds={reviewedIds} timezone={timezone} dateRange={dateRange} accounts={accounts} viewIds={scopeIds} onToggleView={toggleView} onClearView={() => saveView([])} onTimezoneChange={(value) => void updateTimezone(value)} onQuickCapture={() => setCaptureOpen(true)} onNavigate={setView} onReviewStart={setActiveReview} onReportEvidenceOpen={(tradeId) => void openReportEvidence(tradeId)} onRecordFill={setActivePlan} onManageTrade={setActivePlan} onDiscardPlan={discardPlan} onOpenAccountSetup={() => setAccountSetupOpen(true)} onConnectAccount={connectAccount} onSyncAccount={syncAccount} onRevokeAccount={revokeAccount} onDeleteAccount={setDeletingAccount} onEditAccount={setEditingAccount} onRefreshAccount={refreshAccount} onExport={exportVisibleTrades} onImportCsv={(file) => void importCsvFile(file)} onBulkRemove={bulkRemove} onBulkStrategy={bulkStrategy} />
        </div>
      </main>
      {captureOpen && <QuickCaptureModal onClose={() => setCaptureOpen(false)} onSave={savePlan} />}
      {activePlan && <ExecutionModal key={activePlan.id} plan={activePlan} serverErrors={fillErrors} onClose={() => { setActivePlan(null); setFillErrors({}); }} onSave={recordFill} />}
      {activeReview && <ReviewModal key={activeReview.id} trade={activeReview} existingReview={reviews.find((review) => review.tradeId === activeReview.id)} onClose={() => setActiveReview(null)} onSave={completeReview} />}
      {accountSetupOpen && <AccountSetupModal method={mt5Method} onClose={() => setAccountSetupOpen(false)} onSave={saveAccountSetup} />}
      {editingAccount && <EditAccountModal account={editingAccount} onClose={() => setEditingAccount(null)} onSave={renameAccount} />}
      {deletingAccount && <DeleteAccountModal account={deletingAccount} onClose={() => setDeletingAccount(null)} onConfirm={deleteAccount} />}
      {connectingAccount && <MT5ConnectModal method={mt5Method} account={connectingAccount} onClose={() => setConnectingAccount(null)} onConnect={connectMt5Account} />}
      {verifying && (
        <ConnectionVerifier
          accountId={verifying.id}
          accountName={verifying.name}
          onRepair={() => void updateEaSetup(verifying.id, verifying.name)}
          onConnected={() => { const a = accounts.find((x) => x.id === verifying.id); if (a) void refreshAccount(a); }}
          onClose={() => setVerifying(null)}
        />
      )}
      {eaWizard && <EaSetupWizard {...eaWizard} onClose={() => setEaWizard(null)} onFinish={() => {
        const setup = eaWizard;
        setEaWizard(null);
        if (setup.accountId) setVerifying({ id: setup.accountId, name: setup.accountName });
      }} />}
      {oneTimeSecret && <OneTimeSecretDialog secret={oneTimeSecret} onClose={() => setOneTimeSecret(null)} />}
    </div>
  );
}
