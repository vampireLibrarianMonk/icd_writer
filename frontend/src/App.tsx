import { Toolbar } from "./components/Toolbar";
import { DocumentView } from "./components/DocumentView";
import { StatusBar } from "./components/StatusBar";
import { UploadProgressPanel } from "./components/UploadProgressPanel";
import { HelpModal } from "./components/HelpModal";
import { ActivityRail } from "./components/panels/ActivityRail";
import { PanelContainer } from "./components/panels/PanelContainer";
import { PanelManager } from "./components/panels/PanelManager";
import { useState, useCallback, useEffect, useRef } from "react";
import { useEditorStore } from "./store/editorStore";
import { usePanelStore } from "./store/panelStore";
import type { IngestStatus } from "./api/client";

function App() {
  const [panelWidth, setPanelWidth] = useState(420);
  const [dragging, setDragging] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus | null>(null);
  const [helpTab, setHelpTab] = useState<"how-it-works" | "evaluation" | "about" | null>(null);
  const suppressPanelSwitchRef = useRef(false);

  const panelManagerOpen = usePanelStore((s) => s.panelManagerOpen);
  const setActiveGroup = usePanelStore((s) => s.setActiveGroup);

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

  // Auto-switch to editor group when user clicks an element in DocumentView
  // BUT not when navigating from TBD dashboard
  useEffect(() => {
    const handleTbdNavigate = () => {
      // TBD navigation will trigger element-selected — suppress the panel switch
      suppressPanelSwitchRef.current = true;
      // Reset after a generous delay
      setTimeout(() => { suppressPanelSwitchRef.current = false; }, 3000);
    };

    const handleElementSelected = () => {
      if (suppressPanelSwitchRef.current) {
        return; // Don't switch panel — stay on current tab (TBD)
      }
      setActiveGroup("editor");
    };

    const handleTableZoneSelected = () => {
      if (suppressPanelSwitchRef.current) return;
      setActiveGroup("editor");
    };

    const handleRelatedVersions = () => {
      if (suppressPanelSwitchRef.current) return;
      setActiveGroup("compare");
    };

    window.addEventListener("navigate-to-tbd", handleTbdNavigate);
    window.addEventListener("element-selected", handleElementSelected);
    window.addEventListener("table-zone-selected", handleTableZoneSelected);
    window.addEventListener("related-versions-found", handleRelatedVersions);
    return () => {
      window.removeEventListener("navigate-to-tbd", handleTbdNavigate);
      window.removeEventListener("element-selected", handleElementSelected);
      window.removeEventListener("table-zone-selected", handleTableZoneSelected);
      window.removeEventListener("related-versions-found", handleRelatedVersions);
    };
  }, [setActiveGroup]);

  const handleFileUpload = (file: File) => {
    setUploadFile(file);
    setIngestStatus(null);
  };

  const handleIngestProgress = (status: IngestStatus) => {
    setIngestStatus(status);
  };

  const handleIngestComplete = async (status: IngestStatus) => {
    setIngestStatus(status);
    setUploadFile(null);

    // Auto-open the document on success
    if (status.status === "done" && status.pdf_path) {
      await useEditorStore.getState().loadDocument(status.pdf_path);
    }
  };

  const handleUploadDismiss = () => {
    setUploadFile(null);
  };

  // Clear the status bar summary after 10 seconds
  useEffect(() => {
    if (ingestStatus?.done) {
      const timer = setTimeout(() => setIngestStatus(null), 15000);
      return () => clearTimeout(timer);
    }
  }, [ingestStatus?.done]);

  return (
    <div
      style={{ display: "flex", flexDirection: "column", height: "100vh" }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <Toolbar onFileUpload={handleFileUpload} onShowHelp={(tab) => setHelpTab(tab || "how-it-works")} />
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
        {/* Right panel: Activity Rail + Panel Content */}
        <div style={{ width: panelWidth, display: "flex", overflow: "hidden" }}>
          <PanelContainer width={panelWidth - 40} />
          <ActivityRail />
        </div>
      </div>
      <StatusBar ingestStatus={ingestStatus} />
      {/* Upload progress modal */}
      {uploadFile && (
        <UploadProgressPanel
          file={uploadFile}
          onProgress={handleIngestProgress}
          onComplete={handleIngestComplete}
          onDismiss={handleUploadDismiss}
        />
      )}
      {/* Help modal */}
      {helpTab && (
        <HelpModal initialTab={helpTab} onClose={() => setHelpTab(null)} />
      )}
      {/* Panel Manager popover */}
      {panelManagerOpen && <PanelManager />}
    </div>
  );
}

export default App;
