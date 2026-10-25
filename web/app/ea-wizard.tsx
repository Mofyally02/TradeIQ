"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "./api";

type Os = "mac" | "windows";

function detectOs(): Os {
  if (typeof navigator === "undefined") return "windows";
  return /mac|iphone|ipad|ipod/i.test(navigator.userAgent) ? "mac" : "windows";
}

export function EaSetupWizard({
  accountId,
  accountName,
  webhookUrl,
  onClose,
}: {
  accountId?: string;
  accountName: string;
  webhookUrl: string;
  onClose: () => void;
}) {
  const [os, setOs] = useState<Os>(() => detectOs());
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState("pending");
    const mac = os === "mac";

  useEffect(() => {
    if (step !== 2) return;
    const poll = () =>
      (accountId
        ? apiRequest<{ status: string }>(`/accounts/${accountId}/status`).then((r) => setStatus(r.status))
        : apiRequest<unknown[]>("/devices/detected").then((r) => setStatus(r.length > 0 ? "connected" : "pending"))
      ).catch(() => undefined);
    poll();
    const id = window.setInterval(poll, 4000);
    return () => window.clearInterval(id);
  }, [step, accountId]);

  const live = status === "connected";
  const installer = `${webhookUrl}/installer/${os}`;
  const steps: { title: string; body: React.ReactNode }[] = [
    {
      title: "Choose your device",
      body: (
        <>
          <p>We detected <strong>{mac ? "a Mac" : "Windows"}</strong>. Pick the computer where your MetaTrader 5 app is installed.</p>
          <div className="wiz-os">
            <button type="button" className={mac ? "active" : ""} onClick={() => setOs("mac")}><span>🍎</span>Mac</button>
            <button type="button" className={!mac ? "active" : ""} onClick={() => setOs("windows")}><span>🖥️</span>Windows PC</button>
          </div>
          <p className="wiz-note">Install the desktop MetaTrader 5 app and sign in to <strong>{accountName}</strong> once. TradeIQ does the rest automatically.</p>
        </>
      ),
    },
    {
      title: "Download and run the TradeIQ setup",
      body: (
        <>
          <p>One file installs the connector, links it to <strong>{accountName}</strong> and starts the background sync. It only reads data and cannot place trades.</p>
          <a className="button button-primary" href={installer} download>{mac ? "Download TradeIQ-Setup.command" : "Download TradeIQ-Setup.bat"}</a>
          <ol>
            {mac ? (
              <>
                <li>Open <strong>Terminal</strong> and run <code>bash ~/Downloads/TradeIQ-Setup.command</code> (or right-click the file → <strong>Open</strong> and confirm the macOS prompt).</li>
                <li>Allow the permission prompts: closing and reopening MetaTrader 5, and running the sync service in the background.</li>
              </>
            ) : (
              <>
                <li>Double-click <strong>TradeIQ-Setup.bat</strong>. If Windows SmartScreen appears choose <strong>More info → Run anyway</strong>.</li>
                <li>Allow the permission prompts: closing and reopening MetaTrader 5, and the background sync task.</li>
              </>
            )}
            <li>Wait for <em>Done</em>. MetaTrader 5 reopens with TradeIQ attached.</li>
          </ol>
          <p className="wiz-note">This file is personal to your account. Don&apos;t share it.</p>
        </>
      ),
    },
    {
      title: "Confirm you are live",
      body: (
        <div className="wiz-live">
          <span className={`wiz-dot ${live ? "ok" : ""}`} />
          <div>
            <strong>{live ? "Connected. Your account is live." : "Waiting for the first data from MT5…"}</strong>
            <p>{live
              ? "Your balance, open positions and trade history are now importing into TradeIQ."
              : "This updates automatically (usually within a minute). If nothing arrives, open the Experts tab in MT5's Toolbox: run the setup file again and make sure MetaTrader 5 is signed in to this account."}</p>
          </div>
        </div>
      ),
    },
  ];

  const last = step === steps.length - 1;
  return (
    <div className="modal-backdrop">
      <section className="capture-modal wiz" role="dialog" aria-modal="true" aria-labelledby="wiz-title">
        <div className="wiz-head">
          <div className="wiz-progress">{steps.map((_, i) => <i key={i} className={i <= step ? "on" : ""} />)}</div>
          <span className="eyebrow">EA SETUP · STEP {step + 1} OF {steps.length}</span>
          <h2 id="wiz-title">{steps[step].title}</h2>
        </div>
        <div className="wiz-body">{steps[step].body}</div>
        <div className="modal-actions">
          {step > 0 ? <button type="button" className="button button-quiet" onClick={() => setStep(step - 1)}>Back</button> : <button type="button" className="button button-quiet" onClick={onClose}>Close</button>}
          {last
            ? <button type="button" className="button button-primary" onClick={onClose}>{live ? "Done" : "Finish later"}</button>
            : <button type="button" className="button button-primary" onClick={() => setStep(step + 1)}>Next</button>}
        </div>
      </section>
    </div>
  );
}
