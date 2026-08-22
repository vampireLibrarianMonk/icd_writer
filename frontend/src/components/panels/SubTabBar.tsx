interface SubTabBarProps {
  tabs: { id: string; label: string }[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

export function SubTabBar({ tabs, activeTab, onTabChange }: SubTabBarProps) {
  if (!tabs || tabs.length <= 1) return null;

  return (
    <div style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 4,
      padding: "6px 10px",
      borderBottom: "1px solid var(--border, #333)",
      background: "var(--bg-secondary, #252525)",
    }}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          style={{
            padding: "4px 10px",
            border: "none",
            borderRadius: 12,
            background: activeTab === tab.id
              ? "var(--accent, #1976d2)"
              : "var(--bg-tertiary, #1e1e1e)",
            color: activeTab === tab.id
              ? "#fff"
              : "var(--text-secondary, #aaa)",
            cursor: "pointer",
            fontSize: 11,
            fontWeight: activeTab === tab.id ? 600 : 400,
            transition: "all 0.15s",
          }}
          onMouseEnter={(e) => {
            if (activeTab !== tab.id) {
              (e.currentTarget.style.background = "var(--bg-hover, #2a2a2a)");
            }
          }}
          onMouseLeave={(e) => {
            if (activeTab !== tab.id) {
              (e.currentTarget.style.background = "var(--bg-tertiary, #1e1e1e)");
            }
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
