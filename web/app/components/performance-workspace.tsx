"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../api";

export type DateRange = { preset: string; startDate: string; endDate: string };
export type MetricSet = {
  trade_count: number;
  wins: number;
  losses: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  net_pnl: number | null;
  expectancy_r: number | null;
  average_win_r: number | null;
  average_loss_r: number | null;
  max_drawdown_r: number | null;
  max_drawdown_recovery_seconds: number | null;
  average_holding_minutes: number | null;
  average_mae_r: number | null;
  average_mfe_r: number | null;
  mae_sample_count: number;
  mfe_sample_count: number;
  r_sample_count: number;
  r_missing_count: number;
  sample_warning: string | null;
  r_sample_warning: string | null;
  currency: string | null;
};
export type Cohort = MetricSet & { key: string };
type Revenge = {
  window_minutes: number;
  trade_count: number;
  metrics: MetricSet;
  comparison_without_flag: MetricSet;
};
export type Recommendation = {
  priority: number;
  focus: string;
  recommendation: string;
  confidence: string;
};
export type Roadmap = {
  id?: string;
  recommendations: Recommendation[];
  progress_status: "pending" | "in_progress" | "completed" | "adjusted";
  progress_notes: string | null;
};
export type Insight = { id: string; tone: "positive" | "negative" | "neutral"; text: string };
export type PerformanceData = {
  metrics: MetricSet | null;
  strategies: Cohort[];
  byHour: Cohort[];
  byWeekday: Cohort[];
  revenge: Revenge | null;
  adherence: Cohort[];
  emotions: Cohort[];
  ruleBreaks: Cohort[];
  confluences: Cohort[];
  roadmap: Roadmap | null;
  limitation: string;
  loading: boolean;
  error: string;
  saveRoadmap: () => Promise<void>;
  updateProgress: (status: Roadmap["progress_status"], notes?: string | null) => Promise<void>;
};

const MIN_SAMPLE = 30;

function queryString(accountId: string | null, range: DateRange, timezone: string) {
  const params = new URLSearchParams({ timezone: timezone === "local" ? "UTC" : timezone });
  if (accountId) params.set("account_id", accountId);
  if (range.startDate) params.set("start_date", range.startDate);
  if (range.endDate) params.set("end_date", range.endDate);
  return `?${params.toString()}`;
}

