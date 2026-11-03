"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import "./agent.css";

type Range = { preset: string; startDate: string; endDate: string };
type Insight = {
  id: string; code: string; category: string; severity: "info" | "low" | "medium" | "high" | "critical";
  confidence: "low" | "medium" | "high" | "insufficient"; sample_size: number; effect_size: number | null;
  q_value: number | null; est_dollar_impact: number | null; title: string; body: string;
  recommended_action: string | null; holds_out_of_time: boolean | null; status: string; feedback: string | null;
  evidence: { cohort_n?: number; rest_n?: number; cohort_mean_r?: number; rest_mean_r?: number; difference_ci_95?: [number, number]; trade_ids?: string[] };
};
type Core = {
  trade_count: number; r_sample_count: number; win_rate_pct: number | null; win_rate_ci_pct: [number, number] | null;
  expectancy_r: number | null; expectancy_ci: [number, number] | null; profit_factor: number | null; sqn: number | null;
  sqn_label: string | null; max_drawdown_r: number | null; currency: string | null; confidence: string;
};
type Process = {
  total: number | null; trend: number | null; note: string;
  components: Record<"plan_adherence" | "risk_compliance" | "journaling" | "rule_compliance", number | null>;
  weekly: Array<{ week_start: string; trades: number; total: number | null }>;
};
type AgentRun = {
  readiness: { closed_trades: number; r_trades: number; reviewed_trades: number; minimum_trades: number; ready: boolean; tips: string[] };
  core: Core; process: Process; insights: Insight[]; limitations: string[];
};

const COMPONENTS: Array<[keyof Process["components"], string, string]> = [
  ["plan_adherence", "Plan adherence", "Reviews where you followed the plan"],
  ["risk_compliance", "Risk discipline", "A recorded stop and losses within 1.1R"],
  ["journaling", "Journaling", "Review, setup, emotion and notes filled in"],
  ["rule_compliance", "Rule compliance", "Trades without a recorded rule break"],
];
const FEEDBACK: Array<[string, string]> = [["useful", "Useful"], ["already_knew", "Already knew"], ["not_useful", "Not useful"], ["wrong", "Wrong"]];
const STEPS = [
  ["Diagnose", "Statistical rules look for leaks in your own trades: plan adherence, revenge timing, hours, overtrading, sizing, drift and rule breaks."],
  ["Hypothesize", "Each finding comes with a specific rule to test, not a vague warning."],
  ["Test", "Start an experiment from the finding. It tracks your trades against that rule."],
  ["Evaluate", "Findings are re-checked on every run; they resolve when the leak disappears."],
  ["Lock in", "Keep rules that work, retire the ones that do not, and watch your process score."],
];

