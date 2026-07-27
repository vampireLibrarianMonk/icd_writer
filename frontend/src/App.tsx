import { Toolbar } from "./components/Toolbar";
import { DocumentView } from "./components/DocumentView";
import { UnifiedEditor } from "./components/UnifiedEditor";
import { SearchPanel } from "./components/SearchPanel";
import { TBDDashboard } from "./components/TBDDashboardPanel";
import { VersionDiffPanel } from "./components/VersionDiffPanel";
import { StatusBar } from "./components/StatusBar";
import { useState, useCallback, useEffect } from "react";

type RightPanel = "editor" | "search" | "tbd" | "diff";

function App() {
  const [panelWidth, setPanelWidth] = useState(420);
  const [dragging, setDragging] = useState(false);
  const [activePanel, setActivePanel] = useState<RightPanel>("editor");

  const handleMouseDown = () => setDragging(true);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      const newWidth = window.innerWidth - e.clientX;
      setPanelWidth(Math.max(300, Math.min(800, newWidth)));
    },
    [dragging]
  );

  const handleMouseUp = () => setDragging(false);

  // Auto-switch to editor tab when user clicks an element in DocumentView
  useEffect(() => {
    const handleElementSelected = () => setActivePanel("editor");
    const handleTableZoneSelected = () => setActivePanel("editor");
    const handleRelatedVersions = () => setActivePanel("diff");
    window.addEventListener("element-selected", handleElementSelected);
    window.addEventListener("table-zone-selected", handleTableZoneSelected);
    window.addEventListener("related-versions-found", handleRelatedVersions);
    return () => {
      window.removeEventListener("element-selected", handleElementSelected);
      window.removeEventListener("table-zone-selected", handleTableZoneSelected);
      window.removeEventListener("related-versions-found", handleRelatedVersions);
    };
  }, []);

  return (
    <div
      style={{ display: "flex", flexDirection: "column", height: "100vh" }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <Toolbar />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <DocumentView />
        {/* Resizable divider */}
        <div
          onMouseDown={handleMouseDown}
          style={{
            width: "5px",
            cursor: "col-resize",
            background: dragging ? "#2196F3" : "#ddd",
            transition: "background 0.1s",
          }}
          onMouseEnter={(e) => {
            if (!dragging) (e.currentTarget as HTMLElement).style.background = "#bbb";
          }}
          onMouseLeave={(e) => {
            if (!dragging) (e.currentTarget as HTMLElement).style.background = "#ddd";
          }}
        />
        {/* Right panel with tabs */}
        <div style={{ width: panelWidth, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Panel tabs */}
          <div style={{
            display: "flex",
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-secondary)",
          }}>
            <PanelTab
              label="📝 Editor"
              active={activePanel === "editor"}
              onClick={() => setActivePanel("editor")}
            />
            <PanelTab
              label="🔍 Search"
              active={activePanel === "search"}
              onClick={() => setActivePanel("search")}
            />
            <PanelTab
              label="📋 TBDs"
              active={activePanel === "tbd"}
              onClick={() => setActivePanel("tbd")}
            />
            <PanelTab
              label="🔀 Diff"
              active={activePanel === "diff"}
              onClick={() => setActivePanel("diff")}
            />
          </div>
          {/* Panel content */}
          <div style={{ flex: 1, overflow: "hidden" }}>
            {activePanel === "editor" && <UnifiedEditor width={panelWidth} />}
            {activePanel === "search" && <SearchPanel />}
            {activePanel === "tbd" && <TBDDashboard />}
            {activePanel === "diff" && <VersionDiffPanel />}
          </div>
        </div>
      </div>
      <StatusBar />
    </div>
  );
}

function PanelTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "8px 14px",
        border: "none",
        borderBottom: active ? "2px solid var(--accent, #1976d2)" : "2px solid transparent",
        background: "transparent",
        cursor: "pointer",
        fontSize: "12px",
        fontWeight: active ? 600 : 400,
        color: active ? "var(--text-primary)" : "var(--text-secondary)",
        transition: "all 0.15s",
      }}
    >
      {label}
    </button>
  );
}

export default App;
