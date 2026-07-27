import { useEditorStore } from "../store/editorStore";
import { useEffect, useState } from "react";

interface Overlay {
  type: "header" | "footer" | "table_cell" | "text_block";
  label: string;
  text: string;
  id: string | null;
  bbox: { x0: number; y0: number; x1: number; y1: number };
}

export function DocumentView() {
  const { pageData, currentPage, totalPages, goToPage } = useEditorStore();
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  // Load all clickable overlays for this page (fine-grained spans)
  useEffect(() => {
    if (!totalPages || !currentPage) return;

    Promise.all([
      fetch(`http://localhost:8000/document/page/${currentPage}/elements`).then((r) => r.json()),
      fetch(`http://localhost:8000/document/page/${currentPage}/analysis`).then((r) => r.json()),
      fetch(`http://localhost:8000/document/page/${currentPage}/table`).then((r) => r.json()),
    ]).then(([elemData, analysis, tableData]) => {
      let elems = elemData.elements || [];
      // On TOC pages, only show header/footer overlays
      if (analysis.page_type === "table_of_contents") {
        elems = elems.filter((e: Overlay) => e.type === "header" || e.type === "footer");
      }
      // On table pages, show all elements — table editor is in the panel
      // but user can click any body element to edit it directly
      setOverlays(elems);
      setSelectedIdx(null);
    }).catch(() => setOverlays([]));
  }, [currentPage, totalPages]);

  const handleClick = (idx: number) => {
    setSelectedIdx(idx);
    const elem = overlays[idx];
    window.dispatchEvent(new CustomEvent("element-selected", { detail: elem }));
  };

  if (!pageData) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
        No document loaded. Click Open to begin.
      </div>
    );
  }

  const scale = 0.75;
  const pageImageUrl = `http://localhost:8000/document/page/${currentPage}/image`;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
        <button onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1}>◀</button>
        <span>Page {currentPage} / {totalPages}</span>
        <button onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= totalPages}>▶</button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "16px", background: "var(--bg-canvas)" }}>
        <div
          style={{
            position: "relative",
            width: `${pageData.width_pt * scale}px`,
            height: `${pageData.height_pt * scale}px`,
            margin: "0 auto",
            boxShadow: `0 2px 8px var(--shadow)`,
          }}
        >
          <img
            src={pageImageUrl}
            alt={`Page ${currentPage}`}
            style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%" }}
            draggable={false}
            onClick={() => {
              setSelectedIdx(null);
              window.dispatchEvent(new CustomEvent("element-deselected"));
            }}
          />

          {overlays.map((ov, idx) => (
            <div
              key={idx}
              onClick={() => handleClick(idx)}
              style={{
                position: "absolute",
                left: `${ov.bbox.x0 * scale}px`,
                top: `${ov.bbox.y0 * scale}px`,
                width: `${(ov.bbox.x1 - ov.bbox.x0) * scale}px`,
                height: `${(ov.bbox.y1 - ov.bbox.y0) * scale}px`,
                border: selectedIdx === idx
                  ? "2px solid var(--accent)"
                  : "1px solid transparent",
                background: selectedIdx === idx
                  ? "var(--accent-light)"
                  : "transparent",
                cursor: "pointer",
              }}
              onMouseEnter={(e) => {
                if (selectedIdx !== idx) {
                  (e.currentTarget as HTMLElement).style.border = "1px solid var(--accent)";
                  (e.currentTarget as HTMLElement).style.background = "rgba(33,150,243,0.04)";
                }
              }}
              onMouseLeave={(e) => {
                if (selectedIdx !== idx) {
                  (e.currentTarget as HTMLElement).style.border = "1px solid transparent";
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                }
              }}
              title={`${ov.label}: ${ov.text.slice(0, 40)}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