export function fmt(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}
export function fmtR(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}R`;
}
function duration(seconds: number | null) {
  if (seconds == null) return "—";
  const hours = Math.round(seconds / 3600);
  return hours < 24 ? `${hours}h` : `${Math.round(hours / 24)}d`;
}

export function strategyStatus(row: MetricSet): { label: string; tone: string } {
  if (row.r_sample_count < MIN_SAMPLE) return { label: "Building sample", tone: "neutral" };
  if ((row.expectancy_r ?? 0) > 0.1) return { label: "Edge", tone: "positive" };
  if ((row.expectancy_r ?? 0) < 0) return { label: "Leak", tone: "negative" };
  return { label: "Neutral", tone: "neutral" };
}

export function profitFactorTone(value: number | null) {
  if (value == null) return "";
  return value > 1.5 ? "pf-good" : value >= 1 ? "pf-mid" : "pf-bad";
}

function buildInsights(data: PerformanceData): Insight[] {
  const insights: Insight[] = [];
  const rated = data.strategies.filter((row) => row.expectancy_r != null && row.r_sample_count >= 5);
  if (rated.length) {
    const best = [...rated].sort((a, b) => (b.expectancy_r ?? 0) - (a.expectancy_r ?? 0))[0];
    insights.push({
      id: "best-strategy",
      tone: (best.expectancy_r ?? 0) > 0 ? "positive" : "neutral",
      text: `${best.key} has your highest observed expectancy (${fmtR(best.expectancy_r)} over ${best.r_sample_count} recorded R trades)${best.r_sample_count < MIN_SAMPLE ? " — provisional sample." : "."}`,
    });
    const worst = [...rated].sort((a, b) => (a.expectancy_r ?? 0) - (b.expectancy_r ?? 0))[0];
    if (worst.key !== best.key && (worst.expectancy_r ?? 0) < 0) {
      insights.push({
        id: "worst-strategy",
        tone: "negative",
        text: `${worst.key} is currently negative (${fmtR(worst.expectancy_r)} over ${worst.r_sample_count} trades). Review before adding size.`,
      });
    }
  }
  const revenge = data.revenge;
  if (revenge && revenge.trade_count > 0) {
    insights.push({
      id: "revenge",
      tone: "negative",
      text: `${revenge.trade_count} trades opened within ${revenge.window_minutes} min of a loss; expectancy ${fmtR(revenge.metrics.expectancy_r)} vs ${fmtR(revenge.comparison_without_flag.expectancy_r)} otherwise.`,
    });
  }
  const hours = data.byHour.filter((row) => row.trade_count >= 5 && row.win_rate_pct != null);
  if (hours.length) {
    const weakest = [...hours].sort((a, b) => (a.win_rate_pct ?? 0) - (b.win_rate_pct ?? 0))[0];
    insights.push({
      id: "hour",
      tone: "neutral",
      text: `Your win rate is lowest at ${weakest.key}:00 (${fmt(weakest.win_rate_pct, 0)}% over ${weakest.trade_count} trades).`,
    });
  }
  const breaks = data.ruleBreaks.filter((row) => row.trade_count >= 3 && (row.expectancy_r ?? 0) < 0);
  if (breaks.length) {
    const worst = [...breaks].sort((a, b) => (a.expectancy_r ?? 0) - (b.expectancy_r ?? 0))[0];
    insights.push({
      id: "rule-break",
      tone: "negative",
      text: `Trades tagged “${worst.key}” average ${fmtR(worst.expectancy_r)} across ${worst.trade_count} trades.`,
    });
  }
  if (data.metrics && data.metrics.r_missing_count > 0) {
    insights.push({
      id: "missing-r",
      tone: "neutral",
      text: `${data.metrics.r_missing_count} closed trades have no recorded R — add risk to sharpen every metric here.`,
    });
  }
  return insights;
}

export function usePerformanceData(
  accountId: string | null,
  dateRange: DateRange,
  timezone: string,
): PerformanceData & { insights: Insight[] } {
  const [state, setState] = useState<Omit<PerformanceData, "saveRoadmap" | "updateProgress">>({
    metrics: null,
    strategies: [],
    byHour: [],
    byWeekday: [],
    revenge: null,
    adherence: [],
    emotions: [],
    ruleBreaks: [],
    confluences: [],
    roadmap: null,
    limitation: "",
    loading: true,
    error: "",
  });
  const query = useMemo(
    () => queryString(accountId, dateRange, timezone),
    [accountId, dateRange, timezone],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setState((current) => ({ ...current, loading: true, error: "" }));
      try {
        const [snap, strategies, time, behavior, roadmap, saved] = await Promise.all([
          apiRequest<{ metrics: MetricSet }>(`/performance/edge-snapshot${query}`),
          apiRequest<{ strategies: Cohort[] }>(`/performance/strategies${query}`),
          apiRequest<{ by_hour: Cohort[]; by_weekday: Cohort[] }>(`/performance/time${query}`),
          apiRequest<{
            revenge_timing: Revenge;
            plan_adherence: Cohort[];
            emotional_state: Cohort[];
            recorded_rule_breaks: Cohort[];
            recorded_confluences: Cohort[];
            interpretation_limit: string;
          }>(`/performance/behavior${query}`),
          apiRequest<{ current_focus_areas: Recommendation[] }>(`/performance/roadmap${query}`),
          apiRequest<Array<Roadmap & { account_id: string | null }>>("/performance/roadmaps?limit=20"),
        ]);
        if (cancelled) return;
        setState({
          metrics: snap.metrics,
          strategies: strategies.strategies,
          byHour: time.by_hour,
          byWeekday: time.by_weekday,
          revenge: behavior.revenge_timing,
          adherence: behavior.plan_adherence,
          emotions: behavior.emotional_state,
          ruleBreaks: behavior.recorded_rule_breaks,
          confluences: behavior.recorded_confluences,
          roadmap: saved.find((item) => item.account_id === accountId) ?? {
            recommendations: roadmap.current_focus_areas,
            progress_status: "pending",
            progress_notes: null,
          },
          limitation: behavior.interpretation_limit,
          loading: false,
          error: "",
        });
      } catch (cause: unknown) {
        if (!cancelled) {
          setState((current) => ({
            ...current,
            loading: false,
            error: cause instanceof Error ? cause.message : "Performance analysis is unavailable.",
          }));
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [query, accountId]);

  const saveRoadmap = useCallback(async () => {
    try {
      const saved = await apiRequest<Roadmap>(`/performance/roadmaps${query}`, { method: "POST" });
      setState((current) => ({ ...current, roadmap: saved, error: "" }));
    } catch (cause: unknown) {
      setState((current) => ({
        ...current,
        error: cause instanceof Error ? cause.message : "Could not save this roadmap.",
      }));
    }
  }, [query]);

  const updateProgress = useCallback(
    async (progress_status: Roadmap["progress_status"], notes?: string | null) => {
      const roadmapId = state.roadmap?.id;
      if (!roadmapId) return;
      try {
        const updated = await apiRequest<Roadmap>(`/performance/roadmaps/${roadmapId}`, {
          method: "PATCH",
          body: JSON.stringify({
            progress_status,
            progress_notes: notes === undefined ? state.roadmap?.progress_notes : notes,
          }),
        });
        setState((current) => ({
          ...current,
          roadmap: current.roadmap ? { ...current.roadmap, ...updated } : updated,
          error: "",
        }));
      } catch (cause: unknown) {
        setState((current) => ({
          ...current,
          error: cause instanceof Error ? cause.message : "Could not update roadmap progress.",
        }));
      }
    },
    [state.roadmap?.id, state.roadmap?.progress_notes],
  );

  const data: PerformanceData = { ...state, saveRoadmap, updateProgress };
  const insights = useMemo(
    () => buildInsights(data),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state.strategies, state.byHour, state.revenge, state.ruleBreaks, state.metrics],
  );
  return { ...data, insights };
}

export type PerformanceBundle = ReturnType<typeof usePerformanceData>;

function InsightList({ insights, limit }: { insights: Insight[]; limit?: number }) {
  if (!insights.length) {
    return <p className="empty-inline">Insights appear once you have closed trades with strategies and recorded R.</p>;
  }
  return (
    <ul className="insight-list">
      {insights.slice(0, limit ?? insights.length).map((item) => (
        <li key={item.id} className={`insight-${item.tone}`}>{item.text}</li>
      ))}
    </ul>
  );
}

export function EdgeSnapshot({
  data,
  onViewAnalysis,
  onAsk,
  hideViewLink = false,
}: {
  data: PerformanceBundle;
  onViewAnalysis: () => void;
  onAsk: () => void;
  hideViewLink?: boolean;
}) {
  const metrics = data.metrics;
  const rated = data.strategies.filter((row) => row.expectancy_r != null);
  const best = [...rated].sort((a, b) => (b.expectancy_r ?? 0) - (a.expectancy_r ?? 0))[0];
  const worst = [...rated].sort((a, b) => (a.expectancy_r ?? 0) - (b.expectancy_r ?? 0))[0];
  return (
    <section className="panel edge-snapshot">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">EDGE SNAPSHOT</span>
          <h2>What your data reveals</h2>
          <p>Computed only from your own closed trades.</p>
        </div>
      </div>
      {data.loading ? <div className="intelligence-loading" /> : data.error ? <p className="empty-inline">{data.error}</p> : (
        <div className="edge-body">
          <div className="edge-left">
            <div className="edge-hero">
              <span>Expectancy</span>
              <strong className={(metrics?.expectancy_r ?? 0) >= 0 ? "positive" : "negative"}>{fmtR(metrics?.expectancy_r)}</strong>
              <small>Average edge per trade · {metrics?.r_sample_count ?? 0} recorded R</small>
            </div>
            <div className="edge-facts">
              <div><span>Profit factor</span><strong className={profitFactorTone(metrics?.profit_factor ?? null)}>{fmt(metrics?.profit_factor)}</strong></div>
              <div><span>Best strategy</span><strong>{best?.key ?? "—"}</strong></div>
              <div><span>Weakest / leak</span><strong>{worst && worst.key !== best?.key && (worst.expectancy_r ?? 0) < 0 ? worst.key : "—"}</strong></div>
            </div>
            {(metrics?.sample_warning || metrics?.r_sample_warning) && <small className="edge-caveat">{metrics.sample_warning ?? metrics.r_sample_warning}</small>}
          </div>
          <div className="edge-right">
            <span className="eyebrow">TOP INSIGHTS</span>
            <InsightList insights={data.insights} limit={3} />
          </div>
        </div>
      )}
      <div className="edge-footer">
        {hideViewLink ? <span /> : <button className="text-link" onClick={onViewAnalysis}>View full analysis →</button>}
        <button className="button button-outline" onClick={onAsk}>Ask Agent</button>
      </div>
    </section>
  );
}

export function RoadmapWidget({ data }: { data: PerformanceBundle }) {
  const roadmap = data.roadmap;
  const [notes, setNotes] = useState<string | null>(null);
  return (
    <div className="roadmap-card">
      <div className="subsection-heading">
        <div><span className="eyebrow">DEVELOPMENT ROADMAP</span><h3>Current focus</h3></div>
        <span className="roadmap-status">{roadmap?.id ? roadmap.progress_status.replace("_", " ") : "unsaved"}</span>
      </div>
      {roadmap?.recommendations.slice(0, 3).map((item) => (
        <div className="roadmap-item" key={`${item.priority}-${item.focus}`}>
          <span>{item.priority}</span>
          <div><strong>{item.focus}</strong><p>{item.recommendation}</p></div>
        </div>
      ))}
      {roadmap?.id && <div className="progress-track" aria-hidden><span style={{ width: `${{ pending: 5, in_progress: 50, adjusted: 65, completed: 100 }[roadmap.progress_status]}%` }} /></div>}
      <div className="roadmap-actions">
        {roadmap?.id ? (
          <>
            <select aria-label="Roadmap progress" value={roadmap.progress_status} onChange={(event) => void data.updateProgress(event.target.value as Roadmap["progress_status"])}>
              <option value="pending">Not started</option>
              <option value="in_progress">In progress</option>
              <option value="completed">Completed</option>
              <option value="adjusted">Adjusted</option>
            </select>
            <input aria-label="Progress notes" placeholder="Progress note" value={notes ?? roadmap.progress_notes ?? ""} onChange={(event) => setNotes(event.target.value)} onBlur={() => notes !== null && void data.updateProgress(roadmap.progress_status, notes)} />
          </>
        ) : (
          <button className="button button-outline" onClick={() => void data.saveRoadmap()}>Save as my roadmap</button>
        )}
      </div>
    </div>
  );
}

function strategyVerdict(row: Cohort) {
  const n = row.r_sample_count;
  if (row.expectancy_r == null) return `No R recorded yet. ${fmt(row.win_rate_pct, 0)}% of ${row.trade_count} trades won.`;
  if (n < MIN_SAMPLE) return `Early read: ${fmtR(row.expectancy_r)} per trade over ${n} recorded trades. Needs ${MIN_SAMPLE - n} more for a firm view.`;
  return row.expectancy_r > 0.1 ? `Working: earns ${fmtR(row.expectancy_r)} on average per trade.` : row.expectancy_r < 0 ? `Leaking: loses ${fmtR(Math.abs(row.expectancy_r))} on average per trade.` : "Roughly break-even per trade.";
}

export function StrategyTable({ rows }: { rows: Cohort[] }) {
  if (!rows.length) return <p className="empty-inline">Tag a strategy on your trades to start ranking your edge.</p>;
  return (
    <div className="strat-grid">
      {rows.map((row, index) => {
        const status = strategyStatus(row);
        const win = row.win_rate_pct ?? 0;
        const hasPayoff = row.average_win_r != null && row.average_loss_r != null;
        const span = Math.max(0.01, Math.abs(row.average_win_r ?? 0), Math.abs(row.average_loss_r ?? 0));
        return (
          <article className={`strat-card tone-${status.tone}`} key={row.key}>
            <header>
              <span className={`strat-rank rank-${index + 1}`}>{index + 1}</span>
              <div><strong>{row.key}</strong><small>{row.trade_count} trades · {row.wins}W {row.losses}L</small></div>
              <span className={`status-chip chip-${status.tone}`}>{status.label}</span>
            </header>
            <div className="strat-main">
              <div className="strat-ring" style={{ "--win": `${win}%` } as React.CSSProperties}><b>{fmt(win, 0)}%</b><small>win rate</small></div>
              <div className="strat-stats">
                <div><span>Expectancy</span><strong className={(row.expectancy_r ?? 0) >= 0 ? "positive" : "negative"}>{fmtR(row.expectancy_r)}</strong></div>
                <div><span>Profit factor</span><strong className={profitFactorTone(row.profit_factor)}>{fmt(row.profit_factor)}</strong></div>
                <div><span>Avg hold</span><strong>{row.average_holding_minutes == null ? "—" : `${Math.round(row.average_holding_minutes)}m`}</strong></div>
                <div><span>Max drawdown</span><strong>{row.max_drawdown_r == null ? "—" : `${fmt(row.max_drawdown_r)}R`}</strong></div>
              </div>
            </div>
            {hasPayoff ? (
              <div className="strat-payoff" aria-label="Average win versus average loss">
                <div><em>Avg win</em><div className="strat-bar"><i className="up" style={{ width: `${(Math.abs(row.average_win_r ?? 0) / span) * 100}%` }} /></div><b>{fmtR(row.average_win_r)}</b></div>
                <div><em>Avg loss</em><div className="strat-bar"><i className="down" style={{ width: `${(Math.abs(row.average_loss_r ?? 0) / span) * 100}%` }} /></div><b>{fmtR(row.average_loss_r)}</b></div>
              </div>
            ) : (
              <div className="strat-payoff"><div><em>Wins vs losses</em><div className="strat-bar split"><i className="up" style={{ width: `${win}%` }} /><i className="down" style={{ width: `${100 - win}%` }} /></div></div></div>
            )}
            <p className="strat-verdict">{strategyVerdict(row)}</p>
            <div className="strat-sample" title={`${row.r_sample_count} of ${MIN_SAMPLE} trades with recorded R`}><div><i style={{ width: `${Math.min(100, (row.r_sample_count / MIN_SAMPLE) * 100)}%` }} /></div><small>{row.r_sample_count}/{MIN_SAMPLE} recorded R for a reliable read</small></div>
          </article>
        );
      })}
    </div>
  );
}

type Lens = "r" | "win";

// Use expectancy when R is recorded; otherwise fall back to win rate so the chart is never blank.
function pickLens(rows: Cohort[]): Lens {
  return rows.some((row) => row.expectancy_r != null) ? "r" : "win";
}
function lensValue(row: Cohort, lens: Lens) {
  return lens === "r" ? row.expectancy_r : row.win_rate_pct;
}
function lensTone(row: Cohort, lens: Lens) {
  const value = lensValue(row, lens);
  if (value == null) return "none";
  if (lens === "r") return value > 0.05 ? "up" : value < -0.05 ? "down" : "flat";
  return value >= 55 ? "up" : value < 45 ? "down" : "flat";
}
function lensText(row: Cohort, lens: Lens) {
  return lens === "r" ? fmtR(row.expectancy_r) : `${fmt(row.win_rate_pct, 0)}%`;
}
const lensNote = (lens: Lens) => (lens === "r" ? "Average R per trade. Green is profitable, red loses." : "Share of trades that won. Add R-multiples to your trades to see expectancy instead.");

export function CohortBars({ rows, label }: { rows: Cohort[]; label: (key: string) => string }) {
  if (!rows.length) return <p className="empty-inline">No data yet.</p>;
  const lens = pickLens(rows);
  const max = Math.max(0.01, ...rows.map((row) => Math.abs(row.expectancy_r ?? 0)));
  return (
    <div className="cohort-bars">
      <p className="cohort-caption">{lensNote(lens)}</p>
      {rows.map((row) => {
        const tone = lensTone(row, lens);
        const width = lens === "win" ? row.win_rate_pct ?? 0 : row.expectancy_r == null ? 0 : (Math.abs(row.expectancy_r) / max) * 100;
        const thin = row.trade_count < 5;
        return (
          <div className={`cohort-row ${thin ? "thin" : ""}`} key={row.key} title={thin ? "Small sample: treat as a hint, not a pattern" : undefined}>
            <span>{label(row.key)}</span>
            <div className="cohort-track">{lens === "win" && <em aria-hidden="true" />}<i className={tone} style={{ width: `${Math.max(width, 3)}%` }} /></div>
            <b className={tone}>{lensText(row, lens)}</b>
            <small>{row.trade_count} {row.trade_count === 1 ? "trade" : "trades"} · {row.wins}W {row.losses}L{thin ? " · few" : ""}</small>
          </div>
        );
      })}
    </div>
  );
}

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function TimeHighlights({ hours, days }: { hours: Cohort[]; days: Cohort[] }) {
  const lens = pickLens([...hours, ...days]);
  const ranked = (rows: Cohort[]) => rows.filter((row) => row.trade_count >= 3 && lensValue(row, lens) != null).sort((a, b) => (lensValue(b, lens) ?? 0) - (lensValue(a, lens) ?? 0));
  const h = ranked(hours);
  const d = ranked(days);
  const busiest = [...hours].sort((a, b) => b.trade_count - a.trade_count)[0];
  const cards: Array<[string, string, string, string]> = [
    ["Best hour", h[0] ? `${h[0].key}:00` : "—", h[0] ? `${lensText(h[0], lens)} over ${h[0].trade_count} trades` : "Needs 3+ trades in an hour", "up"],
    ["Weakest hour", h.length > 1 ? `${h[h.length - 1].key}:00` : "—", h.length > 1 ? `${lensText(h[h.length - 1], lens)} over ${h[h.length - 1].trade_count} trades` : "Needs 3+ trades in an hour", "down"],
    ["Best day", d[0] ? d[0].key : "—", d[0] ? `${lensText(d[0], lens)} over ${d[0].trade_count} trades` : "Needs 3+ trades in a day", "up"],
    ["Busiest hour", busiest ? `${busiest.key}:00` : "—", busiest ? `${busiest.trade_count} trades opened` : "", "flat"],
  ];
  return <div className="time-highlights">{cards.map(([title, value, note, tone]) => <div key={title} className={`time-card ${tone}`}><span>{title}</span><strong>{value}</strong><small>{note}</small></div>)}</div>;
}

function HourStrip({ rows }: { rows: Cohort[] }) {
  const lens = pickLens(rows);
  const byHour = new Map(rows.map((row) => [Number(row.key), row]));
  const peak = Math.max(1, ...rows.map((row) => row.trade_count));
  return (
    <div>
      <div className="hour-strip" role="list" aria-label="Performance by hour of day">
        {Array.from({ length: 24 }, (_, hour) => {
          const row = byHour.get(hour);
          const tone = row ? lensTone(row, lens) : "none";
          return (
            <div role="listitem" key={hour} className={`hour-cell ${tone}`} style={{ opacity: row ? 0.45 + 0.55 * (row.trade_count / peak) : 1 }} title={row ? `${String(hour).padStart(2, "0")}:00 · ${row.trade_count} trades · ${lensText(row, lens)} · ${row.wins}W ${row.losses}L` : `${String(hour).padStart(2, "0")}:00 · no trades`}>
              <b>{row ? row.trade_count : ""}</b><small>{String(hour).padStart(2, "0")}</small>
            </div>
          );
        })}
      </div>
      <div className="hour-legend"><span><i className="up" />Doing well</span><span><i className="flat" />Break-even</span><span><i className="down" />Losing</span><span><i className="none" />No trades</span><span>Number = trades · stronger colour = more trades</span></div>
      <p className="cohort-caption">{lensNote(lens)}</p>
    </div>
  );
}

export function TimeAnalysis({ data }: { data: PerformanceBundle }) {
  const weekdays = [...data.byWeekday].sort((a, b) => WEEKDAYS.indexOf(a.key) - WEEKDAYS.indexOf(b.key));
  return (
    <div className="content-stack">
      <TimeHighlights hours={data.byHour} days={weekdays} />
      <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">BY HOUR</span><h3>When you trade, around the clock</h3></div></div><HourStrip rows={data.byHour} /></div>
      <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">BY WEEKDAY</span><h3>How each day performs</h3></div></div><CohortBars rows={weekdays} label={(key) => key.slice(0, 3)} /></div>
      <p className="muted-small analysis-note">Times use your selected timezone. Windows describe history; they do not prove a time causes edge.</p>
    </div>
  );
}

export function BehaviorLeaks({ data }: { data: PerformanceBundle }) {
  const revenge = data.revenge;
  return (
    <div className="analysis-grid">
      <div className="panel">
        <div className="subsection-heading"><div><span className="eyebrow">TIMING FLAG</span><h3>Trades soon after a loss</h3></div></div>
        {revenge && revenge.trade_count > 0 ? (
          <div className="leak-compare">
            <div><span>Within {revenge.window_minutes} min of a loss</span><strong>{fmtR(revenge.metrics.expectancy_r)}</strong><small>{revenge.trade_count} trades</small></div>
            <div><span>All other trades</span><strong>{fmtR(revenge.comparison_without_flag.expectancy_r)}</strong><small>{revenge.comparison_without_flag.trade_count} trades</small></div>
          </div>
        ) : <p className="empty-inline">No trades opened shortly after a loss in this range.</p>}
      </div>
      <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">RULE BREAKS</span><h3>Recorded rule breaks</h3></div></div><CohortBars rows={data.ruleBreaks} label={(key) => key} /></div>
      <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">EMOTION</span><h3>Emotional state</h3></div></div><CohortBars rows={data.emotions} label={(key) => key} /></div>
      <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">PLAN ADHERENCE</span><h3>Followed the plan?</h3></div></div><CohortBars rows={data.adherence} label={(key) => key} /></div>
      <p className="muted-small analysis-note">{data.limitation}</p>
    </div>
  );
}

export function ExcursionPanel({ data }: { data: PerformanceBundle }) {
  const metrics = data.metrics;
  if (!metrics) return null;
  const recorded = Math.min(metrics.mae_sample_count, metrics.mfe_sample_count);
  const left = metrics.average_mfe_r != null && metrics.expectancy_r != null ? metrics.average_mfe_r - (metrics.average_win_r ?? 0) : null;
  return (
    <div className="panel">
      <div className="subsection-heading"><div><span className="eyebrow">MAE / MFE</span><h3>Exit efficiency</h3></div><span className="muted-small">{recorded} trades with excursions</span></div>
      <div className="intelligence-metrics">
        <div><span>Average MAE</span><strong>{fmtR(metrics.average_mae_r)}</strong><small>worst drawdown before exit</small></div>
        <div><span>Average MFE</span><strong>{fmtR(metrics.average_mfe_r)}</strong><small>best open profit</small></div>
        <div><span>Average win</span><strong>{fmtR(metrics.average_win_r)}</strong><small>realized</small></div>
        <div><span>Possible gap</span><strong>{left == null ? "—" : fmtR(left)}</strong><small>MFE minus average win</small></div>
      </div>
      <p className="muted-small analysis-note">Excursions are only shown when recorded; nothing is estimated. {recorded < MIN_SAMPLE ? "Sample is too small to judge stop width or exits." : ""}</p>
    </div>
  );
}

export function RDistribution({ values }: { values: number[] }) {
  if (!values.length) return <p className="empty-inline">Record R-multiples on closed trades to see your payoff shape.</p>;
  const bucketOf = (value: number) => Math.min(6, Math.max(0, Math.floor(value) + 3));
  const counts = [0, 1, 2, 3, 4, 5, 6].map((index) => values.filter((value) => bucketOf(value) === index).length);
  const max = Math.max(1, ...counts);
  const labels = ["< −2R", "−2 to −1", "−1 to 0", "0 to 1", "1 to 2", "2 to 3", "≥ 3R"];
  return (
    <div className="r-hist">
      {counts.map((count, index) => (
        <div key={labels[index]} className="r-bar"><i className={index < 3 ? "down" : "up"} style={{ height: `${(count / max) * 100}%` }} /><b>{count}</b><span>{labels[index]}</span></div>
      ))}
    </div>
  );
}

export function AskAgentPanel({ data, onClose }: { data: PerformanceBundle; onClose: () => void }) {
  const [question, setQuestion] = useState("focus");
  const rated = data.strategies.filter((row) => row.expectancy_r != null);
  const best = [...rated].sort((a, b) => (b.expectancy_r ?? 0) - (a.expectancy_r ?? 0))[0];
  const answers: Record<string, { title: string; body: string }> = {
    best: { title: "Which setup has the best observed edge?", body: best ? `${best.key}: ${fmtR(best.expectancy_r)} across ${best.r_sample_count} recorded-R trades. ${best.r_sample_count < MIN_SAMPLE ? "That is a provisional sample, not proof of an edge." : "Still an association in your history, not a forecast."}` : "No strategy has recorded R yet." },
    leak: { title: "Where am I leaking?", body: data.insights.filter((item) => item.tone === "negative").map((item) => item.text).join(" ") || "No negative pattern is visible with the current sample." },
    focus: { title: "What should I focus on?", body: data.roadmap?.recommendations.map((item) => `${item.priority}. ${item.focus}`).join(" ") || "Keep logging trades to generate a roadmap." },
    time: { title: "When do I trade best?", body: data.insights.find((item) => item.id === "hour")?.text ?? "Not enough trades per hour to compare yet." },
  };
  const answer = answers[question];
  return (
    <aside className="agent-drawer" role="dialog" aria-label="Ask the performance agent">
      <div className="panel-heading"><div><span className="eyebrow">PERFORMANCE AGENT</span><h2>Ask your data</h2><p>Answers come from your own records only. No outside AI sees them.</p></div><button className="icon-button" aria-label="Close" onClick={onClose}>×</button></div>
      <div className="agent-chips">{Object.entries(answers).map(([key, value]) => <button key={key} className={`chip ${question === key ? "active" : ""}`} onClick={() => setQuestion(key)}>{value.title}</button>)}</div>
      <div className="agent-answer"><strong>{answer.title}</strong><p>{answer.body}</p></div>
    </aside>
  );
}

export type AnalyticsTab = "overview" | "strategies" | "time" | "behavior" | "excursions" | "insights";
const TABS: Array<[AnalyticsTab, string]> = [
  ["overview", "Overview"], ["strategies", "Strategies"], ["time", "Time analysis"],
  ["behavior", "Behavior"], ["excursions", "MAE / MFE"], ["insights", "Agent insights"],
];

export function AnalyticsWorkspace({ data, rValues }: { data: PerformanceBundle; rValues: number[] }) {
  const [tab, setTab] = useState<AnalyticsTab>("overview");
  const metrics = data.metrics;
  return (
    <section className="intelligence-workspace">
      <div className="analytics-tabs" role="tablist">{TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>)}</div>
      {data.error && <p className="form-error" role="alert">{data.error}</p>}
      {data.loading ? <div className="panel"><div className="intelligence-loading" /></div> : (
        <>
          {tab === "overview" && metrics && (
            <>
              <div className="intelligence-metrics panel">
                <div><span>Expectancy</span><strong>{fmtR(metrics.expectancy_r)}</strong><small>{metrics.r_sample_count} recorded R</small></div>
                <div><span>Profit factor</span><strong className={profitFactorTone(metrics.profit_factor)}>{fmt(metrics.profit_factor)}</strong><small>{metrics.currency ?? "Mixed / unavailable"}</small></div>
                <div><span>Avg win / loss</span><strong>{fmtR(metrics.average_win_r)} / {fmtR(metrics.average_loss_r)}</strong><small>payoff structure</small></div>
                <div><span>Max drawdown</span><strong>{fmt(metrics.max_drawdown_r)}R</strong><small>recovery {duration(metrics.max_drawdown_recovery_seconds)}</small></div>
              </div>
              {(metrics.sample_warning || metrics.r_sample_warning) && <div className="intelligence-warning"><strong>Sample quality</strong><span>{metrics.sample_warning ?? metrics.r_sample_warning}</span></div>}
              <div className="analysis-grid">
                <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">PAYOFF</span><h3>R-multiple distribution</h3></div></div><RDistribution values={rValues} /></div>
                <RoadmapWidget data={data} />
              </div>
            </>
          )}
          {tab === "strategies" && <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">STRATEGY LAB</span><h3>Observed edge by strategy</h3></div><span className="muted-small">Status needs ≥{MIN_SAMPLE} recorded R</span></div><StrategyTable rows={data.strategies} /></div>}
          {tab === "time" && <TimeAnalysis data={data} />}
          {tab === "behavior" && <BehaviorLeaks data={data} />}
          {tab === "excursions" && <ExcursionPanel data={data} />}
          {tab === "insights" && <div className="analysis-grid"><div className="panel"><div className="subsection-heading"><div><span className="eyebrow">INSIGHT FEED</span><h3>What the data says</h3></div></div><InsightList insights={data.insights} /></div><RoadmapWidget data={data} /></div>}
        </>
      )}
    </section>
  );
}

export function StrategyLab({ data }: { data: PerformanceBundle }) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const keyA = a || data.strategies[0]?.key || "";
  const keyB = b || data.strategies.find((row) => row.key !== keyA)?.key || "";
  const rowA = data.strategies.find((row) => row.key === keyA);
  const rowB = data.strategies.find((row) => row.key === keyB);
  const lines: Array<{ label: string; get: (row: Cohort) => number | null; show: (row: Cohort) => string; lowerIsBetter?: boolean }> = [
    { label: "Win rate", get: (row) => row.win_rate_pct, show: (row) => `${fmt(row.win_rate_pct, 0)}%` },
    { label: "Expectancy", get: (row) => row.expectancy_r, show: (row) => fmtR(row.expectancy_r) },
    { label: "Profit factor", get: (row) => row.profit_factor, show: (row) => fmt(row.profit_factor) },
    { label: "Average win", get: (row) => row.average_win_r, show: (row) => fmtR(row.average_win_r) },
    { label: "Average loss", get: (row) => (row.average_loss_r == null ? null : Math.abs(row.average_loss_r)), show: (row) => fmtR(row.average_loss_r), lowerIsBetter: true },
    { label: "Max drawdown", get: (row) => row.max_drawdown_r, show: (row) => (row.max_drawdown_r == null ? "—" : `${fmt(row.max_drawdown_r)}R`), lowerIsBetter: true },
    { label: "Trades", get: (row) => row.trade_count, show: (row) => String(row.trade_count) },
  ];
  return (
    <div className="content-stack">
      <section className="panel intelligence-workspace"><div className="subsection-heading"><div><span className="eyebrow">LEADERBOARD</span><h3>Strategies ranked by observed expectancy</h3></div><span className="muted-small">Status needs ≥{MIN_SAMPLE} recorded R</span></div><StrategyTable rows={data.strategies} /></section>
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">HEAD TO HEAD</span><h3>Compare two strategies</h3></div></div>
        <div className="compare-pickers">
          <select aria-label="Strategy A" value={keyA} onChange={(event) => setA(event.target.value)}>{data.strategies.map((row) => <option key={row.key}>{row.key}</option>)}</select>
          <span className="vs-pill">VS</span>
          <select aria-label="Strategy B" value={keyB} onChange={(event) => setB(event.target.value)}>{data.strategies.map((row) => <option key={row.key}>{row.key}</option>)}</select>
        </div>
        {rowA && rowB && rowA.key !== rowB.key ? (
          <div className="h2h">
            <div className="h2h-head"><strong className="side-a">{rowA.key}</strong><strong className="side-b">{rowB.key}</strong></div>
            {lines.map((line) => {
              const va = line.get(rowA);
              const vb = line.get(rowB);
              const top = Math.max(0.0001, Math.abs(va ?? 0), Math.abs(vb ?? 0));
              const better = va == null || vb == null || va === vb ? null : (va > vb) !== Boolean(line.lowerIsBetter) ? "a" : "b";
              return (
                <div className="h2h-row" key={line.label}>
                  <div className={`h2h-side a ${better === "a" ? "win" : ""}`}><b>{line.show(rowA)}</b><div><i style={{ width: `${(Math.abs(va ?? 0) / top) * 100}%` }} /></div></div>
                  <span>{line.label}</span>
                  <div className={`h2h-side b ${better === "b" ? "win" : ""}`}><b>{line.show(rowB)}</b><div><i style={{ width: `${(Math.abs(vb ?? 0) / top) * 100}%` }} /></div></div>
                </div>
              );
            })}
            <p className="muted-small">Highlighted side is stronger on that measure. Small samples can flip these results.</p>
          </div>
        ) : <p className="empty-inline">Add at least two strategies to your trades to compare them.</p>}
      </section>
      <div className="analysis-grid">
        <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">CONFLUENCES</span><h3>Expectancy by recorded confluence</h3></div></div><CohortBars rows={data.confluences} label={(key) => key} /></div>
        <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">PLAN ADHERENCE</span><h3>Followed the plan?</h3></div></div><CohortBars rows={data.adherence} label={(key) => key} /></div>
        <p className="muted-small analysis-note">{data.limitation}</p>
      </div>
    </div>
  );
}

type Goal = {
  id: string; title: string; metric: string; direction: string; baseline_value: number | null; baseline_sample: number;
  target_value: number; start_date: string; due_date: string | null; status: string; current_value: number | null;
  current_sample: number; progress: number | null; target_reached: boolean | null; sample_warning: string | null;
};
type Experiment = {
  id: string; goal_id: string | null; title: string; hypothesis: string; rule: string; start_date: string;
  end_date: string | null; min_trades: number; status: string; conclusion: string | null;
  evidence: { trade_count: number; expectancy_r: number | null; win_rate_pct: number | null; profit_factor: number | null; max_drawdown_r: number | null; rule_break_rate_pct: number | null; enough_trades: boolean; caveat: string };
};
const goalMetrics: Record<string, { label: string; direction: string }> = {
  expectancy_r: { label: "Expectancy (R)", direction: "increase" },
  win_rate_pct: { label: "Win rate (%)", direction: "increase" },
  profit_factor: { label: "Profit factor", direction: "increase" },
  max_drawdown_r: { label: "Max drawdown (R)", direction: "decrease" },
  average_loss_r: { label: "Average loss (R)", direction: "increase" },
  rule_break_rate_pct: { label: "Trades with rule breaks (%)", direction: "decrease" },
};

function GoalsAndExperiments() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [error, setError] = useState("");
  const [goalForm, setGoalForm] = useState({ title: "", metric: "expectancy_r", target: "" });
  const [expForm, setExpForm] = useState({ title: "", hypothesis: "", rule: "", goal_id: "", min_trades: "20" });
  const [conclusions, setConclusions] = useState<Record<string, string>>({});

  const reload = useCallback(async () => {
    try {
      const [g, e] = await Promise.all([apiRequest<Goal[]>("/development/goals"), apiRequest<Experiment[]>("/development/experiments")]);
      setGoals(g);
      setExperiments(e);
      setError("");
    } catch {
      setError("Goals and experiments could not be loaded.");
    }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(timer);
  }, [reload]);

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      await reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed");
    }
  }
  function addGoal(event: React.FormEvent) {
    event.preventDefault();
    const target = Number(goalForm.target);
    if (!goalForm.title.trim() || !Number.isFinite(target) || goalForm.target === "") return;
    void run(async () => {
      await apiRequest("/development/goals", { method: "POST", body: JSON.stringify({ title: goalForm.title.trim(), metric: goalForm.metric, direction: goalMetrics[goalForm.metric].direction, target_value: target }) });
      setGoalForm({ title: "", metric: "expectancy_r", target: "" });
    });
  }
  function addExperiment(event: React.FormEvent) {
    event.preventDefault();
    if (!expForm.title.trim() || !expForm.hypothesis.trim() || !expForm.rule.trim()) return;
    void run(async () => {
      await apiRequest("/development/experiments", { method: "POST", body: JSON.stringify({ title: expForm.title.trim(), hypothesis: expForm.hypothesis.trim(), rule: expForm.rule.trim(), goal_id: expForm.goal_id || null, min_trades: Number(expForm.min_trades) || 20, start_date: new Date().toISOString().slice(0, 10) }) });
      setExpForm({ title: "", hypothesis: "", rule: "", goal_id: "", min_trades: "20" });
    });
  }
  const patch = (path: string, body: object) => run(() => apiRequest(path, { method: "PATCH", body: JSON.stringify(body) }));
  const remove = (path: string) => run(() => apiRequest(path, { method: "DELETE" }));

  return (
    <>
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">GOALS</span><h3>What are you working toward?</h3></div></div>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <form className="goal-form" onSubmit={addGoal}>
          <input aria-label="Goal title" placeholder="e.g. Stop taking trades after two losses" value={goalForm.title} onChange={(e) => setGoalForm({ ...goalForm, title: e.target.value })} maxLength={160} />
          <select aria-label="Goal metric" value={goalForm.metric} onChange={(e) => setGoalForm({ ...goalForm, metric: e.target.value })}>{Object.entries(goalMetrics).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}</select>
          <input aria-label="Target value" type="number" step="any" placeholder="Target" value={goalForm.target} onChange={(e) => setGoalForm({ ...goalForm, target: e.target.value })} />
          <button className="primary-button" type="submit">Add goal</button>
        </form>
        {goals.length ? <div className="goal-grid">{goals.map((goal) => (
          <article key={goal.id} className={`goal-card goal-${goal.status}`}>
            <div className="goal-head"><strong>{goal.title}</strong><span className="roadmap-status">{goal.status}</span></div>
            <small>{goalMetrics[goal.metric]?.label} · {goal.direction === "increase" ? "raise to" : "lower to"} {fmt(goal.target_value)}</small>
            <div className="goal-bar" role="progressbar" aria-valuenow={Math.round((goal.progress ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${(goal.progress ?? 0) * 100}%` }} /></div>
            <small>Baseline {goal.baseline_value == null ? "—" : fmt(goal.baseline_value)} ({goal.baseline_sample} trades) → now {goal.current_value == null ? "—" : fmt(goal.current_value)} ({goal.current_sample} trades since start)</small>
            {goal.sample_warning ? <small className="muted-small">{goal.sample_warning}</small> : null}
            <div className="goal-actions">
              {goal.status === "active" ? <><button type="button" onClick={() => void patch(`/development/goals/${goal.id}`, { status: "achieved" })}>Mark achieved</button><button type="button" onClick={() => void patch(`/development/goals/${goal.id}`, { status: "paused" })}>Pause</button></> : <button type="button" onClick={() => void patch(`/development/goals/${goal.id}`, { status: "active" })}>Resume</button>}
              <button type="button" onClick={() => void remove(`/development/goals/${goal.id}`)}>Delete</button>
            </div>
          </article>
        ))}</div> : <p className="empty-inline">No goals yet. Pick one metric you want to move; your starting point is captured from your last 90 days.</p>}
      </section>
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">EXPERIMENTS</span><h3>Test one rule at a time</h3></div></div>
        <form className="goal-form experiment-form" onSubmit={addExperiment}>
          <input aria-label="Experiment title" placeholder="Experiment name" value={expForm.title} onChange={(e) => setExpForm({ ...expForm, title: e.target.value })} maxLength={160} />
          <input aria-label="Hypothesis" placeholder="Hypothesis: what do you expect to change?" value={expForm.hypothesis} onChange={(e) => setExpForm({ ...expForm, hypothesis: e.target.value })} />
          <input aria-label="Rule" placeholder="Rule you will follow" value={expForm.rule} onChange={(e) => setExpForm({ ...expForm, rule: e.target.value })} />
          <select aria-label="Linked goal" value={expForm.goal_id} onChange={(e) => setExpForm({ ...expForm, goal_id: e.target.value })}><option value="">No linked goal</option>{goals.map((goal) => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select>
          <input aria-label="Minimum trades" type="number" min={1} value={expForm.min_trades} onChange={(e) => setExpForm({ ...expForm, min_trades: e.target.value })} />
          <button className="primary-button" type="submit">Start experiment</button>
        </form>
        {experiments.length ? <div className="goal-grid">{experiments.map((item) => (
          <article key={item.id} className="goal-card">
            <div className="goal-head"><strong>{item.title}</strong><span className="roadmap-status">{item.status}</span></div>
            <small>Hypothesis: {item.hypothesis}</small>
            <small>Rule: {item.rule}</small>
            <small>{item.evidence.trade_count}/{item.min_trades} trades · expectancy {fmtR(item.evidence.expectancy_r)} · win rate {item.evidence.win_rate_pct == null ? "—" : `${fmt(item.evidence.win_rate_pct)}%`} · rule breaks {item.evidence.rule_break_rate_pct == null ? "—" : `${fmt(item.evidence.rule_break_rate_pct)}%`}</small>
            <small className="muted-small">{item.evidence.caveat}</small>
            {item.conclusion ? <p>{item.conclusion}</p> : null}
            {item.status === "running" || item.status === "planned" ? (
              <div className="goal-actions">
                <input aria-label="Conclusion" placeholder="What did you learn?" value={conclusions[item.id] ?? ""} onChange={(e) => setConclusions({ ...conclusions, [item.id]: e.target.value })} />
                <button type="button" onClick={() => void patch(`/development/experiments/${item.id}`, { status: "concluded", conclusion: conclusions[item.id] || null, end_date: new Date().toISOString().slice(0, 10) })}>Conclude</button>
                <button type="button" onClick={() => void patch(`/development/experiments/${item.id}`, { status: "abandoned" })}>Abandon</button>
              </div>
            ) : null}
            <div className="goal-actions"><button type="button" onClick={() => void remove(`/development/experiments/${item.id}`)}>Delete</button></div>
          </article>
        ))}</div> : <p className="empty-inline">No experiments yet. Change one rule, log enough trades, then review the evidence honestly.</p>}
      </section>
    </>
  );
}

