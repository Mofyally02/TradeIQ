# ruff: noqa: E501
"""Rule-based Trading Agent: statistically guarded diagnostics over one user's own closed trades.

No external model or shared data is used; every finding carries its sample size, effect size,
confidence interval-based gating and a Benjamini-Hochberg corrected q-value.
"""

import hashlib
import math
import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import mean, median, pstdev
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.platform_models import AgentInsight, Trade, TradeReview
from app.services.performance import (
    _as_utc,
    currency_map,
    detect_revenge_trades,
    get_closed_trades,
    get_recent_loss_trades,
    load_reviews,
    metrics_for,
    trade_currency,
)

CALC_VERSION = "agent-1"
MIN_COHORT = 20
MIN_REST = 10
MIN_TIME_BUCKET = 25
BOOTSTRAP_ROUNDS = 1000
Q_THRESHOLD = 0.2
LOSS_OVERRUN_R = -1.1
CONFIDENCE_WEIGHT = {"low": 0.4, "medium": 0.7, "high": 1.0}
NEGATIVE_EMOTIONS = {"anxious", "fearful", "frustrated", "revenge", "fomo", "excited"}


# ---------------------------------------------------------------- statistics
def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def bootstrap_mean_ci(values: list[float], seed: int = 11) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(mean(rng.choices(values, k=n)) for _ in range(BOOTSTRAP_ROUNDS))
    return means[int(0.025 * BOOTSTRAP_ROUNDS)], means[int(0.975 * BOOTSTRAP_ROUNDS) - 1]


def bootstrap_diff_ci(a: list[float], b: list[float], seed: int = 13) -> tuple[float, float]:
    rng = random.Random(seed)
    diffs = sorted(
        mean(rng.choices(a, k=len(a))) - mean(rng.choices(b, k=len(b)))
        for _ in range(BOOTSTRAP_ROUNDS)
    )
    return diffs[int(0.025 * BOOTSTRAP_ROUNDS)], diffs[int(0.975 * BOOTSTRAP_ROUNDS) - 1]


def welch_p_value(a: list[float], b: list[float]) -> float:
    """Two-sided p-value from Welch's statistic with a normal approximation."""
    se = math.sqrt(_var(a) / len(a) + _var(b) / len(b))
    if se == 0:
        return 1.0
    return math.erfc(abs(mean(a) - mean(b)) / se / math.sqrt(2))


