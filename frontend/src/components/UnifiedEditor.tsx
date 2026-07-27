import { useEditorStore } from "../store/editorStore";
import { useState, useEffect } from "react";
import { TocEditor } from "./TocEditor";

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
  const currentPage = useEditorStore((s) => s.currentPage);

  // Reset selection on page change
  useEffect(() => {
    setSelected(null);
    setEditText("");
  }, [currentPage]);

  // Listen for element selection from page view
  useEffect(() => {
    const handler = (e: CustomEvent<ClickableElement>) => {
      setSelected(e.detail);
      setEditText(e.detail.text);
    };
    window.addEventListener("element-selected" as any, handler);
    return () => window.removeEventListener("element-selected" as any, handler);
  }, []);

  // Check if current page is TOC via page analysis
  useEffect(() => {
    if (!documentLoaded || !currentPage) return;
    fetch(`http://localhost:8000/document/page/${currentPage}/analysis`)
      .then((r) => r.json())
      .then((data) => setIsTocPage(data.page_type === "table_of_contents"))
      .catch(() => setIsTocPage(false));
  }, [currentPage, documentLoaded]);

  if (!documentLoaded) {
    return (
      <div style={{ width: `${width}px`, padding: "16px", color: "var(--text-muted)", background: "var(--bg-panel)" }}>
        Open a document to begin.
      </div>
    );
  }

  if (isTocPage) {
    return (
      <div style={{ width: `${width}px`, position: "relative", background: "var(--bg-panel)", overflow: "auto" }}>
        <TocEditor />
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
    useEditorStore.setState((state) => ({
      editCount: state.editCount + 1,
      canUndo: actions.undo_available,
      canRedo: actions.redo_available,
      refreshTrigger: state.refreshTrigger + 1,
    }));
  };

  return (
    <div style={{ width: `${width}px`, padding: "16px", background: "var(--bg-panel)", overflow: "auto" }}>
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