export function DevelopmentRoadmap({ data }: { data: PerformanceBundle }) {
  const [history, setHistory] = useState<Array<Roadmap & { id: string; generated_at: string; trade_count: number }>>([]);
  const savedId = data.roadmap?.id;
  const savedStatus = data.roadmap?.progress_status;
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const rows = await apiRequest<Array<Roadmap & { id: string; generated_at: string; trade_count: number }>>("/performance/roadmaps?limit=20");
        if (!cancelled) setHistory(rows);
      } catch {
        if (!cancelled) setHistory([]);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [savedId, savedStatus]);
  return (
    <div className="content-stack">
      <section className="panel intelligence-workspace"><RoadmapWidget data={data} /></section>
      <GoalsAndExperiments />
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">PROGRESS OVER TIME</span><h3>Saved roadmaps</h3></div></div>
        {history.length ? <div className="roadmap-history">{history.map((item) => (
          <article key={item.id}>
            <div><strong>{new Date(item.generated_at).toLocaleDateString()}</strong><small>{item.trade_count} trades at the time</small></div>
            <ul>{item.recommendations.slice(0, 3).map((rec) => <li key={rec.focus}>{rec.focus}</li>)}</ul>
            <span className="roadmap-status">{item.progress_status.replace("_", " ")}</span>
          </article>
        ))}</div> : <p className="empty-inline">Save your first roadmap to start tracking whether your focus areas are moving.</p>}
      </section>
    </div>
  );
}

