"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleDashed, RefreshCw, XCircle } from "lucide-react";
import { apiRequest } from "./api";

type Step = { key: string; label: string; status: "ok" | "pending" | "failed"; detail: string; fix?: string | null };
type Result = {
  state: "connected" | "action_required" | "waiting";
  connected: boolean;
  headline: string;
  steps: Step[];
  diagnostics: {
    category: string | null;
    ea_version: string;
    terminal_id: string;
    login: string;
    last_error_code: number | null;
    http_status: number | null;
    last_result: string;
    received_at: string;
  } | null;
};

const POLL_MS = 3000;
const MAX_POLLS = 40;

export function ConnectionVerifier({
  accountId,
  accountName,
  onConnected,
  onRepair,
  onClose,
}: {
  accountId: string;
  accountName: string;
  onConnected: () => void;
  onRepair: () => void;
  onClose: () => void;
}) {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [round, setRound] = useState(0);
  const [timedOut, setTimedOut] = useState(false);
  const polls = useRef(0);
  const done = useRef(false);
  const connectedRef = useRef(onConnected);
  useEffect(() => { connectedRef.current = onConnected; });

  const check = useCallback(async () => {
    try {
      const next = await apiRequest<Result>(`/accounts/${accountId}/ea/verify`, { method: "POST" });
      setResult(next);
      setError("");
      if (next.connected) {
        done.current = true;
        connectedRef.current();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not verify the connection.");
    }
  }, [accountId]);

  useEffect(() => {
    polls.current = 0;
    done.current = false;
    window.setTimeout(() => setTimedOut(false), 0);
    const tick = () => {
      if (done.current) return;
      if (polls.current >= MAX_POLLS) { setTimedOut(true); return; }
      polls.current += 1;
      void check();
    };
    const first = window.setTimeout(tick, 0);
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [check, round]);

  const connected = result?.connected;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Verify connection">
      <div className="capture-modal cv-modal">
        <h2>{connected ? "Connected" : `Verifying ${accountName}`}</h2>
        <p className="cv-headline">{error || result?.headline || "Checking the connection…"}</p>
        <ul className="cv-steps">
          {(result?.steps ?? []).map((step) => (
            <li key={step.key} className={`cv-step cv-${step.status}`}>
              {step.status === "ok" ? <CheckCircle2 size={18} /> : step.status === "failed" ? <XCircle size={18} /> : <CircleDashed size={18} />}
              <div>
                <strong>{step.label}</strong>
                <span>{step.detail}</span>
                {step.status !== "ok" && step.fix ? <em>{step.fix}</em> : null}
              </div>
            </li>
          ))}
        </ul>
        {result?.diagnostics && (
          <section className="cv-diagnostics" aria-label="Last accepted EA diagnostic">
            <strong>Last accepted EA diagnostic</strong>
            <span>EA {result.diagnostics.ea_version || "unknown"} · login {result.diagnostics.login || "unknown"} · terminal {result.diagnostics.terminal_id || "unknown"}</span>
            <span>{result.diagnostics.last_result || "No transport result recorded"} · HTTP {result.diagnostics.http_status ?? "—"} · MT5 error {result.diagnostics.last_error_code ?? "—"}</span>
            <small>{result.diagnostics.category?.replaceAll("_", " ")} · {new Date(result.diagnostics.received_at).toLocaleString()}</small>
          </section>
        )}
        <div className="cv-actions">
          {!connected && (
            <>
              <button type="button" className="button button-quiet" onClick={() => setRound((n) => n + 1)}>
                <RefreshCw size={16} /> {timedOut ? "Check again" : "Check now"}
              </button>
              <button type="button" className="button button-quiet" onClick={onRepair}>
                Update EA setup
              </button>
            </>
          )}
          <button type="button" className="button button-primary" onClick={onClose}>
            {connected ? "Done" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
