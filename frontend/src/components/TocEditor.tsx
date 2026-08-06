import { useEffect, useState } from "react";
import { useEditorStore } from "../store/editorStore";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface TocEntry {
  title: string;
  page_ref: string;
  indent: number;
}

interface TocData {
  is_toc: boolean;
  entries: TocEntry[];
}

export function TocEditor() {
  const currentPage = useEditorStore((s) => s.currentPage);
  const totalPages = useEditorStore((s) => s.totalPages);
  const refreshTrigger = useEditorStore((s) => s.refreshTrigger);
  const [tocData, setTocData] = useState<TocData | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editPage, setEditPage] = useState("");

  useEffect(() => {
    if (!totalPages || !currentPage) return;
    fetch(`${API_BASE}/document/page/${currentPage}/toc`)
      .then((r) => r.json())
      .then(setTocData)
      .catch(() => setTocData(null));
  }, [currentPage, totalPages, refreshTrigger]);

  if (!tocData || !tocData.is_toc) return null;

  const handleEdit = (idx: number) => {
    setEditingIdx(idx);
    setEditTitle(tocData.entries[idx].title);
    setEditPage(tocData.entries[idx].page_ref);
  };

  const handleSave = async () => {
    if (editingIdx === null) return;
    const oldEntry = tocData.entries[editingIdx];
    const params = new URLSearchParams();
    params.set("index", String(editingIdx));
    if (editTitle !== oldEntry.title) params.set("title", editTitle);
    if (editPage !== oldEntry.page_ref) params.set("page_ref", editPage);

    try {
      const res = await fetch(`${API_BASE}/document/page/${currentPage}/toc?${params.toString()}`, { method: "PUT" });
      if (res.ok) {
        const newEntries = [...tocData.entries];
        newEntries[editingIdx] = { ...newEntries[editingIdx], title: editTitle, page_ref: editPage };
        setTocData({ ...tocData, entries: newEntries });
        useEditorStore.setState((s) => ({
          refreshTrigger: s.refreshTrigger + 1,
          editCount: s.editCount + 1,
        }));
      }
    } catch (e) {
      console.error("TOC edit failed:", e);
    }
    setEditingIdx(null);
  };

  const handleCancel = () => setEditingIdx(null);

  const handleAddEntry = async () => {
    if (!tocData) return;
    try {
      const res = await fetch(`${API_BASE}/document/page/${currentPage}/toc?title=New+Section&page_ref=`, { method: "POST" });
      if (res.ok) {
        // Re-fetch TOC data to get the new entry from the PDF
        const tocRes = await fetch(`${API_BASE}/document/page/${currentPage}/toc`).then((r) => r.json());
        setTocData(tocRes);
        // Edit the last entry (newly added)
        const newIdx = tocRes.entries.length - 1;
        setEditingIdx(newIdx);
        setEditTitle("New Section");
        setEditPage("");
        useEditorStore.setState((s) => ({
          refreshTrigger: s.refreshTrigger + 1,
          editCount: s.editCount + 1,
        }));
      }
    } catch (e) {
      console.error("TOC add failed:", e);
    }
  };

  const handleDeleteEntry = async (idx: number) => {
    if (!tocData) return;
    try {
      const res = await fetch(`${API_BASE}/document/page/${currentPage}/toc?index=${idx}`, { method: "DELETE" });
      if (res.ok) {
        const newEntries = tocData.entries.filter((_, i) => i !== idx);
        setTocData({ ...tocData, entries: newEntries });
        setEditingIdx(null);
        useEditorStore.setState((s) => ({
          refreshTrigger: s.refreshTrigger + 1,
          editCount: s.editCount + 1,
        }));
      }
    } catch (e) {
      console.error("TOC delete failed:", e);
    }
  };

  const handleIndentIncrease = (idx: number) => {
    if (!tocData) return;
    const newEntries = [...tocData.entries];
    newEntries[idx] = { ...newEntries[idx], indent: Math.min(newEntries[idx].indent + 18, 54) };
    setTocData({ ...tocData, entries: newEntries });
  };

  const handleIndentDecrease = (idx: number) => {
    if (!tocData) return;
    const newEntries = [...tocData.entries];
    newEntries[idx] = { ...newEntries[idx], indent: Math.max(newEntries[idx].indent - 18, 0) };
    setTocData({ ...tocData, entries: newEntries });
  };

  return (
    <div style={{ padding: "0" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
        <span style={{ fontSize: "12px", fontWeight: "bold", color: "var(--text-primary)" }}>
          Table of Contents
        </span>
        <button
          onClick={handleAddEntry}
          style={{
            fontSize: "11px",
            padding: "2px 8px",
            background: "#4caf50",
            color: "white",
            border: "none",
            borderRadius: "3px",
            cursor: "pointer",
          }}
        >
          + Entry
        </button>
      </div>

      <div style={{ border: "1px solid var(--border)", borderRadius: "4px", overflow: "hidden" }}>
        {tocData.entries.map((entry, idx) => {
          const isEditing = editingIdx === idx;
          const indentPx = Math.min(entry.indent, 54);

          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "center",
                padding: "4px 6px",
                paddingLeft: `${indentPx + 6}px`,
                borderBottom: idx < tocData.entries.length - 1 ? "1px solid var(--border)" : "none",
                background: isEditing ? "var(--accent-light, #e3f2fd)" : "transparent",
                fontSize: "12px",
                gap: "4px",
              }}
            >
              {isEditing ? (
                <>
                  <div style={{ display: "flex", flexDirection: "column", flex: 1, gap: "3px" }}>
                    <input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") handleCancel(); }}
                      autoFocus
                      placeholder="Section title"
                      style={{
                        width: "100%",
                        border: "1px solid var(--accent, #2196F3)",
                        borderRadius: "2px",
                        padding: "2px 4px",
                        fontSize: "12px",
                        background: "var(--input-bg, #fff)",
                        color: "var(--text-primary)",
                      }}
                    />
                    <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                      <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Page:</span>
                      <input
                        value={editPage}
                        onChange={(e) => setEditPage(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") handleCancel(); }}
                        placeholder="#"
                        style={{
                          width: "35px",
                          border: "1px solid var(--border)",
                          borderRadius: "2px",
                          padding: "2px 4px",
                          fontSize: "11px",
                          textAlign: "center",
                          background: "var(--input-bg, #fff)",
                          color: "var(--text-primary)",
                        }}
                      />
                      <button onClick={() => handleIndentDecrease(idx)} style={{ fontSize: "10px", padding: "1px 4px", cursor: "pointer" }} title="Decrease indent">←</button>
                      <button onClick={() => handleIndentIncrease(idx)} style={{ fontSize: "10px", padding: "1px 4px", cursor: "pointer" }} title="Increase indent">→</button>
                      <span style={{ flex: 1 }} />
                      <button onClick={handleSave} style={{ fontSize: "10px", padding: "1px 6px", background: "#2196F3", color: "white", border: "none", borderRadius: "2px", cursor: "pointer" }}>Save</button>
                      <button onClick={handleCancel} style={{ fontSize: "10px", padding: "1px 6px", background: "var(--bg-secondary, #eee)", color: "var(--text-primary)", border: "1px solid var(--border, #ccc)", borderRadius: "2px", cursor: "pointer" }}>Cancel</button>
                      <button onClick={() => handleDeleteEntry(idx)} style={{ fontSize: "10px", padding: "1px 6px", background: "#f44336", color: "white", border: "none", borderRadius: "2px", cursor: "pointer" }}>Delete</button>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <span
                    onClick={() => handleEdit(idx)}
                    style={{ flex: 1, cursor: "pointer", color: "var(--text-primary)" }}
                    title="Click to edit"
                  >
                    {entry.title}
                  </span>
                  <span style={{ fontSize: "11px", color: "var(--text-secondary)", minWidth: "24px", textAlign: "right" }}>
                    {entry.page_ref}
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