type EquitySeries = {
  account_id: string; account_name: string; currency: string; snapshot_count: number; max_drawdown_pct: number; current_drawdown_pct: number;
  points: Array<{ observed_at: string; balance: number; equity: number; drawdown_pct: number }>;
};
type RiskStatus = {
  account_id: string; account_name: string; closed_trades_today: number; trade_count_today: number; realized_pnl_today: number;
  risk_profile_configured: boolean; violations: Array<{ rule: string; threshold: number; actual: number }>;
};
type RiskProfileRow = { account_id: string | null; max_daily_loss: number | null; max_risk_per_trade: number | null; max_trades_per_day: number | null };

function RiskControls({ accountId }: { accountId: string | null }) {
  const [equity, setEquity] = useState<EquitySeries[]>([]);
  const [status, setStatus] = useState<RiskStatus[]>([]);
  const [profiles, setProfiles] = useState<RiskProfileRow[]>([]);
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, { daily: string; risk: string; trades: string }>>({});
  const [saving, setSaving] = useState("");

  const load = useCallback(async () => {
    try {
      const query = accountId ? `?account_id=${accountId}` : "";
      const [history, st, pr] = await Promise.all([
        apiRequest<{ series: EquitySeries[] }>(`/performance/equity-history${query}`),
        apiRequest<RiskStatus[]>("/risk/status"),
        apiRequest<RiskProfileRow[]>("/risk/profiles"),
      ]);
      setEquity(history.series);
      setStatus(accountId ? st.filter((item) => item.account_id === accountId) : st);
      setProfiles(pr);
      setError("");
    } catch {
      setError("Account risk data could not be loaded.");
    }
  }, [accountId]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function save(id: string) {
    const draft = drafts[id];
    const body = {
      max_daily_loss: draft.daily ? Number(draft.daily) : null,
      max_risk_per_trade: draft.risk ? Number(draft.risk) : null,
      max_trades_per_day: draft.trades ? Number(draft.trades) : null,
    };
    setSaving(id);
    try {
      await apiRequest(`/accounts/${id}/risk-profile`, { method: "PUT", body: JSON.stringify(body) });
      setDrafts((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== id)));
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save limits");
    } finally {
      setSaving("");
    }
  }

  return (
    <>
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">ACCOUNT EQUITY</span><h3>Drawdown from equity peak</h3></div></div>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {equity.length ? equity.map((series) => {
          const worst = Math.min(0, ...series.points.map((point) => point.drawdown_pct));
          const width = 600;
          const height = 140;
          const path = series.points.length > 1 ? series.points.map((point, index) => `${index ? "L" : "M"}${(index / (series.points.length - 1)) * width},${worst === 0 ? 0 : (point.drawdown_pct / worst) * height}`).join(" ") : "";
          return (
            <div key={series.account_id} className="equity-series">
              <div className="subsection-heading"><strong>{series.account_name} ({series.currency})</strong><span className="muted-small">{series.snapshot_count} terminal snapshots · max {fmt(series.max_drawdown_pct)}% · now {fmt(series.current_drawdown_pct)}%</span></div>
              {path ? <svg className="underwater" viewBox={`0 -4 ${width} ${height + 8}`} preserveAspectRatio="none" role="img" aria-label={`Equity drawdown for ${series.account_name}`}><path d={`${path} L${width},0 L0,0 Z`} className="underwater-fill" /><path d={path} className="underwater-line" /></svg> : <p className="empty-inline">More snapshots are needed to draw this curve.</p>}
            </div>
          );
        }) : <p className="empty-inline">No equity snapshots yet. Once a connected terminal reports balance and equity, the true account drawdown appears here; until then the R-based curve below is used.</p>}
        <p className="muted-small">Accounts are never merged, because their currencies and balances aren’t comparable.</p>
      </section>
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">RULE MONITOR</span><h3>Today against your limits</h3></div></div>
        {status.length ? <div className="goal-grid">{status.map((item) => {
          const profile = profiles.find((row) => row.account_id === item.account_id);
          const draft = drafts[item.account_id] ?? { daily: profile?.max_daily_loss?.toString() ?? "", risk: profile?.max_risk_per_trade?.toString() ?? "", trades: profile?.max_trades_per_day?.toString() ?? "" };
          const set = (patch: Partial<typeof draft>) => setDrafts({ ...drafts, [item.account_id]: { ...draft, ...patch } });
          return (
            <article key={item.account_id} className="goal-card">
              <div className="goal-head"><strong>{item.account_name}</strong><span className={`roadmap-status ${item.violations.length ? "negative" : ""}`}>{item.risk_profile_configured ? (item.violations.length ? `${item.violations.length} breached` : "Within limits") : "No limits set"}</span></div>
              <small>{item.trade_count_today} trades today · realised {fmt(item.realized_pnl_today)} (account currency)</small>
              {item.violations.map((violation) => <small key={violation.rule} className="negative">{violation.rule.replaceAll("_", " ")}: {fmt(violation.actual)} vs limit {fmt(violation.threshold)}</small>)}
              <div className="risk-limit-form">
                <label>Max daily loss<input type="number" min={0} step="any" value={draft.daily} onChange={(e) => set({ daily: e.target.value })} /></label>
                <label>Max risk per trade (%)<input type="number" min={0} max={100} step="any" value={draft.risk} onChange={(e) => set({ risk: e.target.value })} /></label>
                <label>Max trades per day<input type="number" min={1} step={1} value={draft.trades} onChange={(e) => set({ trades: e.target.value })} /></label>
              </div>
              <div className="goal-actions"><button type="button" disabled={saving === item.account_id || !drafts[item.account_id]} onClick={() => void save(item.account_id)}>{saving === item.account_id ? "Saving…" : "Save limits"}</button></div>
            </article>
          );
        })}</div> : <p className="empty-inline">Connect an account to monitor daily limits. These limits are your own rules; they are recorded and flagged, not enforced on the terminal.</p>}
      </section>
    </>
  );
}

