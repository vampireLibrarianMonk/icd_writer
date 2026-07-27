import { useEffect, useState } from "react";
import { useEditorStore } from "../store/editorStore";

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
  const [tocData, setTocData] = useState<TocData | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editPage, setEditPage] = useState("");

  useEffect(() => {
    if (!totalPages || !currentPage) return;
    fetch(`http://localhost:8000/document/page/${currentPage}/toc`)
      .then((r) => r.json())
      .then(setTocData)
      .catch(() => setTocData(null));
  }, [currentPage, totalPages]);

  if (!tocData || !tocData.is_toc) return null;

  const handleEdit = (idx: number) => {
    setEditingIdx(idx);
    setEditTitle(tocData.entries[idx].title);
    setEditPage(tocData.entries[idx].page_ref);
  };

  const handleSave = () => {
    if (editingIdx === null) return;
    const newEntries = [...tocData.entries];
    newEntries[editingIdx] = { ...newEntries[editingIdx], title: editTitle, page_ref: editPage };
    setTocData({ ...tocData, entries: newEntries });
    // TODO: persist to backend
    setEditingIdx(null);
  };

  const handleCancel = () => setEditingIdx(null);

  return (
    <div style={{ padding: "0" }}>
      <div style={{ fontSize: "12px", fontWeight: "bold", color: "var(--accent)", marginBottom: "8px" }}>
        📋 Table of Contents
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "4px", borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>Section</th>
            <th style={{ textAlign: "right", padding: "4px", borderBottom: "1px solid var(--border)", color: "var(--text-secondary)", width: "40px" }}>Pg</th>
          </tr>
        </thead>
        <tbody>
          {tocData.entries.map((entry, idx) => {
            const isEditing = editingIdx === idx;
            const indent = Math.min(entry.indent / 12, 3) * 12;
            return (
              <tr
                key={idx}
                onClick={() => !isEditing && handleEdit(idx)}
                style={{ cursor: "pointer", background: isEditing ? "var(--accent-light)" : "transparent" }}
              >
                <td style={{ padding: "3px 4px", paddingLeft: `${indent + 4}px`, color: "var(--text-primary)" }}>
                  {isEditing ? (
                    <input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") handleCancel(); }}
                      autoFocus
                      style={{ width: "100%", border: "1px solid var(--accent)", borderRadius: "2px", padding: "1px 4px", fontSize: "12px", background: "var(--input-bg)", color: "var(--text-primary)" }}
                    />
                  ) : (
                    entry.title
                  )}
                </td>
                <td style={{ padding: "3px 4px", textAlign: "right", color: "var(--text-secondary)" }}>
                  {isEditing ? (
                    <div style={{ display: "flex", gap: "2px", justifyContent: "flex-end" }}>
                      <input
                        value={editPage}
                        onChange={(e) => setEditPage(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") handleCancel(); }}
                        style={{ width: "30px", border: "1px solid var(--accent)", borderRadius: "2px", padding: "1px", fontSize: "11px", textAlign: "right", background: "var(--input-bg)", color: "var(--text-primary)" }}
                      />
                      <button onClick={handleSave} style={{ fontSize: "9px", padding: "0 3px" }}>✓</button>
                      <button onClick={handleCancel} style={{ fontSize: "9px", padding: "0 3px" }}>✗</button>
                    </div>
                  ) : (
                    entry.page_ref
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