def _var(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    return sum((v - centre) ** 2 for v in values) / (len(values) - 1)


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = sorted(range(count), key=lambda i: p_values[i])
    adjusted = [1.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        running = min(running, p_values[index] * count / rank)
        adjusted[index] = running
    return adjusted


def confidence_tier(sample: int) -> str:
    if sample < MIN_COHORT:
        return "insufficient"
    if sample < 30:
        return "low"
    return "medium" if sample < 60 else "high"


def sqn_label(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1.6:
        return "Poor / hard to trade"
    if value < 2.0:
        return "Below average"
    if value < 2.5:
        return "Average"
    if value < 3.0:
        return "Good"
    return "Excellent"


# ------------------------------------------------------------------ helpers
def _r(trade: Trade) -> float | None:
    return float(trade.r_multiple) if trade.r_multiple is not None else None


def _pnl(trade: Trade) -> float:
    return float(trade.pnl or 0)


def _fmt_r(value: float) -> str:
    return f"{value:+.2f}R"


@dataclass
class Candidate:
    code: str
    category: str
    scope: str
    cohort: list[Trade]
    rest: list[Trade]
    params: dict[str, Any] = field(default_factory=dict)
    # Filled by evaluate():
    cohort_r: list[float] = field(default_factory=list)
    rest_r: list[float] = field(default_factory=list)
    diff: float = 0.0
    ci: tuple[float, float] = (0.0, 0.0)
    p_value: float = 1.0
    q_value: float = 1.0


TEMPLATES: dict[str, tuple[str, str, str]] = {
    "PLAN_NONADHERENCE": (
        "Off-plan trades are costing you",
        "Trades you reviewed as off-plan average {r_cohort} versus {r_rest} when you followed the plan "
        "({n} off-plan trades).",
        "Do not enter without a written plan for your next 20 trades.",
    ),
    "REVENGE_TRADING": (
        "Trades right after a loss are hurting you",
        "Trades opened within {window} minutes of a loss average {r_cohort} versus {r_rest} otherwise "
        "({n} trades).",
        "After a loss, take a mandatory {window}-minute break for your next 20 trades.",
    ),
    "TIME_OF_DAY_LEAK": (
        "Trading at {label} is costing you",
        "Trades opened around {label} average {r_cohort} versus {r_rest} at other times ({n} trades).",
        "Test a no-new-entries rule around {label} for 20 trades.",
    ),
    "OVERTRADING": (
        "Later trades of the day perform worse",
        "Trade number {k} or later in a day averages {r_cohort} versus {r_rest} for earlier trades "
        "({n} trades).",
        "Cap yourself at {cap} trades per day for the next 20 sessions.",
    ),
    "TILT_SIZING": (
        "You size up after losses",
        "Trades that follow a loss with position size above 1.25x your median average {r_cohort} "
        "versus {r_rest} otherwise ({n} trades).",
        "Fix position size to a constant risk percentage for 20 trades.",
    ),
    "SETUP_DRIFT": (
        "{label} is underperforming its own history",
        "{label}: your last {n} trades average {r_cohort} versus {r_rest} before that.",
        "Reduce size on {label} until it recovers, or review its entry criteria.",
    ),
    "RULE_BREAK_COST": (
        "Breaking \"{label}\" is costing you",
        "Trades tagged \"{label}\" average {r_cohort} versus {r_rest} without it ({n} trades).",
        "Make \"{label}\" a hard rule for your next 20 trades and tag every breach.",
    ),
    "EMOTION_LEAK": (
        "Trading while \"{label}\" is costing you",
        "Trades recorded as \"{label}\" average {r_cohort} versus {r_rest} otherwise ({n} trades).",
        "When you notice \"{label}\", skip the next setup and journal instead.",
    ),
    "CUTTING_WINNERS": (
        "You are leaving profit on the table",
        "On {n} winning trades you captured {capture:.0%} of the available move "
        "(average win {avg_win} versus average MFE {avg_mfe}).",
        "Test scaling out at 1R and trailing the remainder for 20 trades.",
    ),
    "LETTING_LOSERS_RUN": (
        "Your losses exceed your planned risk",
        "{share:.0%} of {n} losing trades lost more than 1.1R; the average loss is {avg_loss}.",
        "Use hard stops and no discretionary widening for 20 trades.",
    ),
}
CATEGORY = {
    "PLAN_NONADHERENCE": "process",
    "REVENGE_TRADING": "psychology",
    "TIME_OF_DAY_LEAK": "time",
    "OVERTRADING": "process",
    "TILT_SIZING": "psychology",
    "SETUP_DRIFT": "edge",
    "RULE_BREAK_COST": "process",
    "EMOTION_LEAK": "psychology",
    "CUTTING_WINNERS": "execution",
    "LETTING_LOSERS_RUN": "risk",
}


# -------------------------------------------------------------- candidates
def _local(trade: Trade, zone: ZoneInfo) -> datetime:
    return _as_utc(trade.opened_at).astimezone(zone)


def _split(trades: list[Trade], keep: Callable[[Trade], bool]) -> tuple[list[Trade], list[Trade]]:
    inside = [t for t in trades if keep(t)]
    ids = {t.id for t in inside}
    return inside, [t for t in trades if t.id not in ids]


def build_candidates(
    trades: list[Trade],
    reviews: dict[str, TradeReview],
    zone: ZoneInfo,
    db: Session,
    user_id: UUID,
    account_id: UUID | None,
) -> list[Candidate]:
    out: list[Candidate] = []

    reviewed = [t for t in trades if str(t.id) in reviews]
    off, followed = _split(reviewed, lambda t: reviews[str(t.id)].plan_adherence != "yes")
    out.append(Candidate("PLAN_NONADHERENCE", "process", "all", off, followed))

    window = 30
    history = get_recent_loss_trades(db, user_id, account_id, trades, window)
    flagged = {t.id for t in detect_revenge_trades(trades, window, history)}
    cohort, rest = _split(trades, lambda t: t.id in flagged)
    out.append(Candidate("REVENGE_TRADING", "psychology", "all", cohort, rest, {"window": window}))

    by_hour: dict[int, list[Trade]] = defaultdict(list)
    for trade in trades:
        by_hour[_local(trade, zone).hour].append(trade)
    for hour, members in sorted(by_hour.items()):
        ids = {t.id for t in members}
        out.append(
            Candidate(
                "TIME_OF_DAY_LEAK",
                "time",
                f"hour-{hour:02}",
                members,
                [t for t in trades if t.id not in ids],
                {"label": f"{hour:02}:00", "min_n": MIN_TIME_BUCKET},
            )
        )

    by_day: dict[str, list[Trade]] = defaultdict(list)
    for trade in sorted(trades, key=lambda t: _as_utc(t.opened_at)):
        by_day[_local(trade, zone).date().isoformat()].append(trade)
    counts = sorted(len(day) for day in by_day.values())
    if counts:
        cap = max(2, counts[min(len(counts) - 1, int(0.75 * len(counts)))])
        late_ids = {t.id for day in by_day.values() for t in day[cap:]}
        cohort, rest = _split(trades, lambda t: t.id in late_ids)
        out.append(Candidate("OVERTRADING", "process", "all", cohort, rest, {"k": cap + 1, "cap": cap}))

    sizes = [float(t.size) for t in trades if t.size is not None]
    if sizes:
        typical = median(sizes)
        ordered = sorted(trades, key=lambda t: _as_utc(t.opened_at))
        tilted = {
            current.id
            for previous, current in zip(ordered, ordered[1:], strict=False)
            if float(previous.pnl or 0) < 0
            and current.size is not None
            and float(current.size) > 1.25 * typical
        }
        cohort, rest = _split(trades, lambda t: t.id in tilted)
        out.append(Candidate("TILT_SIZING", "psychology", "all", cohort, rest))

    by_strategy: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        by_strategy[(trade.strategy or "Unspecified").strip() or "Unspecified"].append(trade)
    for name, members in sorted(by_strategy.items()):
        members = sorted(members, key=lambda t: _as_utc(t.closed_at or t.opened_at))
        if len(members) >= MIN_COHORT + MIN_REST:
            recent, older = members[-MIN_COHORT:], members[:-MIN_COHORT]
            out.append(Candidate("SETUP_DRIFT", "edge", name, recent, older, {"label": name}))

    by_break: dict[str, list[Trade]] = defaultdict(list)
    by_emotion: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        for label in trade.rule_breaks or []:
            by_break[label].append(trade)
        if trade.emotional_state and trade.emotional_state.strip().lower() in NEGATIVE_EMOTIONS:
            by_emotion[trade.emotional_state.strip()].append(trade)
    for code, groups in (("RULE_BREAK_COST", by_break), ("EMOTION_LEAK", by_emotion)):
        for label, members in sorted(groups.items()):
            ids = {t.id for t in members}
            out.append(
                Candidate(
                    code,
                    "process" if code == "RULE_BREAK_COST" else "psychology",
                    label.casefold(),
                    members,
                    [t for t in trades if t.id not in ids],
                    {"label": label},
                )
            )
    return out


def evaluate(candidate: Candidate) -> bool:
    min_n = int(candidate.params.get("min_n", MIN_COHORT))
    candidate.cohort_r = [v for t in candidate.cohort if (v := _r(t)) is not None]
    candidate.rest_r = [v for t in candidate.rest if (v := _r(t)) is not None]
    if len(candidate.cohort_r) < min_n or len(candidate.rest_r) < MIN_REST:
        return False
    candidate.diff = mean(candidate.cohort_r) - mean(candidate.rest_r)
    candidate.ci = bootstrap_diff_ci(candidate.cohort_r, candidate.rest_r)
    candidate.p_value = welch_p_value(candidate.cohort_r, candidate.rest_r)
    return True


def _holds_out_of_time(candidate: Candidate, all_trades: list[Trade]) -> bool | None:
    ordered = sorted(all_trades, key=lambda t: _as_utc(t.opened_at))
    if len(ordered) < 2 * (MIN_COHORT + MIN_REST):
        return None
    cutoff = _as_utc(ordered[len(ordered) // 2].opened_at)
    cohort_ids = {t.id for t in candidate.cohort}
    verdicts = []
    for early in (True, False):
        side = [t for t in ordered if (_as_utc(t.opened_at) < cutoff) == early]
        a = [v for t in side if t.id in cohort_ids and (v := _r(t)) is not None]
        b = [v for t in side if t.id not in cohort_ids and (v := _r(t)) is not None]
        if len(a) < 5 or len(b) < 5:
            return None
        verdicts.append(mean(a) < mean(b))
    return all(verdicts)


def _dollar_impact(candidate: Candidate, currencies: dict[str, str]) -> float | None:
    everyone = candidate.cohort + candidate.rest
    if len({trade_currency(t, currencies) for t in everyone}) > 1 or not candidate.rest:
        return None
    gap = mean(_pnl(t) for t in candidate.rest) - mean(_pnl(t) for t in candidate.cohort)
    return round(gap * len(candidate.cohort), 2) if gap > 0 else None


def _severity(diff: float, confidence: str) -> str:
    size = abs(diff)
    level = "high" if size >= 0.5 else "medium" if size >= 0.25 else "low"
    return "low" if confidence == "low" and level == "high" else level


def _fingerprint(code: str, scope: str, account_id: UUID | None) -> str:
    raw = f"{code}|{scope}|{account_id or 'all'}"
    return f"{code}:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def _evidence(candidate: Candidate) -> dict[str, Any]:
    return {
        "cohort_n": len(candidate.cohort_r),
        "rest_n": len(candidate.rest_r),
        "cohort_mean_r": round(mean(candidate.cohort_r), 3),
        "rest_mean_r": round(mean(candidate.rest_r), 3),
        "difference_ci_95": [round(candidate.ci[0], 3), round(candidate.ci[1], 3)],
        "trade_ids": [str(t.id) for t in candidate.cohort[:50]],
    }


def _threshold_findings(trades: list[Trade]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    winners = [t for t in trades if _pnl(t) > 0 and _r(t) is not None and t.mfe_r is not None]
    if len(winners) >= MIN_COHORT:
        won = sum(_r(t) or 0 for t in winners)
        available = sum(float(t.mfe_r or 0) for t in winners)
        if available > 0 and won / available < 0.5:
            capture = won / available
            findings.append(
                {
                    "code": "CUTTING_WINNERS",
                    "scope": "all",
                    "sample": len(winners),
                    "effect": capture,
                    "vars": {
                        "n": len(winners),
                        "capture": capture,
                        "avg_win": _fmt_r(won / len(winners)),
                        "avg_mfe": _fmt_r(available / len(winners)),
                    },
                    "trade_ids": [str(t.id) for t in winners[:50]],
                    "priority": (0.5 - capture) * len(winners) * 10,
                }
            )
    losers = [t for t in trades if _pnl(t) < 0 and _r(t) is not None]
    if len(losers) >= MIN_COHORT:
        overrun = [t for t in losers if (_r(t) or 0) < LOSS_OVERRUN_R]
        share = len(overrun) / len(losers)
        avg_loss = mean(_r(t) or 0 for t in losers)
        if share >= 0.25 and avg_loss < LOSS_OVERRUN_R:
            findings.append(
                {
                    "code": "LETTING_LOSERS_RUN",
                    "scope": "all",
                    "sample": len(losers),
                    "effect": avg_loss,
                    "vars": {"n": len(losers), "share": share, "avg_loss": _fmt_r(avg_loss)},
                    "trade_ids": [str(t.id) for t in overrun[:50]],
                    "priority": share * len(losers) * 10,
                }
            )
    return findings


# -------------------------------------------------------------- process score
def _journal_fraction(trade: Trade, reviewed: bool) -> float:
    return sum([reviewed, bool(trade.setup), bool(trade.emotional_state), bool(trade.notes)]) / 4


def process_components(trades: list[Trade], reviews: dict[str, TradeReview]) -> dict[str, float | None]:
    if not trades:
        return {k: None for k in ("plan_adherence", "risk_compliance", "journaling", "rule_compliance")}
    scores = {"yes": 1.0, "partly": 0.5, "no": 0.0}
    adherence = [scores.get(reviews[str(t.id)].plan_adherence, 0.0) for t in trades if str(t.id) in reviews]

    def risk_ok(trade: Trade) -> float:
        if trade.stop_loss is None:
            return 0.0
        value = _r(trade)
        return 0.0 if value is not None and value < LOSS_OVERRUN_R else 1.0

    return {
        "plan_adherence": mean(adherence) * 100 if adherence else None,
        "risk_compliance": mean(risk_ok(t) for t in trades) * 100,
        "journaling": mean(_journal_fraction(t, str(t.id) in reviews) for t in trades) * 100,
        "rule_compliance": mean(0.0 if t.rule_breaks else 1.0 for t in trades) * 100,
    }


PROCESS_WEIGHTS = {"plan_adherence": 0.3, "risk_compliance": 0.3, "journaling": 0.2, "rule_compliance": 0.2}


def process_total(components: dict[str, float | None]) -> float | None:
    available = {k: v for k, v in components.items() if v is not None}
    weight = sum(PROCESS_WEIGHTS[k] for k in available)
    return sum(PROCESS_WEIGHTS[k] * v for k, v in available.items()) / weight if weight else None


def process_score(
    trades: list[Trade], reviews: dict[str, TradeReview], zone: ZoneInfo, weeks: int = 8
) -> dict[str, Any]:
    components = process_components(trades, reviews)
    by_week: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        closed = _as_utc(trade.closed_at or trade.opened_at).astimezone(zone).date()
        by_week[(closed - timedelta(days=closed.weekday())).isoformat()].append(trade)
    series = []
    for week_start in sorted(by_week)[-weeks:]:
        members = by_week[week_start]
        series.append(
            {
                "week_start": week_start,
                "trades": len(members),
                "total": process_total(process_components(members, reviews)),
            }
        )
    scored = [row["total"] for row in series if row["total"] is not None]
    return {
        "total": process_total(components),
        "components": components,
        "weekly": series,
        "trend": scored[-1] - scored[-2] if len(scored) >= 2 else None,
        "note": "Process quality is scored separately from P&L: plan adherence, stop discipline, "
        "journaling completeness and rule compliance.",
    }


# --------------------------------------------------------------------- core
def core_metrics(trades: list[Trade], currencies: dict[str, str]) -> dict[str, Any]:
    base = metrics_for(trades, currencies)
    values = [v for t in trades if (v := _r(t)) is not None]
    wins = sum(1 for t in trades if _pnl(t) > 0)
    win_ci = wilson_interval(wins, len(trades))
    spread = pstdev(values) if len(values) > 1 else 0.0
    sqn = math.sqrt(len(values)) * mean(values) / spread if spread > 0 else None
    exp_ci = bootstrap_mean_ci(values) if len(values) >= MIN_COHORT else None
    return {
        "trade_count": base["trade_count"],
        "r_sample_count": len(values),
        "win_rate_pct": base["win_rate_pct"],
        "win_rate_ci_pct": [win_ci[0] * 100, win_ci[1] * 100] if win_ci else None,
        "expectancy_r": base["expectancy_r"],
        "expectancy_ci": list(exp_ci) if exp_ci else None,
        "profit_factor": base["profit_factor"],
        "sqn": sqn if len(values) >= MIN_COHORT else None,
        "sqn_label": sqn_label(sqn) if len(values) >= MIN_COHORT else None,
        "max_drawdown_r": base["max_drawdown_r"],
        "average_win_r": base["average_win_r"],
        "average_loss_r": base["average_loss_r"],
        "currency": base["currency"],
        "confidence": confidence_tier(len(values)),
    }


def readiness(trades: list[Trade], reviews: dict[str, TradeReview]) -> dict[str, Any]:
    r_count = sum(1 for t in trades if t.r_multiple is not None)
    tips = []
    if len(trades) < 30:
        tips.append(f"Log {30 - len(trades)} more closed trades for decision-grade statistics.")
    if trades and r_count < len(trades):
        tips.append(f"{len(trades) - r_count} closed trades have no R-multiple; add a stop and risk to each.")
    if trades and len(reviews) < len(trades):
        tips.append(f"{len(trades) - len(reviews)} closed trades are unreviewed; reviews unlock plan-adherence analysis.")
    if trades and sum(1 for t in trades if t.emotional_state) < len(trades) / 2:
        tips.append("Record your emotional state on trades so behavior patterns can be tested.")
    return {
        "closed_trades": len(trades),
        "r_trades": r_count,
        "reviewed_trades": len(reviews),
        "minimum_trades": 30,
        "ready": len(trades) >= 30 and r_count >= 30,
        "tips": tips,
    }


# ----------------------------------------------------------------- pipeline
def render(code: str, **values: Any) -> tuple[str, str, str]:
    title, body, action = TEMPLATES[code]
    return title.format(**values), body.format(**values), action.format(**values)


def run_agent(
    db: Session,
    user_id: UUID,
    account_id: UUID | None,
    start: datetime | None,
    end: datetime | None,
    zone: ZoneInfo,
) -> dict[str, Any]:
    trades = get_closed_trades(db, user_id, account_id, start, end)
    currencies = currency_map(db, user_id, trades)
    reviews = load_reviews(db, user_id, trades)

    candidates = [c for c in build_candidates(trades, reviews, zone, db, user_id, account_id) if evaluate(c)]
    for candidate, q in zip(candidates, benjamini_hochberg([c.p_value for c in candidates]), strict=True):
        candidate.q_value = q

    found: list[dict[str, Any]] = []
    for c in candidates:
        if c.diff >= 0 or c.ci[1] >= 0 or c.q_value > Q_THRESHOLD:
            continue
        sample = len(c.cohort_r)
        confidence = confidence_tier(sample)
        impact = _dollar_impact(c, currencies)
        vars_ = {
            "r_cohort": _fmt_r(mean(c.cohort_r)),
            "r_rest": _fmt_r(mean(c.rest_r)),
            "n": sample,
            **c.params,
        }
        label = c.params.get("label", "")
        title, body, action = render(c.code, label=label, **{k: v for k, v in vars_.items() if k != "label"})
        proxy = abs(c.diff) * sample * 10
        found.append(
            {
                "code": c.code,
                "category": c.category,
                "scope": c.scope,
                "severity": _severity(c.diff, confidence),
                "confidence": confidence,
                "sample_size": sample,
                "effect_size": c.diff,
                "p_value": c.p_value,
                "q_value": c.q_value,
                "est_dollar_impact": impact,
                "priority": (impact if impact else proxy) * CONFIDENCE_WEIGHT[confidence],
                "title": title,
                "body": body,
                "action": action,
                "evidence": _evidence(c),
                "holds": _holds_out_of_time(c, trades),
            }
        )
    for item in _threshold_findings(trades):
        confidence = confidence_tier(item["sample"])
        title, body, action = render(item["code"], **item["vars"])
        found.append(
            {
                "code": item["code"],
                "category": CATEGORY[item["code"]],
                "scope": item["scope"],
                "severity": "medium",
                "confidence": confidence,
                "sample_size": item["sample"],
                "effect_size": item["effect"],
                "p_value": None,
                "q_value": None,
                "est_dollar_impact": None,
                "priority": item["priority"] * CONFIDENCE_WEIGHT[confidence],
                "title": title,
                "body": body,
                "action": action,
                "evidence": {"cohort_n": item["sample"], "trade_ids": item["trade_ids"]},
                "holds": None,
            }
        )

    insights = persist_insights(db, user_id, account_id, found)
    return {
        "generated_at": datetime.now(UTC),
        "calc_version": CALC_VERSION,
        "scope": {"account_id": str(account_id) if account_id else None, "timezone": str(zone)},
        "readiness": readiness(trades, reviews),
        "core": core_metrics(trades, currencies),
        "process": process_score(trades, reviews, zone),
        "insights": insights,
        "limitations": [
            "Findings compare this trader's own trades only; no shared or population data is used.",
            "A finding appears only with enough trades, a confidence interval excluding zero and a "
            "multiple-comparison corrected q-value; associations are not proof of cause.",
            "Dollar impact is an estimate from average P&L gaps, not a guarantee. Not financial advice.",
        ],
    }


def serialize(row: AgentInsight) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "code": row.code,
        "category": row.category,
        "severity": row.severity,
        "confidence": row.confidence,
        "sample_size": row.sample_size,
        "effect_size": row.effect_size,
        "p_value": row.p_value,
        "q_value": row.q_value,
        "est_dollar_impact": row.est_dollar_impact,
        "priority_score": row.priority_score,
        "title": row.title,
        "body": row.body,
        "recommended_action": row.recommended_action,
        "evidence": row.evidence,
        "holds_out_of_time": row.holds_out_of_time,
        "active": row.active,
        "status": row.status,
        "feedback": row.feedback,
        "first_detected_at": row.first_detected_at,
        "last_detected_at": row.last_detected_at,
    }


def persist_insights(
    db: Session, user_id: UUID, account_id: UUID | None, found: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    existing = {
        row.fingerprint: row
        for row in db.scalars(select(AgentInsight).where(AgentInsight.user_id == user_id))
    }
    seen: set[str] = set()
    for item in found:
        fingerprint = _fingerprint(item["code"], item["scope"], account_id)
        seen.add(fingerprint)
        row = existing.get(fingerprint)
        if row is None:
            row = AgentInsight(
                user_id=user_id,
                account_id=account_id,
                fingerprint=fingerprint,
                code=item["code"],
                first_detected_at=now,
                evidence={},
            )
            db.add(row)
        row.category = item["category"]
        row.severity = item["severity"]
        row.confidence = item["confidence"]
        row.sample_size = item["sample_size"]
        row.effect_size = item["effect_size"]
        row.p_value = item["p_value"]
        row.q_value = item["q_value"]
        row.est_dollar_impact = item["est_dollar_impact"]
        row.priority_score = item["priority"]
        row.title = item["title"][:200]
        row.body = item["body"]
        row.recommended_action = item["action"]
        row.evidence = item["evidence"]
        row.holds_out_of_time = item["holds"]
        row.last_detected_at = now
        row.active = True
        if row.status == "resolved":
            row.status = "new"
    for fingerprint, row in existing.items():
        in_scope = row.account_id == account_id
        if in_scope and fingerprint not in seen and row.active:
            row.active = False
            if row.status in ("new", "seen"):
                row.status = "resolved"
    db.commit()
    rows = db.scalars(
        select(AgentInsight)
        .where(AgentInsight.user_id == user_id, AgentInsight.active.is_(True))
        .where(AgentInsight.account_id.is_(None) if account_id is None else AgentInsight.account_id == account_id)
        .order_by(AgentInsight.priority_score.desc())
    ).all()
    return [serialize(row) for row in rows]