export function RiskIntelligence({ data, rValues, accountId = null }: { data: PerformanceBundle; rValues: number[]; accountId?: string | null }) {
  const metrics = data.metrics;
  const curve = rValues.reduce<Array<{ equity: number; peak: number; drawdown: number }>>((points, value) => {
    const equity = (points.at(-1)?.equity ?? 0) + value;
    const peak = Math.max(points.at(-1)?.peak ?? 0, equity);
    return [...points, { equity, peak, drawdown: equity - peak }];
  }, []);
  const worst = Math.min(0, ...curve.map((point) => point.drawdown));
  const width = 600;
  const height = 160;
  const path = curve.length > 1
    ? curve.map((point, index) => `${index ? "L" : "M"}${(index / (curve.length - 1)) * width},${worst === 0 ? 0 : (point.drawdown / worst) * height}`).join(" ")
    : "";
  const current = curve.length ? curve[curve.length - 1].drawdown : null;
  return (
    <div className="content-stack">
      <section className="panel intelligence-workspace intelligence-metrics">
        <div><span>Max drawdown</span><strong>{fmt(metrics?.max_drawdown_r)}R</strong><small>from recorded R</small></div>
        <div><span>Current drawdown</span><strong>{current == null ? "—" : `${fmt(current)}R`}</strong><small>from the latest equity peak</small></div>
        <div><span>Recovery</span><strong>{duration(metrics?.max_drawdown_recovery_seconds ?? null)}</strong><small>worst drawdown</small></div>
        <div><span>Average loss</span><strong>{fmtR(metrics?.average_loss_r)}</strong><small>risk consistency</small></div>
      </section>
      <RiskControls accountId={accountId} />
      <section className="panel intelligence-workspace">
        <div className="subsection-heading"><div><span className="eyebrow">UNDERWATER</span><h3>Drawdown from peak (R)</h3></div><span className="muted-small">{rValues.length} trades with recorded R</span></div>
        {path ? <svg className="underwater" viewBox={`0 -4 ${width} ${height + 8}`} preserveAspectRatio="none" role="img" aria-label="Underwater drawdown curve"><path d={`${path} L${width},0 L0,0 Z`} className="underwater-fill" /><path d={path} className="underwater-line" /></svg> : <p className="empty-inline">Record R-multiples on at least two closed trades to draw your drawdown curve.</p>}
      </section>
      <div className="analysis-grid">
        <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">RULE MONITOR</span><h3>Recorded rule breaks</h3></div></div><CohortBars rows={data.ruleBreaks} label={(key) => key} /></div>
        <div className="panel"><div className="subsection-heading"><div><span className="eyebrow">TIMING</span><h3>Trades soon after a loss</h3></div></div>{data.revenge && data.revenge.trade_count > 0 ? <div className="leak-compare"><div><span>Within {data.revenge.window_minutes} min</span><strong>{fmtR(data.revenge.metrics.expectancy_r)}</strong><small>{data.revenge.trade_count} trades</small></div><div><span>Other trades</span><strong>{fmtR(data.revenge.comparison_without_flag.expectancy_r)}</strong><small>{data.revenge.comparison_without_flag.trade_count} trades</small></div></div> : <p className="empty-inline">No trades opened shortly after a loss in this range.</p>}</div>
        <p className="muted-small analysis-note">The R curve is computed from your recorded R-multiples; account equity drawdown comes from terminal snapshots. Limits are your own rules and are flagged, not enforced.</p>
      </div>
    </div>
  );
}

