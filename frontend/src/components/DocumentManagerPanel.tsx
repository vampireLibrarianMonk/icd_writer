import { useState, useEffect, useRef } from "react";
import { api } from "../api/client";
import { useEditorStore } from "../store/editorStore";

interface DocEntry {
  path: string;
  filename: string;
  stem: string;
  title: string;
  indexed: boolean;
  size_bytes: number;
  sha256: string;
}

/**
 * Document Manager — file-explorer style panel for managing ICD documents.
 * Supports multi-select, bulk operations, upload, open, delete, re-index.
 */
export function DocumentManagerPanel() {
  const [documents, setDocuments] = useState<DocEntry[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"filename" | "size_bytes">("filename");
  const [sortAsc, setSortAsc] = useState(true);
  const [filter, setFilter] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { documentPath } = useEditorStore();

  const refresh = () => {
    setLoading(true);
    api.listDocuments()
      .then((res) => setDocuments(res.documents || []))
      .catch(() => setDocuments([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { refresh(); }, []);

  // Sort and filter
  const filtered = documents
    .filter((d) => !filter || d.filename.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => {
      const va = a[sortBy];
      const vb = b[sortBy];
      const cmp = typeof va === "string" ? va.localeCompare(vb as string) : (va as number) - (vb as number);
      return sortAsc ? cmp : -cmp;
    });

  const allSelected = filtered.length > 0 && filtered.every((d) => selected.has(d.stem));

  const toggleSelect = (stem: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(stem) ? next.delete(stem) : next.add(stem);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((d) => d.stem)));
    }
  };

  const handleOpen = async (doc: DocEntry) => {
    setActionMsg(`Opening ${doc.filename}...`);
    await useEditorStore.getState().loadDocument(doc.path);
    setActionMsg(null);
  };

  const handleDelete = async () => {
    if (selected.size === 0) return;
    const count = selected.size;
    if (!confirm(`Delete ${count} document${count > 1 ? "s" : ""}? This removes indices and IR files.`)) return;
    setDeleting(true);
    setActionMsg(`Deleting ${count} document${count > 1 ? "s" : ""}...`);
    for (const stem of selected) {
      try { await api.deleteDocument(stem); } catch { /* continue */ }
    }
    setSelected(new Set());
    setActionMsg(null);
    setDeleting(false);
    refresh();
  };

  const handleUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setActionMsg(`Uploading ${files.length} file${files.length > 1 ? "s" : ""}...`);
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        await api.ingestDocument(file);
        // Poll until done (simple wait)
        await new Promise((r) => setTimeout(r, 2000));
      } catch { /* continue */ }
    }
    setActionMsg(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    refresh();
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const currentFile = documentPath.split(/[/\\]/).pop() || "";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: "6px",
        padding: "8px 12px", borderBottom: "1px solid var(--border)",
        background: "var(--bg-secondary, #f5f5f5)", flexWrap: "wrap",
      }}>
        <button onClick={handleUpload} style={toolbarBtn} title="Upload PDF">
          + Upload
        </button>
        <button
          onClick={handleDelete}
          disabled={selected.size === 0 || deleting}
          style={{ ...toolbarBtn, color: selected.size > 0 ? "#c62828" : undefined }}
          title="Delete selected"
        >
          Delete ({selected.size})
        </button>
        <button onClick={refresh} style={toolbarBtn} title="Refresh list">
          Refresh
        </button>
        <div style={{ flex: 1 }} />
        <input
          type="text"
          placeholder="Filter..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{
            padding: "3px 8px", fontSize: "11px", borderRadius: "3px",
            border: "1px solid var(--border)", width: "120px",
            background: "var(--input-bg, #fff)", color: "var(--text-primary)",
          }}
        />
        <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>
          {filtered.length} doc{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        multiple
        style={{ display: "none" }}
        onChange={handleFileSelected}
      />

      {/* Action message */}
      {actionMsg && (
        <div style={{ padding: "6px 12px", fontSize: "11px", color: "var(--accent, #1976d2)", background: "var(--info-bg, #e3f2fd)" }}>
          {actionMsg}
        </div>
      )}

      {/* Column headers */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "28px 1fr 70px",
        padding: "4px 12px",
        borderBottom: "1px solid var(--border)",
        fontSize: "10px", fontWeight: 600, color: "var(--text-secondary)",
        textTransform: "uppercase", letterSpacing: "0.5px",
        background: "var(--bg-secondary, #fafafa)",
      }}>
        <div>
          <input type="checkbox" checked={allSelected} onChange={toggleAll} title="Select all" />
        </div>
        <div
          onClick={() => { setSortBy("filename"); setSortAsc(sortBy === "filename" ? !sortAsc : true); }}
          style={{ cursor: "pointer" }}
        >
          Name {sortBy === "filename" ? (sortAsc ? "▲" : "▼") : ""}
        </div>
        <div
          onClick={() => { setSortBy("size_bytes"); setSortAsc(sortBy === "size_bytes" ? !sortAsc : true); }}
          style={{ cursor: "pointer", textAlign: "right" }}
        >
          Size {sortBy === "size_bytes" ? (sortAsc ? "▲" : "▼") : ""}
        </div>
      </div>

      {/* File list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {loading ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--text-secondary)", fontSize: "12px" }}>
            Loading...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--text-secondary)", fontSize: "12px" }}>
            No documents found. Upload a PDF to get started.
          </div>
        ) : (
          filtered.map((doc) => {
            const isOpen = doc.filename === currentFile;
            const isSel = selected.has(doc.stem);
            return (
              <div
                key={doc.stem}
                style={{
                  display: "grid",
                  gridTemplateColumns: "28px 1fr 70px",
                  padding: "5px 12px",
                  borderBottom: "1px solid var(--border, #eee)",
                  background: isSel ? "var(--accent-light, #e3f2fd)" : isOpen ? "var(--success-bg, #e8f5e9)" : "transparent",
                  fontSize: "12px",
                  alignItems: "center",
                }}
              >
                <div>
                  <input
                    type="checkbox"
                    checked={isSel}
                    onChange={() => toggleSelect(doc.stem)}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", overflow: "hidden" }}>
                  <span style={{ fontSize: "14px" }}>📄</span>
                  <span
                    onDoubleClick={() => handleOpen(doc)}
                    style={{
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      cursor: "pointer", fontWeight: isOpen ? 600 : 400,
                    }}
                    title={`${doc.filename}\n${doc.title || ""}\nDouble-click to open`}
                  >
                    {doc.filename}
                  </span>
                  {isOpen && <span style={{ fontSize: "9px", color: "var(--success-text, #2e7d32)", fontWeight: 600 }}>OPEN</span>}
                </div>
                <div style={{ textAlign: "right", color: "var(--text-secondary)", fontSize: "11px" }}>
                  {formatSize(doc.size_bytes)}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Status bar */}
      <div style={{
        padding: "4px 12px", borderTop: "1px solid var(--border)",
        fontSize: "10px", color: "var(--text-secondary)",
        background: "var(--bg-secondary, #fafafa)",
        display: "flex", justifyContent: "space-between",
      }}>
        <span>{selected.size > 0 ? `${selected.size} selected` : `${filtered.length} documents`}</span>
        <span>{formatSize(filtered.reduce((sum, d) => sum + d.size_bytes, 0))} total</span>
      </div>
    </div>
  );
}

const toolbarBtn: React.CSSProperties = {
  padding: "4px 10px",
  fontSize: "11px",
  borderRadius: "3px",
  border: "1px solid var(--border)",
  background: "var(--bg-panel, #fff)",
  cursor: "pointer",
  fontWeight: 500,
};
