import { usePanelStore, type PanelVisibility } from "../../store/panelStore";
import { SubTabBar } from "./SubTabBar";
import { UnifiedEditor } from "../UnifiedEditor";
import { SearchPanel } from "../SearchPanel";
import { TBDDashboard } from "../TBDDashboardPanel";
import { DocumentManagerPanel } from "../DocumentManagerPanel";
import { RevisionComparePanel } from "../RevisionComparePanel";
import { SessionPanel } from "../SessionPanel";
import { ConfluencePanel } from "./ConfluencePanel";
import { SharePointPanel } from "./SharePointPanel";

interface PanelContainerProps {
  width: number;
}

export function PanelContainer({ width }: PanelContainerProps) {
  const activeGroup = usePanelStore((s) => s.activeGroup);
  const subTabs = usePanelStore((s) => s.subTabs);
  const visibility = usePanelStore((s) => s.visibility);
  const setSubTab = usePanelStore((s) => s.setSubTab);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Sub-tab bar (only for groups with multiple panels) */}
      {activeGroup === "discover" && (
        <SubTabBar
          tabs={getDiscoverTabs(visibility)}
          activeTab={subTabs.discover}
          onTabChange={(id) => setSubTab("discover", id as any)}
        />
      )}
      {activeGroup === "sources" && (
        <SubTabBar
          tabs={getSourcesTabs(visibility)}
          activeTab={subTabs.sources}
          onTabChange={(id) => setSubTab("sources", id as any)}
        />
      )}
      {activeGroup === "session" && (
        <SubTabBar
          tabs={getSessionTabs(visibility)}
          activeTab={subTabs.session}
          onTabChange={(id) => setSubTab("session", id as any)}
        />
      )}

      {/* Panel content */}
      <div style={{ flex: 1, overflow: "hidden" }}>
        {activeGroup === "editor" && <UnifiedEditor width={width} />}

        {activeGroup === "discover" && subTabs.discover === "search" && <SearchPanel />}
        {activeGroup === "discover" && subTabs.discover === "tbd" && <TBDDashboard />}

        {activeGroup === "sources" && subTabs.sources === "local" && <DocumentManagerPanel />}
        {activeGroup === "sources" && subTabs.sources === "confluence" && <ConfluencePanel />}
        {activeGroup === "sources" && subTabs.sources === "sharepoint" && <SharePointPanel />}
        {activeGroup === "sources" && subTabs.sources === "lineage" && <PlaceholderPanel name="Lineage" />}

        {activeGroup === "compare" && <RevisionComparePanel />}

        {activeGroup === "session" && subTabs.session === "timeline" && <SessionPanel />}
        {activeGroup === "session" && subTabs.session === "costs" && <PlaceholderPanel name="Cost Tracking" />}
      </div>
    </div>
  );
}

// ─── Tab helpers (filter by visibility) ───────────────────────────────

function getDiscoverTabs(v: PanelVisibility) {
  const tabs: { id: string; label: string }[] = [];
  if (v.search) tabs.push({ id: "search", label: "Search" });
  if (v.tbd) tabs.push({ id: "tbd", label: "TBD Dashboard" });
  return tabs;
}

function getSourcesTabs(v: PanelVisibility) {
  const tabs: { id: string; label: string }[] = [];
  if (v.local) tabs.push({ id: "local", label: "Local" });
  if (v.confluence) tabs.push({ id: "confluence", label: "Confluence" });
  if (v.sharepoint) tabs.push({ id: "sharepoint", label: "SharePoint" });
  if (v.lineage) tabs.push({ id: "lineage", label: "Lineage" });
  return tabs;
}

function getSessionTabs(v: PanelVisibility) {
  const tabs: { id: string; label: string }[] = [];
  if (v.timeline) tabs.push({ id: "timeline", label: "Timeline" });
  if (v.costs) tabs.push({ id: "costs", label: "Costs" });
  return tabs;
}

// ─── Placeholder for future panels ───────────────────────────────────

function PlaceholderPanel({ name }: { name: string }) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      padding: 32,
      textAlign: "center",
      color: "var(--text-secondary, #888)",
    }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>
        {name === "Confluence" ? "🔗" : name === "SharePoint" ? "☁️" : name === "Lineage" ? "🔀" : "📊"}
      </div>
      <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8 }}>
        {name}
      </div>
      <div style={{ fontSize: 12, maxWidth: 240 }}>
        {name === "Confluence" || name === "SharePoint"
          ? `${name} connector is not configured. Connect via Settings to browse and import documents.`
          : name === "Lineage"
          ? "Open a document to see its source lineage — the upstream documents that feed each section."
          : "Coming soon."
        }
      </div>
    </div>
  );
}
