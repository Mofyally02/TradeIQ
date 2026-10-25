"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { apiRequest } from "./api";

type AuthMode = "login" | "register";

type User = {
  id: string;
  full_name: string | null;
  email: string;
  created_at: string;
};

export function AuthPanel({
  apiError,
  initialMode,
  onAuthenticated,
  onClose,
  onRetry,
}: {
  apiError: string;
  initialMode: AuthMode;
  onAuthenticated: (user: User) => void;
  onClose: () => void;
  onRetry: () => void;
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function switchMode(next: AuthMode) {
    setMode(next);
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (mode === "register") {
      if (fullName.trim().split(/\s+/).length < 2) return setError("Enter your first and last name.");
      if (password !== confirmPassword) return setError("Passwords do not match.");
      if (!accepted) return setError("Accept the Terms of Service and Privacy Policy to continue.");
    }
    setBusy(true);
    try {
      await apiRequest<User>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(mode === "register" ? { full_name: fullName.trim(), email, password } : { email, password }),
      });
      const user = await apiRequest<User>("/auth/me");
      onAuthenticated(user);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="auth-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section aria-labelledby="auth-title" aria-modal="true" className="auth-card" role="dialog">
        <button aria-label="Close sign in dialog" className="auth-close" onClick={onClose} type="button">×</button>
        <div className="auth-brand">trade<span>iq</span></div>
        <h1 id="auth-title">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p>
          {mode === "login"
            ? "Sign in to open your private TradeIQ journal."
            : "Start journaling your trades in minutes."}
        </p>
        <div className="auth-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => switchMode("login")}>Sign In</button>
          <button type="button" role="tab" aria-selected={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => switchMode("register")}>Create Account</button>
        </div>
        {apiError && <p className="form-error" role="alert">{apiError}</p>}
        <form onSubmit={submit}>
          {mode === "register" && (
            <label>
              Full name
              <input
                type="text"
                autoComplete="name"
                required
                minLength={2}
                maxLength={120}
                placeholder="First and last name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <span className="auth-password">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 12 : 1}
                maxLength={128}
                required
                placeholder="Your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button type="button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((value) => !value)}>{showPassword ? "Hide" : "Show"}</button>
            </span>
            {mode === "register" && <small>Use at least 12 characters.</small>}
          </label>
          {mode === "register" && (
            <label>
              Confirm password
              <span className="auth-password">
                <input
                  type={showConfirm ? "text" : "password"}
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                  placeholder="Re-enter your password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
                <button type="button" aria-label={showConfirm ? "Hide password" : "Show password"} onClick={() => setShowConfirm((value) => !value)}>{showConfirm ? "Hide" : "Show"}</button>
              </span>
            </label>
          )}
          {mode === "register" && (
            <label className="auth-terms">
              <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <span>I have read and agree to the <a href="#terms">Terms of Service</a> and <a href="#privacy">Privacy Policy</a>.</span>
            </label>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary auth-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in →" : "Create account →"}
          </button>
        </form>
        <div className="auth-divider"><span>or continue with</span></div>
        <button className="auth-google" type="button" disabled title="Google sign-in is not available yet">Continue with Google · coming soon</button>
        <div className="auth-badges"><span>Cloud-hosted</span><span>Encrypted</span><span>MT5</span></div>
        {apiError && <button className="auth-mode-toggle" type="button" onClick={onRetry}>Retry API connection</button>}
      </section>
    </div>
  );
}
