"use client";

import { useEffect, useMemo, useState } from "react";

type CalendarTrade = {
  id: string;
  symbol: string;
  direction: "Long" | "Short";
  strategy: string;
  date: string;
  outcome: "Win" | "Loss" | "Flat" | "Open" | "Planned" | "Discarded";
  pnl: number | null;
  source?: "demo" | "manual" | "mt5";
};

type CalendarProps = {
  trades: CalendarTrade[];
  timezone: string;
  onTimezoneChange: (timezone: string) => void;
};

type DayRecord = {
  key: string;
  day: number;
  pnl: number;
  trades: CalendarTrade[];
};

const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const timezoneOptions = [
  { value: "local", label: "Device time" },
  { value: "UTC", label: "UTC" },
  { value: "Europe/London", label: "London" },
  { value: "America/New_York", label: "New York" },
];
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function formatMoney(value: number, signed = false) {
  const formatted = currency.format(Math.abs(value));
  if (value < 0) return `−${formatted}`;
  return signed && value > 0 ? `+${formatted}` : formatted;
}

function getZonedParts(value: string | Date, timezone: string) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "";
  return { year: Number(part("year")), month: Number(part("month")), day: Number(part("day")), hour: Number(part("hour")) };
}

function toDateKey(year: number, month: number, day: number) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function monthName(year: number, month: number) {
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month, 1)));
}

function formatTime(value: string, timezone: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Unknown time";
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: timezone }).format(date);
}

function useCalendarData(trades: CalendarTrade[], timezone: string) {
  return useMemo(() => {
    const result = new Map<string, DayRecord>();
    for (const trade of trades) {
      if ((trade.outcome !== "Win" && trade.outcome !== "Loss" && trade.outcome !== "Flat") || trade.pnl === null) continue;
      const parts = getZonedParts(trade.date, timezone);
      if (!parts) continue;
      const key = toDateKey(parts.year, parts.month, parts.day);
      const record = result.get(key) ?? { key, day: parts.day, pnl: 0, trades: [] };
      record.pnl += trade.pnl;
      record.trades.push(trade);
      result.set(key, record);
    }
    return result;
  }, [trades, timezone]);
}

