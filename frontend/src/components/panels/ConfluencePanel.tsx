import { useState, useEffect } from "react";
import { connectorsApi, type RemoteSpace, type RemotePage, type RemoteFile } from "../../api/connectors";

type View = "setup" | "spaces" | "pages" | "files";

export function ConfluencePanel() {
  const [view, setView] = useState<View>("setup");
  const [_connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Setup form
  const [url, setUrl] = useState("http://localhost:8090");
  const [token, setToken] = useState("dev-token");

  // Browse state
  const [spaces, setSpaces] = useState<RemoteSpace[]>([]);
  const [pages, setPages] = useState<RemotePage[]>([]);
  const [files, setFiles] = useState<RemoteFile[]>([]);
  const [currentSpace, setCurrentSpace] = useState<RemoteSpace | null>(null);
  const [currentPage, setCurrentPage] = useState<RemotePage | null>(null);

  // Check if already configured on mount
  useEffect(() => {
    connectorsApi.listConnectors().then((data) => {
      const conf = data.connectors?.find((c) => c.type === "confluence");
      if (conf?.configured) {
        setConnected(true);
        setView("spaces");
        connectorsApi.listSpaces("confluence").then((spaceData) => {
          setSpaces(spaceData.spaces || []);
        }).catch(() => {});
      }
    }).catch(() => {});
  }, []);

  const handleConnect = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await connectorsApi.configure("confluence", url, token);
      if (result.connected) {
        setConnected(true);
        setView("spaces");
        await loadSpaces();
      } else {
        setError("Connection failed — check URL and token.");
      }
    } catch (e: any) {
      setError(e.message || "Connection error");
    } finally {
      setLoading(false);
    }
  };

  const loadSpaces = async () => {
    setLoading(true);
    try {
      const data = await connectorsApi.listSpaces("confluence");
      setSpaces(data.spaces);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadPages = async (space: RemoteSpace) => {
    setCurrentSpace(space);
    setLoading(true);
    try {
      const data = await connectorsApi.listPages("confluence", space.id);
      setPages(data.pages);
      setView("pages");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async (page: RemotePage) => {
    setCurrentPage(page);
    setLoading(true);
    try {
      const data = await connectorsApi.listFiles("confluence", page.id);
      setFiles(data.files);
      setView("files");
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
        <h3 style={{ margin: 0, fontSize: 14 }}>Connect to Confluence</h3>
        <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
          Enter your Confluence URL and access token to browse and import documents.
        </p>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          URL
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://yoursite.atlassian.net"
            style={inputStyle}
          />
        </label>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          Access Token
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Personal access token"
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

  // ─── Spaces View ────────────────────────────────────────────────

  if (view === "spaces") {
    return (
      <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
        <Header title="Confluence Spaces" onBack={undefined} />
        {loading && <LoadingDots />}
        {spaces.map((space) => (
          <ItemRow
            key={space.id}
            icon="📚"
            title={space.name}
            subtitle={space.description}
            onClick={() => loadPages(space)}
          />
        ))}
        {!loading && spaces.length === 0 && (
          <Empty message="No spaces found" />
        )}
      </div>
    );
  }

  // ─── Pages View ─────────────────────────────────────────────────

  if (view === "pages") {
    return (
      <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
        <Header title={currentSpace?.name || "Pages"} onBack={() => setView("spaces")} />
        {loading && <LoadingDots />}
        {pages.map((page) => (
          <ItemRow
            key={page.id}
            icon="📄"
            title={page.title}
            subtitle={`v${page.version} · ${page.author}`}
            onClick={() => loadFiles(page)}
          />
        ))}
        {!loading && pages.length === 0 && (
          <Empty message="No pages in this space" />
        )}
      </div>
    );
  }

  // ─── Files View ─────────────────────────────────────────────────

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <Header title={currentPage?.title || "Attachments"} onBack={() => setView("pages")} />
      {loading && <LoadingDots />}
      {files.map((file) => (
        <ItemRow
          key={file.id}
          icon={getFileIcon(file.filename)}
          title={file.filename}
          subtitle={formatBytes(file.size_bytes)}
          onClick={() => {}}
        />
      ))}
      {!loading && files.length === 0 && (
        <Empty message="No attachments on this page" />
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
  if (!filename) return "📎";
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

function formatBytes(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

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
