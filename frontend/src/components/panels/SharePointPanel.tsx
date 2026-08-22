import { useState, useEffect } from "react";
import { connectorsApi, type RemoteSpace, type RemotePage } from "../../api/connectors";

type View = "setup" | "drives" | "items";

export function SharePointPanel() {
  const [view, setView] = useState<View>("setup");
  const [_connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Setup form
  const [url, setUrl] = useState("http://localhost:8091");
  const [token, setToken] = useState("dev-token");
  const [siteId, setSiteId] = useState("site-engineering");

  // Browse state
  const [drives, setDrives] = useState<RemoteSpace[]>([]);
  const [items, setItems] = useState<RemotePage[]>([]);
  const [currentDrive, setCurrentDrive] = useState<RemoteSpace | null>(null);

  // Check if already configured on mount
  useEffect(() => {
    connectorsApi.listConnectors().then((data) => {
      const sp = data.connectors.find((c) => c.type === "sharepoint");
      if (sp?.configured) {
        setConnected(true);
        setView("drives");
        loadDrives();
      }
    }).catch(() => {});
  }, []);

  const handleConnect = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await connectorsApi.configure("sharepoint", url, token, siteId);
      if (result.connected) {
        setConnected(true);
        setView("drives");
        await loadDrives();
      } else {
        setError("Connection failed — check URL, token, and site ID.");
      }
    } catch (e: any) {
      setError(e.message || "Connection error");
    } finally {
      setLoading(false);
    }
  };

  const loadDrives = async () => {
    setLoading(true);
    try {
      const data = await connectorsApi.listSpaces("sharepoint");
      setDrives(data.spaces);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadItems = async (drive: RemoteSpace) => {
    setCurrentDrive(drive);
    setLoading(true);
    try {
      const data = await connectorsApi.listPages("sharepoint", drive.id);
      setItems(data.pages);
      setView("items");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ─── Setup View ─────────────────────────────────────────────────

  if (view === "setup") {
    return (
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>Connect to SharePoint</h3>
        <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
          Enter your Graph API endpoint and bearer token to browse document libraries.
        </p>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          API URL
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://graph.microsoft.com/v1.0"
            style={inputStyle}
          />
        </label>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          Bearer Token
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="OAuth2 access token"
            style={inputStyle}
          />
        </label>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          Site ID
          <input
            type="text"
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            placeholder="site-engineering"
            style={inputStyle}
          />
        </label>
        {error && <div style={{ color: "#f44336", fontSize: 11 }}>{error}</div>}
        <button onClick={handleConnect} disabled={loading || !url || !token} style={btnStyle}>
          {loading ? "Connecting..." : "Connect"}
        </button>
      </div>
    );
  }

  // ─── Drives View ────────────────────────────────────────────────

  if (view === "drives") {
    return (
      <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
        <Header title="Document Libraries" onBack={undefined} />
        {loading && <LoadingDots />}
        {drives.map((drive) => (
          <ItemRow
            key={drive.id}
            icon="📂"
            title={drive.name}
            subtitle={drive.description}
            onClick={() => loadItems(drive)}
          />
        ))}
        {!loading && drives.length === 0 && (
          <Empty message="No document libraries found" />
        )}
      </div>
    );
  }

  // ─── Items View ─────────────────────────────────────────────────

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <Header title={currentDrive?.name || "Files"} onBack={() => setView("drives")} />
      {loading && <LoadingDots />}
      {items.map((item) => (
        <ItemRow
          key={item.id}
          icon={item.has_children ? "📁" : getFileIcon(item.title)}
          title={item.title}
          subtitle={item.modified_at ? formatDate(item.modified_at) + (item.author ? ` · ${item.author}` : "") : ""}
          onClick={() => {}}
        />
      ))}
      {!loading && items.length === 0 && (
        <Empty message="No files in this library" />
      )}
    </div>
  );
}

// ─── Shared sub-components ────────────────────────────────────────────

function Header({ title, onBack }: { title: string; onBack: (() => void) | undefined }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      {onBack && (
        <button onClick={onBack} style={{ ...btnStyle, padding: "2px 8px", fontSize: 11 }}>
          ← Back
        </button>
      )}
      <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
    </div>
  );
}

function ItemRow({ icon, title, subtitle, onClick }: {
  icon: string; title: string; subtitle: string; onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "8px 10px",
        borderRadius: 6,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 2,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover, #2a2a2a)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <span style={{ fontSize: 16 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingDots() {
  return <div style={{ fontSize: 12, color: "var(--text-secondary)", padding: 8 }}>Loading...</div>;
}

function Empty({ message }: { message: string }) {
  return <div style={{ fontSize: 12, color: "var(--text-secondary)", padding: 16, textAlign: "center" }}>{message}</div>;
}

function getFileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "pdf": return "📕";
    case "docx": case "doc": return "📘";
    case "pptx": case "ppt": return "📙";
    case "xlsx": case "xls": return "📗";
    case "png": case "jpg": case "jpeg": case "tiff": return "🖼️";
    default: return "📎";
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

// formatBytes available for future use when showing file sizes in items view
// function formatBytes(bytes: number): string {
//   if (!bytes) return "";
//   if (bytes < 1024) return `${bytes} B`;
//   if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
//   return `${(bytes / 1048576).toFixed(1)} MB`;
// }

// ─── Styles ───────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 4,
  padding: "6px 10px",
  borderRadius: 4,
  border: "1px solid var(--border, #444)",
  background: "var(--bg-tertiary, #1e1e1e)",
  color: "var(--text-primary, #eee)",
  fontSize: 12,
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "none",
  background: "var(--accent, #1976d2)",
  color: "#fff",
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
};