type ReportMetrics = Record<string, number | null | string>;
type ReportEvidence = {
  trade_id: string;
  symbol: string;
  setup: string | null;
  source: string;
  outcome: string;
  closed_at: string;
};
type ReportStrategy = Cohort & { evidence: ReportEvidence[] };
type Report = {
  generated_at: string;
  scope: { timezone: string; current_period: { start_date: string; end_date: string }; previous_period: { start_date: string; end_date: string } };
  comparison: Array<{ metric: string; current: number | null; previous: number | null; change: number | null }>;
  current: ReportMetrics;
  identity: {
    dominant_strategy: { name: string; trade_count: number; share_pct: number } | null;
    strongest_observed_strategy: { name: string; expectancy_r: number; r_sample_count: number } | null;
    interpretation: string;
  };
  strategies: ReportStrategy[];
  limitations: string[];
};

const REPORT_LABELS: Record<string, string> = {
  trade_count: "Closed trades",
  win_rate_pct: "Win rate (%)",
  expectancy_r: "Expectancy (R)",
  profit_factor: "Profit factor",
  net_pnl: "Net P&L",
  average_win_r: "Average win (R)",
  average_loss_r: "Average loss (R)",
  max_drawdown_r: "Max drawdown (R)",
};

const PERIODS: Array<[string, string, number]> = [["7", "Last 7 days", 7], ["30", "Last 30 days", 30], ["90", "Last 90 days", 90]];