const r2 = (value: number | null | undefined) => (value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}R`);
const pct = (value: number | null | undefined) => (value == null ? "—" : `${value.toFixed(0)}%`);
const money = (value: number) => `${value < 0 ? "-" : ""}${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function query(accountId: string | null, range: Range, timezone: string) {
  const params = new URLSearchParams({ timezone: timezone === "local" ? "UTC" : timezone });
  if (accountId) params.set("account_id", accountId);
  if (range.startDate) params.set("start_date", range.startDate);
  if (range.endDate) params.set("end_date", range.endDate);
  return params.toString();
}

function InsightCard({ insight, currency, onChange, onError }: { insight: Insight; currency: string | null; onChange: () => void; onError: (message: string) => void }) {
  const evidence = insight.evidence;
  async function patch(body: { status?: string; feedback?: string }) {
    try {
      await apiRequest(`/agent/insights/${insight.id}`, { method: "PATCH", body: JSON.stringify(body) });
      onChange();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not update this insight.");
    }
  }
  async function startExperiment() {
    try {
      await apiRequest("/development/experiments", {
        method: "POST",
        body: JSON.stringify({
          title: insight.title.slice(0, 160),
          hypothesis: `Acting on this finding improves my results: ${insight.body}`,
          rule: insight.recommended_action ?? insight.title,
          goal_id: null,
          min_trades: 20,
          start_date: new Date().toISOString().slice(0, 10),
        }),
      });
      await patch({ status: "experiment_running" });
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not start the experiment.");
    }
  }
  return (
    <article className={`ta-insight ta-${insight.severity}`}>
      <div className="ta-insight-head">
        <strong>{insight.title}</strong>
        <span className="roadmap-status">{insight.severity}</span>
      </div>
      <p>{insight.body}</p>
      <div className="ta-badges">
        <span>{insight.confidence} confidence · {insight.sample_size} trades</span>
        {insight.holds_out_of_time === true && <span className="ta-ok">Holds in later trades</span>}
        {insight.holds_out_of_time === false && <span className="ta-warn">Not yet replicated</span>}
        {insight.est_dollar_impact != null && <span>Est. cost {money(insight.est_dollar_impact)} {currency ?? ""}</span>}
        {insight.q_value != null && <span>q = {insight.q_value.toFixed(3)}</span>}
      </div>
      {evidence.cohort_mean_r != null && evidence.rest_mean_r != null && (
        <small className="muted-small">
          Evidence: {r2(evidence.cohort_mean_r)} ({evidence.cohort_n} trades) vs {r2(evidence.rest_mean_r)} ({evidence.rest_n} trades)
          {evidence.difference_ci_95 ? `; 95% interval of the gap ${r2(evidence.difference_ci_95[0])} to ${r2(evidence.difference_ci_95[1])}` : ""}.
        </small>
      )}
      {insight.recommended_action && <div className="ta-action"><span>Try</span>{insight.recommended_action}</div>}
      <div className="goal-actions">
        {insight.status !== "experiment_running" && <button type="button" onClick={() => void startExperiment()}>Test this rule</button>}
        {insight.status === "new" && <button type="button" onClick={() => void patch({ status: "seen" })}>Mark seen</button>}
        {insight.status !== "accepted" && insight.status !== "experiment_running" && <button type="button" onClick={() => void patch({ status: "accepted" })}>Accept</button>}
        {insight.status !== "dismissed" ? <button type="button" onClick={() => void patch({ status: "dismissed" })}>Dismiss</button> : <button type="button" onClick={() => void patch({ status: "seen" })}>Restore</button>}
        <span className="muted-small ta-status">{insight.status.replace("_", " ")}</span>
      </div>
      <div className="ta-feedback" aria-label="Was this useful?">
        {FEEDBACK.map(([value, label]) => <button key={value} type="button" className={insight.feedback === value ? "chosen" : ""} onClick={() => void patch({ feedback: value })}>{label}</button>)}
      </div>
    </article>
  );
}

export function AgentPage({ accountId, dateRange, timezone }: { accountId: string | null; dateRange: Range; timezone: string }) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [showDismissed, setShowDismissed] = useState(false);
  const [guide, setGuide] = useState(false);
  const qs = query(accountId, dateRange, timezone);

  const load = useCallback(async () => {
    try {
      setRun(await apiRequest<AgentRun>(`/agent/run?${qs}`, { method: "POST" }));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The agent could not analyze your trades.");
    } finally {
      setLoading(false);
    }
  }, [qs]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (loading) return <div className="panel"><div className="intelligence-loading" /></div>;
  if (!run) return <p className="form-error" role="alert">{error}</p>;

  const { readiness, core, process } = run;
  const open = run.insights.filter((item) => !["dismissed", "resolved"].includes(item.status));
  const dismissed = run.insights.filter((item) => item.status === "dismissed");
  const priorities = open.slice(0, 3);
  const progress = Math.min(100, (readiness.closed_trades / readiness.minimum_trades) * 100);

  return (
    <div className="content-stack">
      {error && <p className="form-error" role="alert">{error}</p>}
      <section className="panel ta-hero">
        <div className="subsection-heading">
          <div><span className="eyebrow">TRADEIQ AGENT</span><h3>{readiness.ready ? "Your agent has enough data to find patterns" : "Your agent is building your baseline"}</h3></div>
          <span className="muted-small">{readiness.closed_trades} / {readiness.minimum_trades} closed trades</span>
        </div>
        <div className="goal-bar" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div>
        {readiness.tips.length > 0 && <ul className="ta-tips">{readiness.tips.map((tip) => <li key={tip}>{tip}</li>)}</ul>}
      </section>

      <section className="intelligence-metrics panel ta-metrics">
        <div><span>Expectancy</span><strong className={(core.expectancy_r ?? 0) >= 0 ? "positive" : "negative"}>{r2(core.expectancy_r)}</strong><small>{core.expectancy_ci ? `95% range ${r2(core.expectancy_ci[0])} to ${r2(core.expectancy_ci[1])}` : `${core.r_sample_count} trades with R`}</small></div>
        <div><span>Win rate</span><strong>{pct(core.win_rate_pct)}</strong><small>{core.win_rate_ci_pct ? `95% range ${pct(core.win_rate_ci_pct[0])} to ${pct(core.win_rate_ci_pct[1])}` : "—"}</small></div>
        <div><span>System quality (SQN)</span><strong>{core.sqn == null ? "—" : core.sqn.toFixed(2)}</strong><small>{core.sqn_label ?? "Needs 20+ trades with R"}</small></div>
        <div><span>Profit factor</span><strong>{core.profit_factor == null ? "—" : core.profit_factor.toFixed(2)}</strong><small>{core.currency ?? "Mixed currencies"}</small></div>
        <div><span>Max drawdown</span><strong>{core.max_drawdown_r == null ? "—" : `${core.max_drawdown_r.toFixed(2)}R`}</strong><small>Cumulative R</small></div>
        <div><span>Confidence</span><strong style={{ textTransform: "capitalize" }}>{core.confidence}</strong><small>From R sample size</small></div>
      </section>

      <div className="analysis-grid ta-duo">
        <section className="panel ta-process">
          <div className="subsection-heading"><div><span className="eyebrow">PROCESS SCORE</span><h3>How well you follow your process</h3></div>
            <div className="ta-score"><div className="ta-ring" style={{ "--score": `${process.total ?? 0}%` } as React.CSSProperties}><strong>{process.total == null ? "—" : Math.round(process.total)}</strong></div>{process.trend != null && <small className={process.trend >= 0 ? "positive" : "negative"}>{process.trend >= 0 ? "▲" : "▼"} {Math.abs(process.trend).toFixed(0)} vs last week</small>}</div>
          </div>
          <div className="ta-components">
            {COMPONENTS.map(([key, label, hint]) => (
              <div key={key}><div><b>{label}</b><small>{hint}</small></div><span>{pct(process.components[key])}</span><div className="goal-bar"><span style={{ width: `${process.components[key] ?? 0}%` }} /></div></div>
            ))}
          </div>
          {process.weekly.length > 0 && <div className="ta-weekly" aria-label="Weekly process score">{process.weekly.map((week) => <div key={week.week_start} title={`${week.week_start}: ${week.total == null ? "n/a" : Math.round(week.total)} (${week.trades} trades)`}><span style={{ height: `${week.total ?? 0}%` }} /><small>{week.week_start.slice(5)}</small></div>)}</div>}
          <p className="muted-small">{process.note}</p>
        </section>

        <section className="panel ta-priority-panel">
          <div className="subsection-heading"><div><span className="eyebrow">TOP PRIORITIES</span><h3>Fix these first</h3></div></div>
          {priorities.length ? <ol className="ta-priorities">{priorities.map((item) => <li key={item.id}><b>{item.title}</b><small>{item.recommended_action}</small></li>)}</ol>
            : <p className="empty-inline">{readiness.ready ? "No statistically supported leak right now. Keep logging; the agent re-checks on every run." : "Findings appear once there are enough trades with recorded R. Nothing is guessed from small samples."}</p>}
          <button type="button" className="button button-outline" onClick={() => setGuide((value) => !value)}>{guide ? "Hide" : "How the agent works"}</button>
          {guide && <ol className="ta-steps">{STEPS.map(([title, text]) => <li key={title}><b>{title}</b><span>{text}</span></li>)}</ol>}
        </section>
      </div>

      <section className="panel ta-findings">
        <div className="subsection-heading"><div><span className="eyebrow">FINDINGS</span><h3>What the agent found in your trades</h3></div>{dismissed.length > 0 && <button type="button" className="button button-outline" onClick={() => setShowDismissed((value) => !value)}>{showDismissed ? "Hide" : "Show"} dismissed ({dismissed.length})</button>}</div>
        {open.length ? <div className="ta-insights">{open.map((item) => <InsightCard key={item.id} insight={item} currency={core.currency} onChange={() => void load()} onError={setError} />)}</div> : <p className="empty-inline">No active findings.</p>}
        {showDismissed && <div className="ta-insights">{dismissed.map((item) => <InsightCard key={item.id} insight={item} currency={core.currency} onChange={() => void load()} onError={setError} />)}</div>}
      </section>
      <p className="muted-small analysis-note">{run.limitations.join(" ")}</p>
    </div>
  );
}
