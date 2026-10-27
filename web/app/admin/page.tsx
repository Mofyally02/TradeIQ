"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import {
  Activity,
  AlertTriangle,
  BookOpenCheck,
  BrainCircuit,
  ClipboardCheck,
  FileChartColumn,
  Fingerprint,
  FlaskConical,
  LayoutDashboard,
  LockKeyhole,
  NotebookPen,
  Radio,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
  WalletCards,
  Wrench,
} from "lucide-react";
import { ApiError, apiRequest } from "../api";
import "./admin.css";

type Method = "metaapi" | "ea";
type Permission = string;
type Me = { id: string; full_name: string; email: string; roles: string[]; permissions: Permission[] };
type Overview = {
  users: number;
  active_users: number;
  suspended_users: number;
  accounts: number;
  connected_accounts: number;
  failing_accounts: number;
  trades: number;
  deals: number;
  sync_runs_failed: number;
  open_incidents: number;
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
  full_name: string | null;
  email: string;
  role: string;
  status: "active" | "suspended";
  roles: string[];
  method_override: Method | null;
  method: Method;
  accounts: AdminAccount[];
};
type Incident = {
  id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  status: string;
  assigned_to: string | null;
  resolution_reason: string | null;
  created_at: string;
  resolved_at: string | null;
};
type Role = { name: string; description: string; permissions: string[] };
type RecordRow = Record<string, unknown>;

const LABEL: Record<Method, string> = {
  metaapi: "MetaApi (hosted)",
  ea: "Expert Advisor (webhook)",
};

const NAV = [
  { id: "overview", label: "Admin Overview", icon: LayoutDashboard, permission: "overview.read" },
  { id: "users", label: "Users & Workspaces", icon: Users, permission: "users.read" },
  { id: "accounts", label: "Trading Accounts", icon: WalletCards, permission: "accounts.read" },
  { id: "connectors", label: "MT5 Connectors", icon: Radio, permission: "connectors.read" },
  { id: "sync", label: "Sync & Reconciliation", icon: Activity, permission: "sync.read" },
  { id: "integrity", label: "Trade Data Integrity", icon: AlertTriangle, permission: "data_quality.read" },
  { id: "journal", label: "Journal & Review Quality", icon: BookOpenCheck, permission: "journal_quality.read" },
  { id: "intelligence", label: "Intelligence Operations", icon: BrainCircuit, permission: "intelligence.read" },
  { id: "taxonomy", label: "Strategy Taxonomy", icon: NotebookPen, permission: "taxonomy.manage" },
  { id: "risk", label: "Risk Rules & Policies", icon: ShieldCheck, permission: "risk_rules.manage" },
  { id: "development", label: "Development Framework", icon: Wrench, permission: "development.manage" },
  { id: "evaluation", label: "Experiments & Evaluation", icon: FlaskConical, permission: "experiments.manage" },
  { id: "incidents", label: "Support & Incidents", icon: ClipboardCheck, permission: "incidents.manage" },
  { id: "reports", label: "Reports & Exports", icon: FileChartColumn, permission: "journal_quality.read" },
  { id: "roles", label: "Roles & Permissions", icon: LockKeyhole, permission: "users.manage_roles" },
  { id: "audit", label: "Audit Logs", icon: ScrollText, permission: "audit.read" },
  { id: "settings", label: "System Settings", icon: Settings, permission: "settings.manage" },
] as const;

type SectionId = (typeof NAV)[number]["id"];

function messageCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  try {
    const parsed: unknown = JSON.parse(error.message);
    return parsed && typeof parsed === "object" && "code" in parsed
      ? String((parsed as { code: unknown }).code)
      : null;
  } catch {
    return null;
  }
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DataTable({ rows, empty }: { rows: RecordRow[]; empty: string }) {
  const columns = useMemo(
    () => [...new Set(rows.flatMap((row) => Object.keys(row)))].filter((key) => key !== "id"),
    [rows],
  );
  if (!rows.length) return <p className="adm-empty">{empty}</p>;
  return (
    <div className="adm-table-wrap">
      <table className="adm-table">
        <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => (
          <tr key={String(row.id ?? index)}>
            {columns.map((column) => <td key={column}>{display(row[column])}</td>)}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [section, setSection] = useState<SectionId>("overview");
  const [sectionData, setSectionData] = useState<unknown>(null);
  const [sectionLoading, setSectionLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [mfaMode, setMfaMode] = useState<"setup" | "verify" | null>(null);
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaQr, setMfaQr] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [incidentForm, setIncidentForm] = useState({ title: "", category: "operations", severity: "medium", description: "" });

  const loadBase = useCallback(async (includeUsers = true) => {
    const [o, u] = await Promise.all([
      apiRequest<Overview>("/admin/overview"),
      includeUsers
        ? apiRequest<AdminUser[]>("/admin/users?limit=200")
        : Promise.resolve([] as AdminUser[]),
    ]);
    setOverview(o);
    setUsers(u);
  }, []);

  const loadSection = useCallback(async (target: SectionId) => {
    const endpoint: Partial<Record<SectionId, string>> = {
      accounts: "/admin/accounts",
      connectors: "/admin/connectors",
      sync: "/admin/sync-runs",
      integrity: "/admin/reconciliation-issues",
      journal: "/admin/journal-quality",
      intelligence: "/admin/intelligence/health",
      incidents: "/admin/incidents",
      roles: "/admin/roles",
      audit: "/admin/audit-logs",
      settings: "/admin/settings",
    };
    if (target === "sync") {
      setSectionLoading(true);
      try {
        const [runs, reconciliation] = await Promise.all([
          apiRequest<RecordRow[]>("/admin/sync-runs"),
          apiRequest<{ issues: RecordRow[] }>("/admin/reconciliation-issues"),
        ]);
        setSectionData({ runs, issues: reconciliation.issues });
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load synchronization data.");
      } finally {
        setSectionLoading(false);
      }
      return;
    }
    if (!endpoint[target]) {
      setSectionData(null);
      return;
    }
    setSectionLoading(true);
    try {
      setSectionData(await apiRequest<unknown>(endpoint[target]));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this section.");
    } finally {
      setSectionLoading(false);
    }
  }, []);

  const openAdmin = useCallback(async () => {
    try {
      const current = await apiRequest<Me>("/admin/me");
      setMe(current);
      setMfaMode(null);
      setMfaSecret("");
      setMfaQr("");
      await loadBase(current.permissions.includes("users.read"));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 428) {
        setMe(null);
        if (messageCode(caught) === "admin_mfa_setup_required") {
          try {
            const setup = await apiRequest<{ secret: string; otpauth_uri: string }>("/admin/mfa/setup", { method: "POST" });
            setMfaSecret(setup.secret);
            setMfaQr(await QRCode.toDataURL(setup.otpauth_uri, { width: 224, margin: 2, errorCorrectionLevel: "M" }));
            setMfaMode("setup");
          } catch (setupError) {
            if (setupError instanceof ApiError && setupError.status === 409) {
              setMfaMode("verify");
            } else {
              setError(setupError instanceof Error ? setupError.message : "MFA setup failed.");
            }
          }
        } else {
          setMfaMode("verify");
        }
      } else {
        setMe(null);
        throw caught;
      }
    }
  }, [loadBase]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void openAdmin()
        .catch(() => undefined)
        .finally(() => setChecking(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [openAdmin]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (me) void loadSection(section);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSection, me, section]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await apiRequest("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      await openAdmin();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        await apiRequest("/auth/logout", { method: "POST" }).catch(() => undefined);
        setError("This account does not have administrator access.");
      } else {
        setError(caught instanceof Error ? caught.message : "Sign in failed.");
      }
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function verifyMfa(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const path = mfaMode === "setup" ? "/admin/mfa/confirm" : "/admin/mfa/verify";
      await apiRequest(path, { method: "POST", body: JSON.stringify({ code: mfaCode }) });
      setMfaCode("");
      setMfaMode(null);
      await openAdmin();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authenticator verification failed.");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await apiRequest<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
    setOverview(null);
    setUsers([]);
    setMfaMode(null);
    setMfaSecret("");
    setMfaQr("");
  }

  async function run(action: () => Promise<unknown>, message: string) {
    setError("");
    setNotice("");
    try {
      await action();
      await Promise.all([
        loadBase(me?.permissions.includes("users.read") ?? false),
        loadSection(section),
      ]);
      setNotice(message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Action failed.");
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
        `Switch ${user.full_name}? Accounts using the other method will be disconnected and require setup again.`,
      )
    ) return;
    return run(
      () => apiRequest(`/admin/users/${user.id}/mt5-method`, { method: "PUT", body: JSON.stringify({ method }) }),
      `${user.full_name} now uses ${LABEL[target]}.`,
    );
  }

  async function changeStatus(user: AdminUser) {
    const reason = window.prompt(`Reason to ${user.status === "active" ? "suspend" : "restore"} ${user.email}?`);
    if (!reason) return;
    const status = user.status === "active" ? "suspended" : "active";
    await run(
      () => apiRequest(`/admin/users/${user.id}/status`, { method: "PATCH", body: JSON.stringify({ status, reason }) }),
      `${user.email} is now ${status}.`,
    );
  }

  async function assignRole(user: AdminUser, role: string) {
    const reason = window.prompt(`Reason for updating administrator access for ${user.email}?`);
    if (!reason) return;
    await run(
      () => apiRequest(`/admin/users/${user.id}/roles`, { method: "PUT", body: JSON.stringify({ roles: role ? [role] : [], reason }) }),
      `Administrator roles updated for ${user.email}.`,
    );
  }

  async function createIncident(event: FormEvent) {
    event.preventDefault();
    await run(
      () => apiRequest("/admin/incidents", { method: "POST", body: JSON.stringify(incidentForm) }),
      "Incident recorded.",
    );
    setIncidentForm({ title: "", category: "operations", severity: "medium", description: "" });
  }

  async function updateIncident(incident: Incident, status: string) {
    const resolution_reason = status === "resolved" || status === "accepted_exception"
      ? window.prompt("Document the resolution or exception reason.")
      : undefined;
    if ((status === "resolved" || status === "accepted_exception") && !resolution_reason) return;
    await run(
      () => apiRequest(`/admin/incidents/${incident.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, ...(resolution_reason ? { resolution_reason } : {}) }),
      }),
      "Incident updated.",
    );
  }

  if (checking) return <main className="auth-shell"><p>Loading admin access…</p></main>;

  if (!me && mfaMode) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <span className="eyebrow">MofyAlly EDGE · ADMIN SECURITY</span>
          <h1>{mfaMode === "setup" ? "Set up authenticator MFA" : "Verify your authenticator"}</h1>
          {mfaMode === "setup" ? (
            <div className="adm-mfa-help">
              <p>Scan this QR code with your authenticator app, then enter its current six-digit code.</p>
              {mfaQr && (
                // eslint-disable-next-line @next/next/no-img-element
                <img className="adm-mfa-qr" src={mfaQr} alt="QR code to add MofyAlly EDGE to your authenticator app" width={224} height={224} />
              )}
              <p className="adm-mfa-manual">Can&apos;t scan? Enter this key manually:</p>
              <code>{mfaSecret}</code>
              <button type="button" className="adm-text-button" onClick={() => void navigator.clipboard.writeText(mfaSecret)}>Copy key</button>
            </div>
          ) : <p>Enter the six-digit code from your authenticator app to verify this session.</p>}
          <form onSubmit={verifyMfa}>
            <label>Authenticator code<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} required /></label>
            {error && <p role="alert" className="adm-form-error">{error}</p>}
            <button className="button button-primary" disabled={busy || mfaCode.length !== 6}>{busy ? "Verifying…" : mfaMode === "setup" ? "Enable MFA" : "Verify"}</button>
          </form>
          <button className="adm-text-button" onClick={() => void signOut()}>Cancel and sign out</button>
        </section>
      </main>
    );
  }

  if (!me) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <span className="eyebrow">MofyAlly EDGE · ADMIN CONTROL CENTER</span>
          <h1>Admin sign in</h1>
          <p>Restricted workspace. Privileged access requires an authenticator code.</p>
          <form onSubmit={signIn}>
            <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required /></label>
            <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
            {error && <p role="alert" className="adm-form-error">{error}</p>}
            <button className="button button-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        </section>
      </main>
    );
  }

  const currentMe = me;
  const allowedNav = NAV.filter((item) => me.permissions.includes(item.permission));
  const q = query.trim().toLowerCase();
  const shown = users.filter((user) =>
    !q || user.email.toLowerCase().includes(q) || (user.full_name ?? "").toLowerCase().includes(q) ||
    user.accounts.some((account) => (account.login ?? "").includes(q) || account.name.toLowerCase().includes(q)),
  );
  const rowsFrom = (data: unknown): RecordRow[] => {
    if (Array.isArray(data)) return data as RecordRow[];
    if (data && typeof data === "object") return [data as RecordRow];
    return [];
  };
  const currentLabel = NAV.find((item) => item.id === section)?.label ?? "Admin";

  function renderSection() {
    if (section === "overview" && overview) {
      const cards = [
        ["Registered users", overview.users, `${overview.active_users} active · ${overview.suspended_users} suspended`],
        ["Healthy connections", `${overview.connected_accounts}/${overview.accounts}`, "Connected trading accounts"],
        ["Unreconciled signals", overview.failing_accounts, "Accounts reporting connector errors"],
        ["Failed sync runs", overview.sync_runs_failed, "Inspect sync history"],
        ["Trading records", overview.trades, `${overview.deals} imported MT5 deals`],
        ["Open incidents", overview.open_incidents, "Operational incidents requiring attention"],
      ];
      return <>
        <section className="adm-stats">{cards.map(([label, value, note]) => <article className="adm-stat" key={String(label)}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</section>
        <div className="adm-two-col">
          <section className="adm-card"><h2>Operational alerts</h2><p>Signals drawn from persisted account and synchronization records.</p>
            <div className="adm-alert-list">
              <div><i className={overview.failing_accounts ? "bad" : "good"} />{overview.failing_accounts ? `${overview.failing_accounts} connector errors need investigation.` : "No connector errors reported."}</div>
              <div><i className={overview.sync_runs_failed ? "bad" : "good"} />{overview.sync_runs_failed ? `${overview.sync_runs_failed} failed sync runs recorded.` : "No failed sync runs recorded."}</div>
              <div><i className={overview.open_incidents ? "warn" : "good"} />{overview.open_incidents ? `${overview.open_incidents} incidents remain open.` : "No open incidents."}</div>
            </div>
          </section>
          <section className="adm-card"><h2>Integration configuration</h2><p>Credentials are never shown in this workspace.</p>
            <div className="adm-health"><span className={`adm-chip ${overview.metaapi_configured ? "on" : ""}`}>MetaApi token {overview.metaapi_configured ? "configured" : "missing"}</span><span className="adm-chip on">EA endpoint configured</span></div>
            <small className="adm-muted">Default connector: {LABEL[overview.default_method]}</small>
          </section>
        </div>
      </>;
    }
    if (section === "users") {
      return <section className="adm-card">
        <div className="adm-toolbar"><div><h2>Users & workspaces</h2><p>{shown.length} of {users.length} shown · private reflections are not displayed</p></div><input placeholder="Search name, email or account login" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <div className="adm-users">{shown.map((user) => <article className="adm-user" key={user.id}>
          <div><h3>{user.full_name || user.email}</h3><div className="mail">{user.email}</div><span className={`adm-pill ${user.status}`}>{user.status}</span><small className="adm-role-list">{user.roles.join(", ") || "Trader"}</small></div>
          <div className="adm-accts">{user.accounts.length === 0 && <span className="adm-empty">No trading accounts</span>}
            {user.accounts.map((account) => <div className="adm-acct" key={account.id}><div><strong>{account.name}</strong><small>{account.login ?? "—"} · {account.server ?? "—"} · {account.connector}</small></div><span className={`adm-pill ${account.status}`}>{account.status}</span></div>)}
          </div>
          <div className="adm-user-actions">
            {currentMe.permissions.includes("users.manage_status") && <button className="adm-button" onClick={() => void changeStatus(user)}>{user.status === "active" ? "Suspend access" : "Restore access"}</button>}
            {currentMe.permissions.includes("settings.manage") && <select aria-label={`MT5 method for ${user.full_name ?? user.email}`} value={user.method_override ?? "default"} onChange={(event) => void setUserMethod(user, event.target.value)}>
              <option value="default">Default ({LABEL[overview?.default_method ?? "metaapi"]})</option><option value="metaapi">{LABEL.metaapi}</option><option value="ea">{LABEL.ea}</option>
            </select>}
          </div>
        </article>)}</div>
      </section>;
    }
    if (section === "roles") {
      const roleRows = Array.isArray(sectionData) ? sectionData as Role[] : [];
      return <div className="adm-stack">
        <section className="adm-card"><h2>Role-based access</h2><p>Every API operation enforces permission checks. Legacy administrator accounts are treated as Super Admin during migration compatibility.</p>
          {roleRows.map((role) => <article className="adm-role-card" key={role.name}><strong>{role.name.replaceAll("_", " ")}</strong><small>{role.description}</small><div className="adm-permissions">{role.permissions.map((permission) => <span key={permission}>{permission}</span>)}</div></article>)}
        </section>
        <section className="adm-card"><h2>Assign a role</h2><p>Role changes require an administrative reason and are written to the immutable audit log. Super Admin elevation is deliberately unavailable in this form.</p>
          <div className="adm-role-assign">{users.filter((user) => user.role !== "admin").map((user) => <article key={user.id}><strong>{user.full_name || user.email}</strong><select aria-label={`Role for ${user.email}`} defaultValue={user.roles[0] ?? ""} onChange={(event) => void assignRole(user, event.target.value)}><option value="">Trader / no admin role</option>{roleRows.filter((role) => role.name !== "super_admin").map((role) => <option key={role.name} value={role.name}>{role.name.replaceAll("_", " ")}</option>)}</select></article>)}</div>
        </section>
      </div>;
    }
    if (section === "incidents") {
      const incidentRows = Array.isArray(sectionData) ? sectionData as Incident[] : [];
      return <div className="adm-stack">
        <section className="adm-card"><h2>Open a support incident</h2><p>Record only operational diagnostics. Do not include passwords, connector tokens or private journal reflections.</p>
          <form className="adm-incident-form" onSubmit={(event) => void createIncident(event)}>
            <input aria-label="Incident title" placeholder="Short incident title" value={incidentForm.title} onChange={(event) => setIncidentForm({ ...incidentForm, title: event.target.value })} required maxLength={180} />
            <select aria-label="Incident severity" value={incidentForm.severity} onChange={(event) => setIncidentForm({ ...incidentForm, severity: event.target.value })}>{["low", "medium", "high", "critical"].map((item) => <option key={item}>{item}</option>)}</select>
            <textarea aria-label="Incident description" placeholder="Safe diagnostic summary" value={incidentForm.description} onChange={(event) => setIncidentForm({ ...incidentForm, description: event.target.value })} required maxLength={5000} />
            <button className="adm-button primary">Create incident</button>
          </form>
        </section>
        <section className="adm-card"><h2>Incident queue</h2>{incidentRows.map((incident) => <article className="adm-incident" key={incident.id}><div><strong>{incident.title}</strong><small>{incident.category} · {incident.severity} · {incident.created_at}</small><p>{incident.description}</p>{incident.resolution_reason && <small>Resolution: {incident.resolution_reason}</small>}</div><div><span className={`adm-pill ${incident.status}`}>{incident.status}</span>{incident.status !== "resolved" && incident.status !== "accepted_exception" && <button className="adm-button" onClick={() => void updateIncident(incident, "investigating")}>Investigate</button>}{incident.status !== "resolved" && <button className="adm-button" onClick={() => void updateIncident(incident, "resolved")}>Resolve</button>}</div></article>)}</section>
      </div>;
    }
    if (section === "settings" && overview) {
      return <section className="adm-card"><h2>Platform connector settings</h2><p>Changes to the default connector are audited and may require users to reconnect accounts.</p><div className="adm-seg" role="group" aria-label="Default MT5 method">{(Object.keys(LABEL) as Method[]).map((method) => <button key={method} className={overview.default_method === method ? "active" : ""} onClick={() => overview.default_method !== method && void setDefault(method)}>{LABEL[method]}</button>)}</div><div className="adm-health"><span className={`adm-chip ${overview.metaapi_configured ? "on" : ""}`}>MetaApi {overview.metaapi_configured ? "configured" : "missing"}</span><span className="adm-chip on">EA endpoint {overview.public_api_url}</span></div></section>;
    }
    if (section === "sync") {
      const syncRows = rowsFrom(sectionData && typeof sectionData === "object" && "runs" in sectionData ? (sectionData as { runs: unknown }).runs : []);
      return <div className="adm-stack"><section className="adm-card"><h2>Synchronization history</h2><p>Recorded sync runs only; retries are not initiated from this read-only queue.</p><DataTable rows={syncRows} empty="No synchronization runs have been recorded." /></section><section className="adm-card"><h2>Reconciliation candidates</h2><p>Potential mapping gaps from the trade-data integrity scan. Review before treating any candidate as an actual discrepancy.</p><DataTable rows={rowsFrom(sectionData && typeof sectionData === "object" && "issues" in sectionData ? (sectionData as { issues: unknown }).issues : [])} empty="No potential unmapped deal records found." /></section></div>;
    }
    if (section === "integrity") {
      return <section className="adm-card"><h2>Potential trade-data discrepancies</h2><p>Automated candidates are evidence for review, not confirmed discrepancies. This view does not change source or journal records.</p><DataTable rows={rowsFrom(sectionData && typeof sectionData === "object" && "issues" in sectionData ? (sectionData as { issues: unknown }).issues : [])} empty="No potential mapping gaps found." /></section>;
    }
    if (section === "journal") {
      return <section className="adm-card"><h2>Journal completeness</h2><p>Aggregate workflow quality only. Private notes and reflections are never returned.</p><DataTable rows={rowsFrom(sectionData)} empty="No journal metrics available." /></section>;
    }
    if (section === "intelligence") {
      return <section className="adm-card"><h2>Intelligence service status</h2><p>Deterministic per-user analysis health. No shared trader-performance data or external model content is used.</p><DataTable rows={rowsFrom(sectionData)} empty="No intelligence status available." /></section>;
    }
    if (section === "audit") {
      return <section className="adm-card"><h2>Administrative audit log</h2><p>Append-only history for privileged changes. Access and exports are restricted.</p><DataTable rows={rowsFrom(sectionData)} empty="No administrative actions have been recorded." /></section>;
    }
    if (section === "accounts" || section === "connectors" || section === "reports") {
      return <section className="adm-card"><h2>{currentLabel}</h2><p>{section === "reports" ? "Operational aggregates only. User-level trading performance is never exported here." : "Operational metadata only. Passwords and connector secrets are not accessible."}</p><DataTable rows={rowsFrom(sectionData)} empty={`No ${currentLabel.toLowerCase()} data found.`} /></section>;
    }
    const explanations: Record<string, string> = {
      taxonomy: "Versioned strategy taxonomy and alias management are not enabled yet. User-defined strategy labels remain unchanged and no historic trade is silently reclassified.",
      risk: "Versioned shared risk-policy definitions are not enabled yet. Trader-owned risk profiles remain scoped to their account and advisory only.",
      development: "Reusable development-goal templates are not enabled yet. Traders continue to own their personal goals and experiments.",
      evaluation: "Versioned analytics evaluation datasets and approval workflows are not enabled yet. Numeric insights remain deterministic and derived from each user's own records.",
    };
    return <section className="adm-card"><h2>{currentLabel}</h2><p>{explanations[section] ?? "This section is not available yet."}</p><span className="adm-pill pending">Planned follow-on release</span></section>;
  }

  return (
    <div className="adm">
      <header className="adm-top"><div className="adm-brand"><i>EDGE</i><span>MofyAlly EDGE</span><small>ADMIN CONTROL CENTER</small></div><div className="adm-who"><span>{me.full_name} · {me.roles.map((role) => role.replaceAll("_", " ")).join(", ")}</span><button onClick={() => void signOut()}>Sign out</button></div></header>
      <div className="adm-layout">
        <aside className="adm-sidebar"><span className="adm-nav-title">PLATFORM OPERATIONS</span>{allowedNav.map((item) => { const NavIcon = item.icon; return <button key={item.id} className={`adm-nav-item ${section === item.id ? "active" : ""}`} onClick={() => setSection(item.id)}><NavIcon size={18} strokeWidth={1.85} aria-hidden="true" /><span>{item.label}</span></button>; })}</aside>
        <main className="adm-main">
          <div className="adm-page-heading"><div><span className="adm-kicker">ADMINISTRATOR WORKSPACE</span><h1>{currentLabel}</h1><p>Operate the platform, protect source-data integrity and govern intelligence quality.</p></div><button className="adm-button" onClick={() => void Promise.all([loadBase(), loadSection(section)])}>Refresh</button></div>
          {error && <div className="adm-toast err" role="alert">{error}</div>}
          {notice && <div className="adm-toast ok" role="status">{notice}</div>}
          {sectionLoading ? <section className="adm-card"><p>Loading operational records…</p></section> : renderSection()}
          <footer className="adm-footer"><Fingerprint size={15} /> Access is role-checked by the API. Journal reflections and broker credentials are excluded.</footer>
        </main>
      </div>
    </div>
  );
}
