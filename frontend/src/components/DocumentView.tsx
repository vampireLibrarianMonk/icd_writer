import { useEditorStore } from "../store/editorStore";
import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface Overlay {
  type: "header" | "footer" | "table_cell" | "text_block";
  label: string;
  text: string;
  id: string | null;
  bbox: { x0: number; y0: number; x1: number; y1: number };
}

export function DocumentView() {
  const { pageData, currentPage, totalPages, goToPage, documentPath, refreshTrigger } = useEditorStore();
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  // Load all clickable overlays for this page (fine-grained spans)
  useEffect(() => {
    if (!totalPages || !currentPage) return;

    Promise.all([
      fetch(`${API_BASE}/document/page/${currentPage}/elements`).then((r) => r.json()),
      fetch(`${API_BASE}/document/page/${currentPage}/analysis`).then((r) => r.json()),
    ]).then(([elemData, analysis]) => {
      let elems = elemData.elements || [];
      // On TOC pages, only show header/footer overlays
      if (analysis.page_type === "table_of_contents") {
        elems = elems.filter((e: Overlay) => e.type === "header" || e.type === "footer");
      }
      // Elements now come from Document IR with proper block IDs.
      // No table zone replacement needed — IR blocks are clickable and editable directly.
      setOverlays(elems);
      setSelectedIdx(null);
    }).catch(() => setOverlays([]));
  }, [currentPage, totalPages, refreshTrigger]);

  // Listen for TBD navigation: highlight matching element on current page
  const [highlightText, setHighlightText] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const { context } = e.detail;
      // Store the context text to match against overlays
      setHighlightText(context);
    };
    window.addEventListener("navigate-to-tbd" as any, handler);
    return () => window.removeEventListener("navigate-to-tbd" as any, handler);
  }, []);

  // Once overlays load after navigation, find and highlight the matching one
  useEffect(() => {
    if (!highlightText || overlays.length === 0) return;

    // Find the overlay whose text best matches the TBD context
    const contextLower = highlightText.toLowerCase();
    let bestIdx = -1;
    let bestScore = 0;

    for (let i = 0; i < overlays.length; i++) {
      const ovText = overlays[i].text.toLowerCase();
      // Check if context words appear in the overlay text
      const contextWords = contextLower.split(/\s+/).filter(w => w.length > 3);
      const matches = contextWords.filter(w => ovText.includes(w)).length;
      const score = contextWords.length > 0 ? matches / contextWords.length : 0;
      if (score > bestScore) {
        bestScore = score;
        bestIdx = i;
      }
    }

    if (bestIdx >= 0 && bestScore > 0.3) {
      setSelectedIdx(bestIdx);
      // Also dispatch element-selected so the editor panel shows it
      window.dispatchEvent(new CustomEvent("element-selected", { detail: overlays[bestIdx] }));
    }

    // Clear highlight text after matching
    setHighlightText(null);
  }, [overlays, highlightText]);

  const handleClick = (idx: number) => {
    setSelectedIdx(idx);
    const elem = overlays[idx] as any;
    if (elem._isTableZone) {
      // Dispatch table zone selection
      window.dispatchEvent(new CustomEvent("table-zone-selected", {
        detail: { yMin: elem._yMin, yMax: elem._yMax, label: elem.label }
      }));
    } else {
      window.dispatchEvent(new CustomEvent("element-selected", { detail: elem }));
    }
  };

  if (!pageData) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
        No document loaded. Click Open to begin.
      </div>
    );
  }

  const scale = 0.75;
  const pageImageUrl = `${API_BASE}/document/page/${currentPage}/image?v=${refreshTrigger}`;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
        <span style={{ fontSize: "12px", fontWeight: 500, marginRight: "8px", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={documentPath}>
          {documentPath.split("/").pop()}
        </span>
        <span style={{ borderLeft: "1px solid #ccc", height: "16px" }} />
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
            key={`page-img-${currentPage}-${refreshTrigger}`}
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
