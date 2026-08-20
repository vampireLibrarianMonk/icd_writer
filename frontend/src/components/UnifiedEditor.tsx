import { useEditorStore } from "../store/editorStore";
import { useState, useEffect } from "react";
import { TocEditor } from "./TocEditor";
import { TableEditor } from "./TableEditor";
import { HeaderFooterEditor } from "./HeaderFooterEditor";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface ClickableElement {
  type: "header" | "footer" | "table_cell" | "text_block";
  label: string;
  text: string;
  id: string | null;
  bbox: { x0: number; y0: number; x1: number; y1: number };
}

export function UnifiedEditor({ width }: { width: number }) {
  const { documentLoaded } = useEditorStore();
  const [selected, setSelected] = useState<ClickableElement | null>(null);
  const [editText, setEditText] = useState("");
  const [isTocPage, setIsTocPage] = useState(false);
  const [selectedTableZone, setSelectedTableZone] = useState<{ yMin: number; yMax: number; label: string } | null>(null);
  const currentPage = useEditorStore((s) => s.currentPage);

  // Element navigation state
  const [allElements, setAllElements] = useState<ClickableElement[]>([]);
  const [currentElementIdx, setCurrentElementIdx] = useState<number>(-1);

  // Load all elements for this page (for navigation)
  useEffect(() => {
    if (!documentLoaded || !currentPage) return;
    fetch(`${API_BASE}/document/page/${currentPage}/elements`)
      .then((r) => r.json())
      .then((data) => {
        setAllElements(data.elements || []);
      })
      .catch(() => setAllElements([]));
  }, [currentPage, documentLoaded]);

  // Reset selection on page change
  useEffect(() => {
    setSelected(null);
    setEditText("");
    setSelectedTableZone(null);
    setCurrentElementIdx(-1);
  }, [currentPage]);

  // Listen for element selection from page view
  useEffect(() => {
    const handler = (e: CustomEvent<ClickableElement>) => {
      setSelected(e.detail);
      setEditText(e.detail.text);
      setSelectedTableZone(null);
      // Find index in allElements
      const idx = allElements.findIndex(
        (el) => el.id === e.detail.id || (el.bbox.x0 === e.detail.bbox.x0 && el.bbox.y0 === e.detail.bbox.y0)
      );
      setCurrentElementIdx(idx);
    };
    const deselect = () => { setSelected(null); setSelectedTableZone(null); setCurrentElementIdx(-1); };
    const tableZone = (e: CustomEvent) => {
      setSelectedTableZone(e.detail);
      setSelected(null);
      setCurrentElementIdx(-1);
    };
    window.addEventListener("element-selected" as any, handler);
    window.addEventListener("element-deselected" as any, deselect);
    window.addEventListener("table-zone-selected" as any, tableZone);
    return () => {
      window.removeEventListener("element-selected" as any, handler);
      window.removeEventListener("element-deselected" as any, deselect);
      window.removeEventListener("table-zone-selected" as any, tableZone);
    };
  }, [allElements]);

  // (Navigation is handled by the PageElementSelector dropdown)

  // Check page type
  useEffect(() => {
    if (!documentLoaded || !currentPage) return;
    fetch(`${API_BASE}/document/page/${currentPage}/analysis`)
      .then((r) => r.json())
      .then((data) => {
        setIsTocPage(data.page_type === "table_of_contents");
      })
      .catch(() => { setIsTocPage(false); });
  }, [currentPage, documentLoaded]);

  if (!documentLoaded) {
    return (
      <div style={{ width: `${width}px`, padding: "16px", color: "var(--text-muted)", background: "var(--bg-panel)" }}>
        Open a document to begin.
      </div>
    );
  }

  if (isTocPage && !selected) {
    return (
      <div style={{ width: `${width}px`, padding: "0", background: "var(--bg-panel)", overflow: "auto" }}>
        <PageElementSelector currentPage={currentPage} defaultSection="toc" />
      </div>
    );
  }

  if (selectedTableZone) {
    return (
      <div style={{ width: `${width}px`, padding: "12px", background: "var(--bg-panel)", overflow: "auto" }}>
        <button
          onClick={() => setSelectedTableZone(null)}
          style={{ marginBottom: "8px", fontSize: "11px" }}
        >
          ← Back
        </button>
        <div style={{ fontSize: "12px", fontWeight: "bold", color: "var(--accent)", marginBottom: "8px" }}>
          {selectedTableZone.label}
        </div>
        <TableEditor yMin={selectedTableZone.yMin} yMax={selectedTableZone.yMax} />
      </div>
    );
  }

  if (!selected) {
    return (
      <div style={{ width: `${width}px`, padding: "0", background: "var(--bg-panel)", overflow: "auto" }}>
        <PageElementSelector currentPage={currentPage} />
        <div style={{ padding: "16px", color: "var(--text-muted)" }}>
          <p style={{ fontSize: "11px", color: "var(--text-secondary)", margin: "0 0 10px 0", lineHeight: 1.4 }}>
            Select an element from the dropdown or click directly on the document to edit.
            Changes are saved to a working copy until you use File &gt; Save Document.
          </p>
        </div>
      </div>
    );
  }

  // Header/footer elements are edited via the selector panel, not the paragraph editor
  const isHeaderFooter = selected.bbox.y0 < 60 || selected.bbox.y0 > 700;
  if (isHeaderFooter) {
    return (
      <div style={{ width: `${width}px`, padding: "0", background: "var(--bg-panel)", overflow: "auto" }}>
        <PageElementSelector currentPage={currentPage} defaultSection="footer" />
        <div style={{ padding: "16px", color: "var(--text-muted)" }}>
          Edit header/footer fields above.
        </div>
      </div>
    );
  }

  const hasChanges = editText !== selected.text;

  const handleApply = async () => {
    if (!hasChanges) return;

    if (selected.id) {
      await fetch(`${API_BASE}/document/block/${selected.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_text: editText }),
      });
    } else {
      await fetch(
        `${API_BASE}/document/table-cell?page=${currentPage}&old_text=${encodeURIComponent(selected.text)}&new_text=${encodeURIComponent(editText)}`,
        { method: "PUT" }
      );
    }

    setSelected({ ...selected, text: editText });

    const actions = await fetch(`${API_BASE}/session/actions`).then((r) => r.json());
    // Use Date.now() to guarantee a unique value that always changes
    useEditorStore.setState({
      editCount: useEditorStore.getState().editCount + 1,
      canUndo: actions.undo_available,
      canRedo: actions.redo_available,
      refreshTrigger: Date.now(),
    });
  };

  return (
    <div style={{ width: `${width}px`, padding: "0", background: "var(--bg-panel)", overflow: "auto" }}>
      {/* Consolidated element selector */}
      <PageElementSelector currentPage={currentPage} />

      <div style={{ padding: "12px 16px" }}>
      {/* Back button on special pages */}
      {isTocPage && (
        <button
          onClick={() => setSelected(null)}
          style={{ marginBottom: "8px", fontSize: "11px" }}
        >
          ← Back to TOC
        </button>
      )}

      {/* Element counter */}
      <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "8px" }}>
        Element {currentElementIdx >= 0 ? currentElementIdx + 1 : "—"} of {allElements.length}
      </div>

      {/* Element label */}
      <div style={{ fontSize: "12px", fontWeight: "bold", color: "var(--accent)", marginBottom: "8px" }}>
        {selected.label}
      </div>

      {/* Editor */}
      <textarea
        value={editText}
        onChange={(e) => setEditText(e.target.value)}
        style={{
          width: "100%",
          minHeight: "100px",
          padding: "8px",
          fontSize: "13px",
          fontFamily: "serif",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          background: "var(--input-bg)",
          color: "var(--text-primary)",
          resize: "vertical",
        }}
      />

      {/* Buttons */}
      <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
        <button
          onClick={handleApply}
          disabled={!hasChanges}
          style={{
            padding: "6px 16px",
            background: hasChanges ? "var(--accent)" : "var(--border)",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: hasChanges ? "pointer" : "default",
          }}
        >
          Apply
        </button>
        <button
          onClick={() => setEditText(selected.text)}
          disabled={!hasChanges}
        >
          Revert
        </button>
      </div>

      {/* Element info */}
      <div style={{ marginTop: "12px", fontSize: "11px", color: "var(--text-muted)" }}>
        <div><b>Type:</b> {selected.type}</div>
        {selected.id && <div><b>ID:</b> {selected.id}</div>}
        <div><b>Position:</b> ({selected.bbox.x0.toFixed(0)}, {selected.bbox.y0.toFixed(0)})</div>
      </div>
      </div>
    </div>
  );
}

/* ─── Page Element Selector (Header / Footer / Tables in one dropdown) ─── */

function PageElementSelector({ currentPage, defaultSection }: { currentPage: number; defaultSection?: string }) {
  const [activeSection, setActiveSection] = useState<string>(defaultSection || "");
  const refreshTrigger = useEditorStore((s) => s.refreshTrigger);
  const totalPages = useEditorStore((s) => s.totalPages);
  const [hasHeader, setHasHeader] = useState(false);
  const [hasFooter, setHasFooter] = useState(false);
  const [tableZoneCount, setTableZoneCount] = useState(0);
  const [hasToc, setHasToc] = useState(false);

  // Detect what's on this page
  const [bodyElements, setBodyElements] = useState<{id: string; text: string; type: string}[]>([]);

  useEffect(() => {
    if (!totalPages || !currentPage) return;
    // Check header/footer
    fetch(`${API_BASE}/document/page/${currentPage}/header-footer`)
      .then((r) => r.json())
      .then((data) => {
        setHasHeader((data.header || []).length > 0);
        setHasFooter((data.footer || []).length > 0);
      })
      .catch(() => { setHasHeader(false); setHasFooter(false); });
    // Check tables
    fetch(`${API_BASE}/document/page/${currentPage}/table-zones`)
      .then((r) => r.json())
      .then((data) => setTableZoneCount((data.zones || []).length))
      .catch(() => setTableZoneCount(0));
    // Check TOC
    fetch(`${API_BASE}/document/page/${currentPage}/toc`)
      .then((r) => r.json())
      .then((data) => setHasToc(data.is_toc || false))
      .catch(() => setHasToc(false));
    // Get body elements for the content list
    fetch(`${API_BASE}/document/page/${currentPage}/elements`)
      .then((r) => r.json())
      .then((data) => {
        const elems = (data.elements || []).filter(
          (e: any) => e.type !== "header" && e.type !== "footer"
        );
        setBodyElements(elems.map((e: any) => ({
          id: e.id,
          text: e.text,
          type: e.type,
        })));
      })
      .catch(() => setBodyElements([]));
  }, [currentPage, totalPages, refreshTrigger]);

  // Auto-select based on defaultSection prop
  useEffect(() => {
    if (defaultSection) setActiveSection(defaultSection);
  }, [defaultSection]);

  // Sync dropdown when element is selected from outside (clicking on document)
  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const elem = e.detail;
      if (elem && elem.id) {
        const matchValue = `block-${elem.id}`;
        // Check if this element is in our options
        const exists = bodyElements.some((b) => b.id === elem.id);
        if (exists) {
          setActiveSection(matchValue);
        }
      }
    };
    window.addEventListener("element-selected" as any, handler);
    return () => window.removeEventListener("element-selected" as any, handler);
  }, [bodyElements]);

  // Build options
  const options: { value: string; label: string }[] = [];
  if (hasToc) options.push({ value: "toc", label: "Table of Contents" });
  if (hasHeader) options.push({ value: "header", label: "Header" });
  if (hasFooter) options.push({ value: "footer", label: "Footer" });
  for (let i = 0; i < tableZoneCount; i++) {
    options.push({ value: `table-${i}`, label: tableZoneCount > 1 ? `Table ${i + 1}` : "Table" });
  }
  // Add body content elements labeled by type and count
  const typeCounts: Record<string, number> = {};
  for (const elem of bodyElements) {
    typeCounts[elem.type] = (typeCounts[elem.type] || 0) + 1;
    const count = typeCounts[elem.type];
    const typeLabel = elem.type.charAt(0).toUpperCase() + elem.type.slice(1);
    options.push({ value: `block-${elem.id}`, label: `${typeLabel} ${count}` });
  }

  if (options.length === 0) return null;

  return (
    <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
      <select
        value={activeSection}
        onChange={(e) => {
          const val = e.target.value;
          setActiveSection(val);
          // If a body block is selected, dispatch element-selected to show it in the editor
          if (val.startsWith("block-")) {
            const blockId = val.replace("block-", "");
            const elem = bodyElements.find((el) => el.id === blockId);
            if (elem) {
              // Fetch full element data to get bbox
              fetch(`${API_BASE}/document/page/${currentPage}/elements`)
                .then((r) => r.json())
                .then((data) => {
                  const fullElem = (data.elements || []).find((el: any) => el.id === blockId);
                  if (fullElem) {
                    window.dispatchEvent(new CustomEvent("element-selected", { detail: fullElem }));
                  }
                });
            }
          }
        }}
        style={{
          width: "100%",
          fontSize: "12px",
          padding: "4px 8px",
          borderRadius: "4px",
          border: "1px solid var(--border)",
          background: "var(--input-bg, #fff)",
          color: "var(--text-primary)",
          marginBottom: "8px",
        }}
      >
        <option value="">— Select section to edit —</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {activeSection === "header" && (
        <HeaderFooterEditor section="header" />
      )}
      {activeSection === "footer" && (
        <HeaderFooterEditor section="footer" />
      )}
      {activeSection === "toc" && (
        <TocEditor />
      )}
      {activeSection.startsWith("table-") && (
        <TableEditor />
      )}
    </div>
  );
}