function isoDay(date: Date) {
  return date.toISOString().slice(0, 10);
}

function download(name: string, type: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function ReportsPage({ accountId, timezone, onOpenTrade }: { accountId: string | null; timezone: string; onOpenTrade: (tradeId: string) => void }) {
  const [period, setPeriod] = useState("30");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      const days = PERIODS.find(([id]) => id === period)?.[2] ?? 30;
      const end = new Date();
      const start = new Date(end.getTime() - (days - 1) * 86400000);
      const params = new URLSearchParams({ start_date: isoDay(start), end_date: isoDay(end), timezone: timezone === "local" ? "UTC" : timezone });
      if (accountId) params.set("account_id", accountId);
      try {
        const next = await apiRequest<Report>(`/performance/report?${params.toString()}`);
        if (!cancelled) setReport(next);
      } catch (cause: unknown) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not build this report.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [accountId, period, timezone]);

  function exportCsv() {
    if (!report) return;
    const rows = [["metric", "current", "previous", "change"], ...report.comparison.map((row) => [REPORT_LABELS[row.metric] ?? row.metric, row.current ?? "", row.previous ?? "", row.change ?? ""])];
    rows.push([], ["strategy", "trades", "win_rate_pct", "expectancy_r", "profit_factor"]);
    report.strategies.forEach((row) => rows.push([row.key, row.trade_count, row.win_rate_pct ?? "", row.expectancy_r ?? "", row.profit_factor ?? ""]));
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
    download(`tradeiq-report-${report.scope.current_period.end_date}.csv`, "text/csv", csv);
  }

  const cell = (metric: string, value: number | null) => (value == null ? "—" : metric === "trade_count" ? String(value) : fmt(value, metric === "net_pnl" ? 2 : 2));
  return (
    <div className="content-stack">
      <section className="panel intelligence-workspace">
        <div className="subsection-heading">
          <div><span className="eyebrow">PERIOD REPORT</span><h3>{report ? `${report.scope.current_period.start_date} → ${report.scope.current_period.end_date}` : "Choose a period"}</h3></div>
          <div className="report-actions">
            <select aria-label="Report period" value={period} onChange={(event) => setPeriod(event.target.value)}>{PERIODS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
            <button className="button button-outline" disabled={!report} onClick={exportCsv}>Download CSV</button>
            <button className="button button-outline" disabled={!report} onClick={() => report && download(`tradeiq-report-${report.scope.current_period.end_date}.json`, "application/json", JSON.stringify(report, null, 2))}>Download JSON</button>
            <button className="button button-outline" onClick={() => window.print()}>Print</button>
          </div>
        </div>
        {loading ? <div className="intelligence-loading" /> : error ? <p className="form-error" role="alert">{error}</p> : report && (
          <>
            <div className="table-wrap">
              <table className="intel-table">
                <thead><tr><th>Metric</th><th>This period</th><th>Previous ({report.scope.previous_period.start_date} → {report.scope.previous_period.end_date})</th><th>Change</th></tr></thead>
                <tbody>{report.comparison.map((row) => <tr key={row.metric}><td>{REPORT_LABELS[row.metric] ?? row.metric}</td><td><strong>{cell(row.metric, row.current)}</strong></td><td>{cell(row.metric, row.previous)}</td><td className={(row.change ?? 0) > 0 ? "positive" : (row.change ?? 0) < 0 ? "negative" : ""}>{row.change == null ? "—" : `${row.change > 0 ? "+" : ""}${row.change.toFixed(2)}`}</td></tr>)}</tbody>
              </table>
            </div>
            <p className="muted-small analysis-note">Generated {new Date(report.generated_at).toLocaleString()} · {report.scope.timezone}. {report.limitations.join(" ")}</p>
          </>
        )}
      </section>
      {report && !loading && <section className="panel intelligence-workspace"><div className="subsection-heading"><div><span className="eyebrow">THIS PERIOD</span><h3>Strategies</h3></div></div><StrategyTable rows={report.strategies} /></section>}
      {report && !loading && (
        <>
          <section className="panel intelligence-workspace">
            <div className="subsection-heading"><div><span className="eyebrow">EDGE TRADER DNA</span><h3>Observed trading identity</h3></div><span className="muted-small">{String(report.current.trade_count ?? 0)} closed trades</span></div>
            <div className="dna-summary-grid">
              <div><span>Most recorded strategy</span><strong>{report.identity.dominant_strategy?.name ?? "Not recorded"}</strong><small>{report.identity.dominant_strategy ? `${report.identity.dominant_strategy.trade_count} trades · ${fmt(report.identity.dominant_strategy.share_pct, 0)}% of this period` : "Add strategy labels to identify your trading mix."}</small></div>
              <div><span>Strongest observed expectancy</span><strong>{report.identity.strongest_observed_strategy?.name ?? "Building sample"}</strong><small>{report.identity.strongest_observed_strategy ? `${fmtR(report.identity.strongest_observed_strategy.expectancy_r)} · ${report.identity.strongest_observed_strategy.r_sample_count} recorded R trades` : "A setup is highlighted only after 30 recorded R trades."}</small></div>
            </div>
            <p className="muted-small analysis-note">{report.identity.interpretation}</p>
          </section>
          <section className="panel intelligence-workspace">
            <div className="subsection-heading"><div><span className="eyebrow">REPORT EVIDENCE</span><h3>Source trades</h3></div></div>
            {report.strategies.length ? <div className="report-evidence-groups">{report.strategies.map((strategy) => (
              <details className="report-evidence-group" key={strategy.key}>
                <summary><strong>{strategy.key}</strong><span>{strategy.evidence.length} trades</span></summary>
                <ul className="report-evidence-list">{strategy.evidence.map((trade) => (
                  <li key={trade.trade_id}>
                    <span><strong>{trade.symbol}</strong><small>{trade.setup ?? "Setup not recorded"} · {trade.outcome} · {trade.source === "mt5" ? "MT5 record" : "Journal record"} · {new Date(trade.closed_at).toLocaleDateString()}</small></span>
                    <button className="text-link" onClick={() => onOpenTrade(trade.trade_id)}>Open review</button>
                  </li>
                ))}</ul>
              </details>
            ))}</div> : <p className="empty-inline">No closed trades are eligible in this period.</p>}
          </section>
        </>
      )}
    </div>
  );
}
