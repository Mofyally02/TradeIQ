"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import "./admin.css";

type Method = "metaapi" | "ea";
type Me = { full_name: string; email: string; role: string };
type Overview = {
  users: number;
  accounts: number;
  connected_accounts: number;
  failing_accounts: number;
  trades: number;
  deals: number;
  accounts_by_connector: Record<string, number>;
  default_method: Method;
  metaapi_configured: boolean;
  public_api_url: string;
};
type AdminAccount = {
  id: string;
  name: string;
  login: string | null;
  server: string | null;
  connector: string;
  status: string;
  last_synced_at: string | null;
  last_error: string | null;
};
type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  method_override: Method | null;
  method: Method;
  accounts: AdminAccount[];
};

const LABEL: Record<Method, string> = { metaapi: "MetaApi (hosted)", ea: "Expert Advisor (webhook)" };

export default function AdminPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    const [o, u] = await Promise.all([
      apiRequest<Overview>("/admin/overview"),
      apiRequest<AdminUser[]>("/admin/users"),
    ]);
    setOverview(o);
    setUsers(u);
  }, []);

  useEffect(() => {
    apiRequest<Me>("/admin/me")
      .then(async (m) => {
        setMe(m);
        await load();
      })
      .catch(() => undefined)
      .finally(() => setChecking(false));
  }, [load]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await apiRequest("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      const m = await apiRequest<Me>("/admin/me").catch(async () => {
        await apiRequest("/auth/logout", { method: "POST" }).catch(() => undefined);
        throw new Error("This account does not have admin access.");
      });
      setMe(m);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign in failed.");
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function signOut() {
    await apiRequest("/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
    setOverview(null);
    setUsers([]);
  }

  async function run(action: () => Promise<unknown>, message: string) {
    setError("");
    setNotice("");
    try {
      await action();
      await load();
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed.");
    }
  }

  function setDefault(method: Method) {
    return run(
      () => apiRequest("/admin/settings", { method: "PUT", body: JSON.stringify({ method }) }),
      `Platform default is now ${LABEL[method]}.`,
    );
  }

  function setUserMethod(user: AdminUser, value: string) {
    const method = value === "default" ? null : (value as Method);
    const target = method ?? overview?.default_method ?? "metaapi";
    if (
      user.accounts.length > 0 &&
      !window.confirm(
        `Switch ${user.full_name} to ${LABEL[target]}? Their accounts using the other method will be disconnected and must be set up again.`,
      )
    ) {
      return;
    }
    return run(
      () => apiRequest(`/admin/users/${user.id}/mt5-method`, { method: "PUT", body: JSON.stringify({ method }) }),
      `${user.full_name} now uses ${LABEL[target]}.`,
    );
  }

  if (checking) return <main className="auth-shell"><p>Loading…</p></main>;

  if (!me) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <span className="eyebrow">TRADEIQ ADMIN</span>
          <h1>Admin sign in</h1>
          <p>Restricted area. Only administrators can continue.</p>
          <form onSubmit={signIn}>
            <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></label>
            <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
            {error && <p role="alert" style={{ color: "#b3261e", margin: 0 }}>{error}</p>}
            <button className="button button-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        </section>
      </main>
    );
  }

  const q = query.trim().toLowerCase();
  const shown = users.filter((u) =>
    !q || u.email.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q) ||
    u.accounts.some((a) => (a.login ?? "").includes(q) || a.name.toLowerCase().includes(q)));

  return (
    <div className="adm">
      <header className="adm-top">
        <div className="adm-brand"><i>IQ</i> TradeIQ <small>ADMIN</small></div>
        <div className="adm-who"><span>{me.full_name} · {me.email}</span><button onClick={signOut}>Sign out</button></div>
      </header>
      <main className="adm-body">
        {error && <div className="adm-toast err" role="alert">{error}</div>}
        {notice && <div className="adm-toast ok" role="status">{notice}</div>}

        {overview && (
          <>
            <section className="adm-stats">
              <div className="adm-stat"><span>Users</span><strong>{overview.users}</strong></div>
              <div className="adm-stat"><span>Accounts</span><strong>{overview.accounts}</strong></div>
              <div className="adm-stat good"><span>Connected</span><strong>{overview.connected_accounts}</strong></div>
              <div className="adm-stat bad"><span>Failing</span><strong>{overview.failing_accounts}</strong></div>
              <div className="adm-stat"><span>Trades</span><strong>{overview.trades}</strong></div>
              <div className="adm-stat"><span>Deals</span><strong>{overview.deals}</strong></div>
            </section>

            <section className="adm-card">
              <h2>MT5 connection method</h2>
              <p>The platform default applies to every user without an override. Users can be switched individually below.</p>
              <div className="adm-health">
                <span className={`adm-chip ${overview.metaapi_configured ? "on" : ""}`}>MetaApi token {overview.metaapi_configured ? "configured" : "missing"}</span>
                <span className="adm-chip on">EA webhook <code>{overview.public_api_url}</code></span>
              </div>
              <div className="adm-seg" role="group" aria-label="Default MT5 method">
                {(Object.keys(LABEL) as Method[]).map((m) => (
                  <button key={m} className={overview.default_method === m ? "active" : ""} onClick={() => overview.default_method !== m && setDefault(m)}>{LABEL[m]}</button>
                ))}
              </div>
            </section>
          </>
        )}

        <section className="adm-card">
          <div className="adm-toolbar">
            <div><h2>Users</h2><p style={{ margin: 0 }}>{shown.length} of {users.length} shown</p></div>
            <input placeholder="Search name, email or MT5 login" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="adm-users">
            {shown.map((u) => (
              <article className="adm-user" key={u.id}>
                <div>
                  <h3>{u.full_name || u.email}{u.role === "admin" && <em>ADMIN</em>}</h3>
                  <div className="mail">{u.email}</div>
                </div>
                <div className="adm-accts">
                  {u.accounts.length === 0 && <span className="adm-empty">No trading accounts</span>}
                  {u.accounts.map((a) => (
                    <div className="adm-acct" key={a.id} title={a.last_error ?? ""}>
                      <div><strong>{a.name}</strong><small>{a.login ?? "—"} · {a.server ?? "—"} · {a.connector}{a.last_error ? ` · ${a.last_error}` : ""}</small></div>
                      <span className={`adm-pill ${a.status}`}>{a.status}</span>
                    </div>
                  ))}
                </div>
                <select value={u.method_override ?? "default"} onChange={(e) => setUserMethod(u, e.target.value)} aria-label={`MT5 method for ${u.full_name}`}>
                  <option value="default">Default ({LABEL[overview?.default_method ?? "metaapi"]})</option>
                  <option value="metaapi">{LABEL.metaapi}</option>
                  <option value="ea">{LABEL.ea}</option>
                </select>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
