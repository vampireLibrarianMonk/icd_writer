import { usePanelStore, type PanelVisibility } from "../../store/panelStore";

export function PanelManager() {
  const visibility = usePanelStore((s) => s.visibility);
  const toggleVisibility = usePanelStore((s) => s.toggleVisibility);
  const setPanelManagerOpen = usePanelStore((s) => s.setPanelManagerOpen);

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1000,
      }}
      onClick={() => setPanelManagerOpen(false)}
    >
      <div
        style={{
          position: "absolute",
          right: 50,
          bottom: 50,
          width: 260,
          background: "var(--bg-primary, #1e1e1e)",
          border: "1px solid var(--border, #444)",
          borderRadius: 8,
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
          padding: "12px 0",
          fontSize: 12,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "0 14px 8px",
          borderBottom: "1px solid var(--border, #333)",
          marginBottom: 8,
        }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary, #eee)" }}>
            Panel Visibility
          </span>
          <button
            onClick={() => setPanelManagerOpen(false)}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 16,
              color: "var(--text-secondary, #888)",
              lineHeight: 1,
            }}
            aria-label="Close panel manager"
          >
            ✕
          </button>
        </div>

        {/* Groups */}
        <PanelGroup title="DISCOVER">
          <PanelToggle label="Search" panel="search" checked={visibility.search} onToggle={toggleVisibility} />
          <PanelToggle label="TBD Dashboard" panel="tbd" checked={visibility.tbd} onToggle={toggleVisibility} />
        </PanelGroup>

        <PanelGroup title="SOURCES">
          <PanelToggle label="Local Documents" panel="local" checked={visibility.local} onToggle={toggleVisibility} />
          <PanelToggle label="Confluence" panel="confluence" checked={visibility.confluence} onToggle={toggleVisibility} hint="not configured" />
          <PanelToggle label="SharePoint" panel="sharepoint" checked={visibility.sharepoint} onToggle={toggleVisibility} hint="not configured" />
          <PanelToggle label="Lineage" panel="lineage" checked={visibility.lineage} onToggle={toggleVisibility} />
        </PanelGroup>

        <PanelGroup title="COMPARE">
          <PanelToggle label="Revision Compare" panel="compare" checked={visibility.compare} onToggle={toggleVisibility} />
        </PanelGroup>

        <PanelGroup title="SESSION">
          <PanelToggle label="Session Timeline" panel="timeline" checked={visibility.timeline} onToggle={toggleVisibility} />
          <PanelToggle label="Cost Tracking" panel="costs" checked={visibility.costs} onToggle={toggleVisibility} />
          <PanelToggle label="Credentials" panel="credentials" checked={visibility.credentials} onToggle={toggleVisibility} />
        </PanelGroup>
      </div>
    </div>
  );
}

function PanelGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{
        padding: "4px 14px",
        fontSize: 10,
        fontWeight: 700,
        color: "var(--text-tertiary, #666)",
        letterSpacing: "0.5px",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function PanelToggle({
  label,
  panel,
  checked,
  onToggle,
  hint,
}: {
  label: string;
  panel: keyof PanelVisibility;
  checked: boolean;
  onToggle: (panel: keyof PanelVisibility) => void;
  hint?: string;
}) {
  return (
    <label style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "4px 14px",
      cursor: "pointer",
      color: "var(--text-primary, #ddd)",
    }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover, #2a2a2a)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={() => onToggle(panel)}
        style={{ margin: 0, cursor: "pointer" }}
      />
      <span>{label}</span>
      {hint && !checked && (
        <span style={{ fontSize: 10, color: "var(--text-tertiary, #666)", marginLeft: "auto" }}>
          ({hint})
        </span>
      )}
    </label>
  );
}
