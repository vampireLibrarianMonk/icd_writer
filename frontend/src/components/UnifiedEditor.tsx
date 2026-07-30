import { useEditorStore } from "../store/editorStore";
import { useState, useEffect } from "react";
import { TocEditor } from "./TocEditor";
import { TableEditor } from "./TableEditor";

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
  const [isTablePage, setIsTablePage] = useState(false);
  const [selectedTableZone, setSelectedTableZone] = useState<{ yMin: number; yMax: number; label: string } | null>(null);
  const currentPage = useEditorStore((s) => s.currentPage);

  // Element navigation state
  const [allElements, setAllElements] = useState<ClickableElement[]>([]);
  const [currentElementIdx, setCurrentElementIdx] = useState<number>(-1);

  // Load all elements for this page (for navigation)
  useEffect(() => {
    if (!documentLoaded || !currentPage) return;
    fetch(`http://localhost:8000/document/page/${currentPage}/elements`)
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

  // Navigate to prev/next element
  const navigateElement = (direction: "prev" | "next") => {
    if (allElements.length === 0) return;
    let newIdx = currentElementIdx;
    if (direction === "next") {
      newIdx = currentElementIdx < allElements.length - 1 ? currentElementIdx + 1 : 0;
    } else {
      newIdx = currentElementIdx > 0 ? currentElementIdx - 1 : allElements.length - 1;
    }
    const elem = allElements[newIdx];
    setSelected(elem);
    setEditText(elem.text);
    setCurrentElementIdx(newIdx);
    // Also highlight it on the document view
    window.dispatchEvent(new CustomEvent("element-selected", { detail: elem }));
  };

  // Check page type
  useEffect(() => {
    if (!documentLoaded || !currentPage) return;
    fetch(`http://localhost:8000/document/page/${currentPage}/analysis`)
      .then((r) => r.json())
      .then((data) => {
        setIsTocPage(data.page_type === "table_of_contents");
        setIsTablePage(data.page_type === "table");
      })
      .catch(() => { setIsTocPage(false); setIsTablePage(false); });
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
      <div style={{ width: `${width}px`, padding: "12px", background: "var(--bg-panel)", overflow: "auto" }}>
        <TocEditor />
      </div>
    );
  }

  if (isTablePage && !selected && !selectedTableZone) {
    return (
      <div style={{ width: `${width}px`, padding: "16px", color: "var(--text-muted)", background: "var(--bg-panel)" }}>
        Click a table area on the page to edit it, or click any other element.
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
      <div style={{ width: `${width}px`, padding: "16px", color: "var(--text-muted)", background: "var(--bg-panel)" }}>
        Click any element on the page to edit it.
      </div>
    );
  }

  const hasChanges = editText !== selected.text;

  const handleApply = async () => {
    if (!hasChanges) return;

    if (selected.id) {
      await fetch(`http://localhost:8000/document/block/${selected.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_text: editText }),
      });
    } else {
      await fetch(
        `http://localhost:8000/document/table-cell?page=${currentPage}&old_text=${encodeURIComponent(selected.text)}&new_text=${encodeURIComponent(editText)}`,
        { method: "PUT" }
      );
    }

    setSelected({ ...selected, text: editText });

    const actions = await fetch("http://localhost:8000/session/actions").then((r) => r.json());
    // Use Date.now() to guarantee a unique value that always changes
    useEditorStore.setState({
      editCount: useEditorStore.getState().editCount + 1,
      canUndo: actions.undo_available,
      canRedo: actions.redo_available,
      refreshTrigger: Date.now(),
    });
  };

  return (
    <div style={{ width: `${width}px`, padding: "16px", background: "var(--bg-panel)", overflow: "auto" }}>
      {/* Back button on special pages */}
      {isTocPage && (
        <button
          onClick={() => setSelected(null)}
          style={{ marginBottom: "8px", fontSize: "11px" }}
        >
          ← Back to TOC
        </button>
      )}
      {/* Element navigation bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        marginBottom: "8px",
        padding: "4px 8px",
        background: "var(--bg-secondary)",
        borderRadius: "4px",
        fontSize: "11px",
      }}>
        <button
          onClick={() => navigateElement("prev")}
          disabled={allElements.length === 0}
          style={{ padding: "2px 6px", fontSize: "11px" }}
          title="Previous element"
        >◀</button>
        <span style={{ fontWeight: 500 }}>
          Element {currentElementIdx >= 0 ? currentElementIdx + 1 : "—"} of {allElements.length}
        </span>
        <button
          onClick={() => navigateElement("next")}
          disabled={allElements.length === 0}
          style={{ padding: "2px 6px", fontSize: "11px" }}
          title="Next element"
        >▶</button>
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
  );
}
