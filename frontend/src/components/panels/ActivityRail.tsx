import { usePanelStore, type PanelGroup } from "../../store/panelStore";

interface RailItem {
  id: PanelGroup;
  icon: string;
  label: string;
}

const RAIL_ITEMS: RailItem[] = [
  { id: "editor", icon: "✏️", label: "Editor" },
  { id: "discover", icon: "🔍", label: "Discover" },
  { id: "sources", icon: "📄", label: "Sources" },
  { id: "compare", icon: "🔀", label: "Compare" },
  { id: "session", icon: "📜", label: "Session" },
];

export function ActivityRail() {
  const activeGroup = usePanelStore((s) => s.activeGroup);
  const setActiveGroup = usePanelStore((s) => s.setActiveGroup);
  const setPanelManagerOpen = usePanelStore((s) => s.setPanelManagerOpen);

  return (
    <div style={{
      width: 40,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      background: "var(--bg-tertiary, #1e1e1e)",
      borderLeft: "1px solid var(--border, #333)",
      paddingTop: 8,
      gap: 2,
      flexShrink: 0,
    }}>
      {RAIL_ITEMS.map((item) => (
        <RailButton
          key={item.id}
          icon={item.icon}
          label={item.label}
          active={activeGroup === item.id}
          onClick={() => setActiveGroup(item.id)}
        />
      ))}

      {/* Spacer pushes settings to bottom */}
      <div style={{ flex: 1 }} />

      {/* Settings / Panel Manager */}
      <RailButton
        icon="⚙️"
        label="Panel Settings"
        active={false}
        onClick={() => setPanelManagerOpen(true)}
      />
      <div style={{ height: 8 }} />
    </div>
  );
}

function RailButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      style={{
        width: 34,
        height: 34,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        border: "none",
        borderRadius: 6,
        background: active ? "var(--bg-primary, #2d2d2d)" : "transparent",
        cursor: "pointer",
        fontSize: 16,
        position: "relative",
        transition: "background 0.15s",
        boxShadow: active ? "inset 2px 0 0 var(--accent, #1976d2)" : "none",
      }}
      onMouseEnter={(e) => {
        if (!active) (e.currentTarget.style.background = "var(--bg-hover, #2a2a2a)");
      }}
      onMouseLeave={(e) => {
        if (!active) (e.currentTarget.style.background = "transparent");
      }}
    >
      <span role="img" aria-hidden="true">{icon}</span>
    </button>
  );
}
