import { Toolbar } from "./components/Toolbar";
import { DocumentView } from "./components/DocumentView";
import { UnifiedEditor } from "./components/UnifiedEditor";
import { StatusBar } from "./components/StatusBar";
import { useState, useCallback } from "react";

function App() {
  const [panelWidth, setPanelWidth] = useState(380);
  const [dragging, setDragging] = useState(false);

  const handleMouseDown = () => setDragging(true);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      const newWidth = window.innerWidth - e.clientX;
      setPanelWidth(Math.max(250, Math.min(700, newWidth)));
    },
    [dragging]
  );

  const handleMouseUp = () => setDragging(false);

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
        <UnifiedEditor width={panelWidth} />
      </div>
      <StatusBar />
    </div>
  );
}

export default App;