function createMonthCells(year: number, month: number) {
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const mondayOffset = (new Date(Date.UTC(year, month, 1)).getUTCDay() + 6) % 7;
  const cells: (number | null)[] = Array.from({ length: mondayOffset }, () => null);
  for (let day = 1; day <= daysInMonth; day += 1) cells.push(day);
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function CalendarIcon() {
  return <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="5.5" width="16" height="15" rx="2" /><path d="M8 3.5v4M16 3.5v4M4 10h16" /></svg>;
}

function Chevron({ direction }: { direction: "left" | "right" }) {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={direction === "left" ? "m15 18-6-6 6-6" : "m9 18 6-6-6-6"} /></svg>;
}

function DayCell({ day, year, month, record, selected, best, onSelect, compact = false }: {
  day: number;
  year: number;
  month: number;
  record?: DayRecord;
  selected?: boolean;
  best?: boolean;
  onSelect?: (key: string) => void;
  compact?: boolean;
}) {
  const positive = (record?.pnl ?? 0) > 0;
  const negative = (record?.pnl ?? 0) < 0;
  const className = [
    "pnl-day",
    record ? positive ? "pnl-positive" : negative ? "pnl-negative" : "pnl-flat" : "pnl-empty",
    selected ? "is-selected" : "",
    best ? "is-best" : "",
    compact ? "compact-day" : "",
  ].filter(Boolean).join(" ");
  const label = record
    ? `${monthName(year, month)} ${day}: ${formatMoney(record.pnl)}, ${record.trades.length} ${record.trades.length === 1 ? "trade" : "trades"}`
    : `${monthName(year, month)} ${day}: no closed trades`;
  const content = <><span className="pnl-day-number">{day}</span>{record && <span className="pnl-day-value">{formatMoney(record.pnl, true)}</span>}{best && <span className="best-day-marker" aria-label="Best day">★</span>}</>;
  return <button type="button" className={className} aria-label={label} aria-pressed={selected} title={label} onClick={() => onSelect?.(toDateKey(year, month + 1, day))}>{content}</button>;
}

function MiniMonth({ year, month, records, maxAbs, onOpen }: { year: number; month: number; records: Map<string, DayRecord>; maxAbs: number; onOpen: (month: number) => void }) {
  const cells = createMonthCells(year, month);
  const total = [...records.values()].filter((record) => record.key.startsWith(`${year}-${String(month + 1).padStart(2, "0")}-`)).reduce((sum, record) => sum + record.pnl, 0);
  return <button type="button" className="year-month-card" onClick={() => onOpen(month)} aria-label={`Open ${monthName(year, month)}, net P and L ${formatMoney(total)}`}>
    <span className="year-month-heading">{new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(year, month, 1)))}</span>
    <div className="year-month-grid">{cells.map((day, index) => {
      if (day === null) return <span className="year-empty-day" key={`empty-${index}`} />;
      const record = records.get(toDateKey(year, month + 1, day));
      const intensity = record ? Math.min(1, Math.abs(record.pnl) / maxAbs) : 0;
      return <span key={day} className={`year-heat-day ${record ? record.pnl > 0 ? "heat-positive" : record.pnl < 0 ? "heat-negative" : "heat-flat" : ""}`} style={record ? { opacity: .35 + intensity * .65 } : undefined} title={record ? `${day}: ${formatMoney(record.pnl)}` : `${day}: no closed trades`} />;
    })}</div>
    <span className={`year-month-total ${total >= 0 ? "positive" : "negative"}`}>{formatMoney(total, true)}</span>
  </button>;
}

