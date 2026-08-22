import { useState, useEffect } from "react";
import { credentialsApi, type StoredCredential, type CreateCredentialRequest } from "../../api/credentials";

type View = "list" | "add" | "edit";

export function CredentialsPanel() {
  const [view, setView] = useState<View>("list");
  const [credentials, setCredentials] = useState<StoredCredential[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const loadCredentials = async () => {
    setLoading(true);
    try {
      const data = await credentialsApi.list();
      setCredentials(data.credentials);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadCredentials(); }, []);

  const handleDelete = async (id: string) => {
    await credentialsApi.delete(id);
    await loadCredentials();
  };

  const handleTest = async (id: string) => {
    const result = await credentialsApi.test(id);
    // Reload to show updated test result
    await loadCredentials();
    return result;
  };

  // ─── List View ──────────────────────────────────────────────────

  if (view === "list") {
    return (
      <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Stored Credentials</span>
          <button onClick={() => setView("add")} style={btnPrimary}>+ Add</button>
        </div>

        {loading && <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>Loading...</div>}

        {credentials.length === 0 && !loading && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)", textAlign: "center", padding: 24 }}>
            No credentials stored. Click "+ Add" to save connector credentials.
          </div>
        )}

        {credentials.map((cred) => (
          <CredentialCard
            key={cred.id}
            credential={cred}
            onEdit={() => { setEditingId(cred.id); setView("edit"); }}
            onDelete={() => handleDelete(cred.id)}
            onTest={() => handleTest(cred.id)}
          />
        ))}
      </div>
    );
  }

  // ─── Add / Edit View ────────────────────────────────────────────

  return (
    <CredentialForm
      mode={view === "add" ? "add" : "edit"}
      editId={editingId}
      credentials={credentials}
      onSave={async () => { await loadCredentials(); setView("list"); }}
      onCancel={() => setView("list")}
    />
  );
}

// ─── Credential Card ──────────────────────────────────────────────────

function CredentialCard({ credential, onEdit, onDelete, onTest }: {
  credential: StoredCredential;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
}) {
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    await onTest();
    setTesting(false);
  };

  return (
    <div style={{
      border: "1px solid var(--border, #333)",
      borderRadius: 6,
      padding: 10,
      marginBottom: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600 }}>{credential.name}</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
            {serviceIcon(credential.service)} {credential.service} · {credential.url}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-tertiary, #666)", marginTop: 2 }}>
            Token: {credential.token_preview}
          </div>
        </div>
        <StatusBadge result={credential.last_test_result} />
      </div>

      {credential.notes && (
        <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 4, fontStyle: "italic" }}>
          {credential.notes}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button onClick={handleTest} disabled={testing} style={btnSmall}>
          {testing ? "Testing..." : "Test"}
        </button>
        <button onClick={onEdit} style={btnSmall}>Edit</button>
        <button onClick={onDelete} style={{ ...btnSmall, color: "#f44336" }}>Delete</button>
      </div>
    </div>
  );
}

// ─── Add/Edit Form ────────────────────────────────────────────────────

function CredentialForm({ mode, editId, credentials, onSave, onCancel }: {
  mode: "add" | "edit";
  editId: string | null;
  credentials: StoredCredential[];
  onSave: () => Promise<void>;
  onCancel: () => void;
}) {
  const existing = mode === "edit" ? credentials.find((c) => c.id === editId) : null;

  const [service, setService] = useState(existing?.service || "confluence");
  const [name, setName] = useState(existing?.name || "");
  const [url, setUrl] = useState(existing?.url || "");
  const [token, setToken] = useState("");
  const [siteId, setSiteId] = useState(existing?.site_id || "");
  const [notes, setNotes] = useState(existing?.notes || "");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      if (mode === "add") {
        const req: CreateCredentialRequest = { service, name, url, token, site_id: siteId, notes };
        await credentialsApi.create(req);
      } else if (editId) {
        const fields: Partial<CreateCredentialRequest> = { name, url, site_id: siteId, notes };
        if (token) fields.token = token; // Only update token if provided
        await credentialsApi.update(editId, fields);
      }
      await onSave();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {mode === "add" ? "Add Credential" : "Edit Credential"}
        </span>
        <button onClick={onCancel} style={btnSmall}>Cancel</button>
      </div>

      <label style={labelStyle}>
        Service
        <select value={service} onChange={(e) => setService(e.target.value)} style={inputStyle}>
          <option value="confluence">Confluence</option>
          <option value="sharepoint">SharePoint</option>
          <option value="other">Other</option>
        </select>
      </label>

      <label style={labelStyle}>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="e.g., HESSI Confluence, JSC SharePoint" style={inputStyle} />
      </label>

      <label style={labelStyle}>
        URL
        <input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="http://localhost:8090" style={inputStyle} />
      </label>

      <label style={labelStyle}>
        Token {mode === "edit" && <span style={{ fontSize: 9, color: "var(--text-tertiary)" }}>(leave blank to keep existing)</span>}
        <input type="password" value={token} onChange={(e) => setToken(e.target.value)}
          placeholder={mode === "edit" ? "••••••••" : "Access token or Bearer token"} style={inputStyle} />
      </label>

      {service === "sharepoint" && (
        <label style={labelStyle}>
          Site ID
          <input value={siteId} onChange={(e) => setSiteId(e.target.value)}
            placeholder="site-engineering" style={inputStyle} />
        </label>
      )}

      <label style={labelStyle}>
        Notes (optional)
        <input value={notes} onChange={(e) => setNotes(e.target.value)}
          placeholder="e.g., Expires 2026-12-31" style={inputStyle} />
      </label>

      <button onClick={handleSubmit} disabled={saving || !name || !url || (mode === "add" && !token)}
        style={btnPrimary}>
        {saving ? "Saving..." : mode === "add" ? "Save Credential" : "Update"}
      </button>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────

function StatusBadge({ result }: { result: string | null }) {
  if (!result) return null;
  const isSuccess = result === "success";
  return (
    <span style={{
      fontSize: 9,
      padding: "2px 6px",
      borderRadius: 3,
      background: isSuccess ? "#1b5e20" : "#b71c1c",
      color: "#fff",
      fontWeight: 600,
    }}>
      {isSuccess ? "OK" : "FAIL"}
    </span>
  );
}

function serviceIcon(service: string): string {
  switch (service) {
    case "confluence": return "🔗";
    case "sharepoint": return "☁️";
    default: return "🔑";
  }
}

// ─── Styles ───────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 3,
  padding: "6px 10px",
  borderRadius: 4,
  border: "1px solid var(--border, #444)",
  background: "var(--bg-tertiary, #1e1e1e)",
  color: "var(--text-primary, #eee)",
  fontSize: 12,
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--text-secondary)",
};

const btnPrimary: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 5,
  border: "none",
  background: "var(--accent, #1976d2)",
  color: "#fff",
  fontSize: 11,
  fontWeight: 500,
  cursor: "pointer",
};

const btnSmall: React.CSSProperties = {
  padding: "3px 8px",
  borderRadius: 4,
  border: "1px solid var(--border, #444)",
  background: "transparent",
  color: "var(--text-primary, #ddd)",
  fontSize: 10,
  cursor: "pointer",
};
