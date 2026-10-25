"use client";

import { useEffect, useState, type FormEvent } from "react";
import { apiRequest } from "./api";

export type DetectedAccount = {
  id: string;
  login: string;
  server: string | null;
  name: string | null;
  currency: string | null;
  balance: number | null;
  equity: number | null;
};

export type SwitcherAccount = { id: string; name: string; loginId: string; status?: string; provider: string };

const money = (value: number | null, currency: string | null) =>
  value == null ? "—" : `${currency ?? ""} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();

export function useDetectedAccounts(enabled: boolean) {
  const [items, setItems] = useState<DetectedAccount[]>([]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const load = () =>
      apiRequest<DetectedAccount[]>("/devices/detected")
        .then((rows) => !cancelled && setItems(rows))
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [enabled, tick]);
  return { items, refresh: () => setTick((value) => value + 1), remove: (id: string) => setItems((rows) => rows.filter((row) => row.id !== id)) };
}

export function DetectedAccountsBanner({
  items,
  onDismissed,
  onConnected,
}: {
  items: DetectedAccount[];
  onDismissed: (id: string) => void;
  onConnected: (id: string, accountId: string) => void;
}) {
  const [confirming, setConfirming] = useState<DetectedAccount | null>(null);
  if (items.length === 0) return null;

  async function dismiss(item: DetectedAccount) {
    onDismissed(item.id);
    await apiRequest<void>(`/devices/detected/${item.id}/dismiss`, { method: "POST" }).catch(() => undefined);
  }

  return (
    <>
      <div className="detected-stack">
        {items.map((item) => (
          <div className="detected-card" key={item.id}>
            <span className="detected-pulse" />
            <div className="detected-copy">
              <strong>New MT5 account detected{item.name ? `: ${item.name}` : ""}</strong>
              <span>
                Login {item.login}
                {item.server ? ` · ${item.server}` : ""} · Balance {money(item.balance, item.currency)}
              </span>
            </div>
            <div className="detected-actions">
              <button type="button" className="button button-quiet" onClick={() => void dismiss(item)}>Not now</button>
              <button type="button" className="button button-primary" onClick={() => setConfirming(item)}>Connect account</button>
            </div>
          </div>
        ))}
      </div>
      {confirming && (
        <ConfirmDetectedModal
          item={confirming}
          onClose={() => setConfirming(null)}
          onConnected={(accountId) => {
            onConnected(confirming.id, accountId);
            setConfirming(null);
          }}
        />
      )}
    </>
  );
}

function ConfirmDetectedModal({
  item,
  onClose,
  onConnected,
}: {
  item: DetectedAccount;
  onClose: () => void;
  onConnected: (accountId: string) => void;
}) {
  const [login, setLogin] = useState("");
  const [server, setServer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const account = await apiRequest<{ id: string }>(`/devices/detected/${item.id}/connect`, {
        method: "POST",
        body: JSON.stringify({ login: login.trim(), server: server.trim() }),
      });
      onConnected(account.id);
    } catch (connectError) {
      setError(connectError instanceof Error ? connectError.message : "Could not connect this account.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <form className="capture-modal account-setup-modal" onSubmit={(event) => void submit(event)} role="dialog" aria-modal="true" aria-labelledby="detected-title">
        <div className="modal-heading"><div><span className="eyebrow">CONFIRM ACCOUNT</span><h2 id="detected-title">Confirm this is your account</h2></div></div>
        <p className="wiz-note">Enter the login and server of the account TradeIQ detected so we can confirm they match. Your password is never needed.</p>
        <label>Account login<input value={login} inputMode="numeric" onChange={(event) => setLogin(event.target.value)} placeholder="e.g. 592226966" required autoFocus /></label>
        <label>Server<input value={server} onChange={(event) => setServer(event.target.value)} placeholder="e.g. FxPro-MT5 Demo" required /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="button button-quiet" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="button button-primary" disabled={busy}>{busy ? "Confirming..." : "Confirm and connect"}</button>
        </div>
      </form>
    </div>
  );
}

function EyeIcon({ off }: { off?: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M4 4l16 16" />}
    </svg>
  );
}

export function ViewToggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`view-toggle${on ? " is-on" : ""}`} onClick={onClick} aria-pressed={on}>
      <span className="vt-icon"><EyeIcon off={!on} /></span>
      {on ? "In view" : "Add to view"}
    </button>
  );
}

export function AccountSwitcher({
  accounts,
  viewIds,
  onToggle,
  onAll,
}: {
  accounts: SwitcherAccount[];
  viewIds: string[];
  onToggle: (id: string) => void;
  onAll: () => void;
}) {
  const mt5 = accounts.filter((item) => item.provider === "MT5" && item.status === "connected");
  if (mt5.length < 2) return null;
  return (
    <div className="account-switcher" role="group" aria-label="Accounts in view">
      <button type="button" className={`switch-chip${viewIds.length === 0 ? " is-on" : ""}`} onClick={onAll}>All</button>
      {mt5.map((item) => (
        <button type="button" key={item.id} className={`switch-chip${viewIds.includes(item.id) ? " is-on" : ""}`} onClick={() => onToggle(item.id)} aria-pressed={viewIds.includes(item.id)} title={item.loginId}>
          <EyeIcon off={!viewIds.includes(item.id)} />
          {item.name}
        </button>
      ))}
    </div>
  );
}
