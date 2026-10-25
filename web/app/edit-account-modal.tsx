"use client";

import { useState, type FormEvent } from "react";

type EditableAccount = { id: string; name: string; server: string; loginId: string };

export function EditAccountModal<T extends EditableAccount>({
  account,
  onClose,
  onSave,
}: {
  account: T;
  onClose: () => void;
  onSave: (account: T, name: string) => Promise<void>;
}) {
  const [name, setName] = useState(account.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Enter a name for this account.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSave(account, trimmed);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save this account.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <form className="capture-modal account-setup-modal" onSubmit={(event) => void submit(event)} role="dialog" aria-modal="true" aria-labelledby="edit-account-title">
        <div className="modal-heading"><div><span className="eyebrow">EDIT ACCOUNT</span><h2 id="edit-account-title">Edit account</h2></div></div>
        <label>Account name<input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} autoFocus /></label>
        <p className="wiz-note">Login {account.loginId || "—"} · {account.server || "No server"} are fixed once connected. To change them, delete the account and add it again.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="button button-quiet" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="button button-primary" disabled={busy}>{busy ? "Saving..." : "Save changes"}</button>
        </div>
      </form>
    </div>
  );
}