export function PnlCalendar({ trades, timezone, onTimezoneChange }: CalendarProps) {
  const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const activeTimezone = timezone === "local" ? localTimezone : timezone;
  const records = useCalendarData(trades, activeTimezone);
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const latestTrade = trades
      .map((trade) => Date.parse(trade.date))
      .filter(Number.isFinite)
      .reduce((latest, current) => Math.max(latest, current), Date.UTC(2026, 9, 1));
    const latestDate = new Date(latestTrade);
    return new Date(latestDate.getUTCFullYear(), latestDate.getUTCMonth(), 1);
  });
  useEffect(() => {
    const timeout = window.setTimeout(() => setSelectedMonth(new Date()), 0);
    return () => window.clearTimeout(timeout);
  }, []);
  const [selectedDay, setSelectedDay] = useState("");
  const [yearMode, setYearMode] = useState(false);
  const year = selectedMonth.getFullYear();
  const month = selectedMonth.getMonth();
  const days = createMonthCells(year, month);
  const rows = Array.from({ length: days.length / 7 }, (_, index) => days.slice(index * 7, index * 7 + 7));
  const monthRecords = [...records.values()].filter((record) => record.key.startsWith(`${year}-${String(month + 1).padStart(2, "0")}-`));
  const monthTotal = monthRecords.reduce((sum, record) => sum + record.pnl, 0);
  const positiveDays = monthRecords.filter((record) => record.pnl > 0);
  const bestDay = positiveDays.length ? positiveDays.reduce((best, record) => record.pnl > best.pnl ? record : best) : null;
  const selectedRecord = records.get(selectedDay);
  const selectedDate = selectedDay ? new Date(`${selectedDay}T12:00:00Z`) : null;
  const hourlyRecords = selectedRecord?.trades.reduce((hours, trade) => {
    const parts = getZonedParts(trade.date, activeTimezone);
    if (!parts) return hours;
    const hourTrades = hours.get(parts.hour) ?? [];
    hourTrades.push(trade);
    hours.set(parts.hour, hourTrades);
    return hours;
  }, new Map<number, CalendarTrade[]>()) ?? new Map<number, CalendarTrade[]>();
  const hourlyValues = Array.from({ length: 24 }, (_, hour) => (hourlyRecords.get(hour) ?? []).reduce((sum, trade) => sum + (trade.pnl ?? 0), 0));
  const maxHourlyMagnitude = Math.max(1, ...hourlyValues.map(Math.abs));
  const yearRecords = [...records.values()].filter((record) => record.key.startsWith(`${year}-`));
  const maxYearMagnitude = Math.max(1, ...yearRecords.map((record) => Math.abs(record.pnl)));

  function moveMonth(offset: number) {
    setSelectedMonth(new Date(year, month + offset, 1));
    setSelectedDay("");
  }

  function openMonth(nextMonth: number) {
    setSelectedMonth(new Date(year, nextMonth, 1));
    setSelectedDay("");
    setYearMode(false);
  }

  function showSelectedDay(key: string) {
    setSelectedDay((current) => current === key ? "" : key);
  }

  return <section className="panel pnl-calendar-panel" aria-labelledby="pnl-calendar-title">
    <div className="panel-heading pnl-calendar-heading">
      <div><span className="eyebrow">DAILY PERFORMANCE</span><h2 id="pnl-calendar-title">P&amp;L calendar</h2><p>See the realized result by calendar day, then drill into the trades behind it.</p></div>
      <label className="timezone-control"><span>TIME ZONE</span><select value={timezone} onChange={(event) => onTimezoneChange(event.target.value)} aria-label="Calendar time zone">{timezoneOptions.map((option) => <option key={option.value} value={option.value}>{option.label}{option.value === "local" ? ` · ${localTimezone}` : ""}</option>)}</select></label>
    </div>
    <div className="calendar-toolbar">
      <div className="calendar-view-toggle" role="group" aria-label="Calendar view">
        <button type="button" className={!yearMode ? "active" : ""} onClick={() => setYearMode(false)}>Month</button>
        <button type="button" className={yearMode ? "active" : ""} onClick={() => setYearMode(true)}>Year</button>
      </div>
      <div className="calendar-month-control">
        <button type="button" className="calendar-arrow" onClick={() => moveMonth(yearMode ? -12 : -1)} aria-label={yearMode ? "Previous year" : "Previous month"}><Chevron direction="left" /></button>
        <strong>{yearMode ? year : monthName(year, month)}</strong>
        <button type="button" className="calendar-arrow" onClick={() => moveMonth(yearMode ? 12 : 1)} aria-label={yearMode ? "Next year" : "Next month"}><Chevron direction="right" /></button>
      </div>
      <div className="calendar-period-note"><CalendarIcon /> <span>{yearMode ? "Year at a glance" : `${monthRecords.length} active ${monthRecords.length === 1 ? "day" : "days"}`}</span></div>
    </div>

    {!yearMode ? <div className="calendar-content">
      <div className="month-calendar">
        <div className="calendar-grid calendar-weekdays">{weekdays.map((weekday) => <span key={weekday}>{weekday}</span>)}<span className="week-total-heading">Week</span></div>
        {rows.map((week, rowIndex) => {
          const weeklyTotal = week.reduce<number>((sum, day) => day === null ? sum : sum + (records.get(toDateKey(year, month + 1, day))?.pnl ?? 0), 0);
          return <div className="calendar-grid calendar-week" key={`week-${rowIndex}`}>
            {week.map((day, columnIndex) => <div className="calendar-day-slot" key={day ?? `blank-${rowIndex}-${columnIndex}`}>
              {day === null ? <span className="calendar-blank" /> : <DayCell day={day} year={year} month={month} record={records.get(toDateKey(year, month + 1, day))} selected={selectedDay === toDateKey(year, month + 1, day)} best={bestDay?.day === day} onSelect={showSelectedDay} />}
            </div>)}
            <div className={`calendar-week-total ${weeklyTotal > 0 ? "positive" : weeklyTotal < 0 ? "negative" : ""}`}>{formatMoney(weeklyTotal, true)}</div>
          </div>;
        })}
      </div>
      <div className="calendar-month-summary">
        <span>Month <strong className={monthTotal >= 0 ? "positive" : "negative"}>{formatMoney(monthTotal, true)} net</strong></span>
        <span>{bestDay ? <>Best day <strong className="positive">★ {formatMoney(bestDay.pnl, true)}</strong></> : "No positive days yet"}</span>
      </div>
      {selectedDay && <section className="day-drilldown" aria-label="Selected day P and L details">
        <div className="drilldown-heading"><div><span className="eyebrow">DAY DRILL-DOWN</span><h3>{selectedDate && new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }).format(selectedDate)}</h3></div><div className="drilldown-total"><span>{selectedRecord?.trades.length ?? 0} {selectedRecord?.trades.length === 1 ? "trade" : "trades"}</span><strong className={selectedRecord && selectedRecord.pnl >= 0 ? "positive" : "negative"}>{selectedRecord ? `${formatMoney(selectedRecord.pnl, true)} net` : "—"}</strong></div></div>
        {selectedRecord ? <>
          <div className="hourly-chart" role="img" aria-label={`Hourly P and L for ${selectedDay} in ${activeTimezone}`}>
            {hourlyValues.map((value, hour) => <div className="hourly-column" key={hour} title={`${String(hour).padStart(2, "0")}:00 · ${formatMoney(value)}`}><span className={`hourly-bar ${value > 0 ? "hour-positive" : value < 0 ? "hour-negative" : ""}`} style={{ height: `${value === 0 ? 2 : Math.max(7, Math.abs(value) / maxHourlyMagnitude * 100)}%` }} /></div>)}
          </div>
          <div className="hourly-labels"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>11 PM</span></div>
          <div className="day-trade-list">{selectedRecord.trades.slice().sort((a, b) => a.date.localeCompare(b.date)).map((trade) => <article className="day-trade-row" key={trade.id}><div className={`day-trade-direction ${trade.pnl !== null && trade.pnl < 0 ? "loss" : ""}`}>{trade.direction === "Long" ? "↗" : "↘"}</div><div className="day-trade-main"><strong>{trade.symbol}</strong><span>{formatTime(trade.date, activeTimezone)} · {trade.strategy} · {trade.source === "demo" ? "Illustrative" : "Manual"}</span></div><strong className={`day-trade-pnl ${trade.pnl !== null && trade.pnl >= 0 ? "positive" : "negative"}`}>{formatMoney(trade.pnl ?? 0, true)}</strong></article>)}</div>
        </> : <p className="no-day-trades">No closed trades were recorded on this calendar day.</p>}
      </section>}
    </div> : <div className="year-calendar">
      <div className="year-legend"><span><i className="heat-negative" /> Net loss</span><span><i className="heat-empty" /> No closed trades</span><span><i className="heat-positive" /> Net profit</span></div>
      <div className="year-months">{Array.from({ length: 12 }, (_, monthIndex) => <MiniMonth key={monthIndex} year={year} month={monthIndex} records={records} maxAbs={maxYearMagnitude} onOpen={openMonth} />)}</div>
      <div className="calendar-month-summary"><span>Year <strong className={yearRecords.reduce((sum, record) => sum + record.pnl, 0) >= 0 ? "positive" : "negative"}>{formatMoney(yearRecords.reduce((sum, record) => sum + record.pnl, 0), true)} net</strong></span><span>{yearRecords.length} active days</span></div>
    </div>}
    <p className="calendar-footnote">Only closed trades with recorded realized P&amp;L are included. Daily buckets use the selected time zone; open positions and planned ideas are excluded.</p>
  </section>;
}
