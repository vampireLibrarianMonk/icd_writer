import { useEditorStore } from "../store/editorStore";
import { api } from "../api/client";
import { useRef, useState, useEffect } from "react";

interface DocInfo {
  path: string;
  filename: string;
  stem: string;
  indexed: boolean;
}

interface ToolbarProps {
  onFileUpload: (file: File) => void;
  onShowHelp: (tab?: "how-it-works" | "evaluation" | "about") => void;
}

export function Toolbar({ onFileUpload, onShowHelp }: ToolbarProps) {
  const { documentLoaded, editCount, undo, redo, canUndo, canRedo, documentPath } = useEditorStore();
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const [darkMode, setDarkMode] = useState(false);
  const [availableDocs, setAvailableDocs] = useState<DocInfo[]>([]);
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const fileMenuRef = useRef<HTMLDivElement>(null);

  // Load available documents on mount and after document state changes
  useEffect(() => {
    api.listDocuments().then((res) => {
      setAvailableDocs(res.documents || []);
    }).catch(() => {});
  }, [documentLoaded]);

  // Close file menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (fileMenuRef.current && !fileMenuRef.current.contains(e.target as Node)) {
        setFileMenuOpen(false);
      }
    };
    if (fileMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [fileMenuOpen]);

  const handleDocSwitch = async (path: string) => {
    if (path === documentPath) return;
    await useEditorStore.getState().loadDocument(path);
    api.listDocuments().then((res) => setAvailableDocs(res.documents || []));
  };

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.setAttribute("data-theme", !darkMode ? "dark" : "light");
  };

  const handleUploadClick = () => {
    uploadInputRef.current?.click();
  };

  const handleUploadSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onFileUpload(file);
    e.target.value = "";
  };

  const handleSave = async () => {
    setFileMenuOpen(false);
    await api.saveSession();
  };

  const handleExport = async () => {
    setFileMenuOpen(false);
    const origName = useEditorStore.getState().documentPath.split("/").pop()?.replace(".pdf", "") || "document";
    const exportName = `${origName}_edited.pdf`;
    const API_BASE = import.meta.env.VITE_API_BASE || "";
    const res = await fetch(`${API_BASE}/document/export`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Export failed" }));
      alert(err.detail || "Export failed — is a document loaded?");
      return;
    }
    window.location.href = `${API_BASE}/document/export-download?filename=${encodeURIComponent(exportName)}`;
  };

  const handleDelete = async () => {
    setFileMenuOpen(false);
    const docPath = useEditorStore.getState().documentPath;
    const filename = docPath.split("/").pop() || "this document";
    const stem = filename.replace(".pdf", "");

    const confirmed = window.confirm(
      `Remove "${filename}" from the application?\n\n` +
      `This will:\n` +
      `• Remove all search index data (OpenSearch)\n` +
      `• Delete the extracted document structure\n` +
      `• Remove associated TBD/TBR items\n\n` +
      `The original PDF in icds/ will NOT be deleted.\n` +
      `Uploaded PDFs in uploads/ WILL be deleted.`
    );
    if (!confirmed) return;

    try {
      const result = await api.deleteDocument(stem);
      // Reset the editor state
      useEditorStore.setState({
        documentLoaded: false,
        documentPath: "",
        totalPages: 0,
        currentPage: 1,
        pageData: null,
        selectedBlock: null,
        editText: "",
      });
      // Refresh available docs
      api.listDocuments().then((res) => setAvailableDocs(res.documents || []));
      alert(
        `Document removed.\n\n` +
        `• ${result.chunks_deleted} chunks removed from ${result.indices_cleared} indices\n` +
        `• ${result.tbd_items_removed} TBD items removed\n` +
        `• IR file deleted: ${result.ir_deleted}`
      );
    } catch (e) {
      alert("Delete failed: " + (e instanceof Error ? e.message : "unknown error"));
    }
  };

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "6px",
      padding: "6px 12px",
      borderBottom: "1px solid var(--border)",
      background: "var(--bg-secondary)",
      fontSize: "13px",
    }}>
      {/* File dropdown menu */}
      <div ref={fileMenuRef} style={{ position: "relative" }}>
        <button
          onClick={() => setFileMenuOpen(!fileMenuOpen)}
          style={{
            background: "transparent",
            border: "none",
            padding: "4px 10px",
            cursor: "pointer",
            fontWeight: 500,
            fontSize: "13px",
            borderRadius: "4px",
            color: "var(--text-primary)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-tertiary, #e8e8e8)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          File
        </button>
        {fileMenuOpen && (
          <div style={{
            position: "absolute",
            top: "100%",
            left: 0,
            background: "var(--bg-primary, #fff)",
            border: "1px solid var(--border, #ddd)",
            borderRadius: "6px",
            boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
            minWidth: "180px",
            zIndex: 1000,
            padding: "4px 0",
          }}>
            <MenuItem label="Upload & Index..." shortcut="Ctrl+U" onClick={() => { setFileMenuOpen(false); handleUploadClick(); }} />
            <MenuDivider />
            <MenuItem label="Save Session" shortcut="Ctrl+S" onClick={handleSave} disabled={!documentLoaded} />
            <MenuItem label="Export PDF..." onClick={handleExport} disabled={!documentLoaded} />
            <MenuItem label="Remove Document..." onClick={handleDelete} disabled={!documentLoaded} />
            <MenuDivider />
            <MenuItem label="Undo" shortcut="Ctrl+Z" onClick={() => { setFileMenuOpen(false); undo(); }} disabled={!canUndo} />
            <MenuItem label="Redo" shortcut="Ctrl+Y" onClick={() => { setFileMenuOpen(false); redo(); }} disabled={!canRedo} />
          </div>
        )}
      </div>

      {/* Help menu */}
      <button
        onClick={() => onShowHelp("how-it-works")}
        style={{
          background: "transparent",
          border: "none",
          padding: "4px 10px",
          cursor: "pointer",
          fontWeight: 500,
          fontSize: "13px",
          borderRadius: "4px",
          color: "var(--text-primary)",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-tertiary, #e8e8e8)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        Help
      </button>

      <span style={{ borderLeft: "1px solid var(--border, #ccc)", height: "20px" }} />

      {/* Hidden file input for upload */}
      <input
        ref={uploadInputRef}
        type="file"
        accept=".pdf"
        style={{ display: "none" }}
        onChange={handleUploadSelected}
      />

      {/* Open indexed document dropdown */}
      {availableDocs.length > 0 && (
        <>
          <select
            value={documentPath || ""}
            onChange={(e) => e.target.value && handleDocSwitch(e.target.value)}
            style={{
              fontSize: "12px",
              padding: "4px 8px",
              borderRadius: "4px",
              border: "1px solid var(--border)",
              maxWidth: "200px",
              background: "var(--bg-primary)",
              color: "var(--text-primary)",
            }}
            title="Open an indexed document"
          >
            <option value="">— Open Document —</option>
            {availableDocs.map((doc) => (
              <option key={doc.path} value={doc.path}>
                {doc.filename}
              </option>
            ))}
          </select>
        </>
      )}

      <span style={{ borderLeft: "1px solid var(--border, #ccc)", height: "20px", margin: "0 4px" }} />

      {/* Theme toggle */}
      <button onClick={toggleDarkMode} title="Toggle dark/light mode">
        {darkMode ? "☀️" : "🌙"}
      </button>

      {/* Spacer */}
      <span style={{ flex: 1 }} />

      {/* Edit count */}
      {documentLoaded && editCount > 0 && (
        <span style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
          {editCount} edit{editCount !== 1 ? "s" : ""}
        </span>
      )}
    </div>
  );
}

/* ─── Menu Components ───────────────────────────────────────── */

function MenuItem({ label, shortcut, onClick, disabled }: {
  label: string;
  shortcut?: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        width: "100%",
        padding: "6px 14px",
        border: "none",
        background: "transparent",
        cursor: disabled ? "default" : "pointer",
        fontSize: "12px",
        color: disabled ? "var(--text-disabled, #aaa)" : "var(--text-primary)",
        textAlign: "left",
      }}
      onMouseEnter={(e) => {
        if (!disabled) e.currentTarget.style.background = "var(--bg-tertiary, #f0f0f0)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      <span>{label}</span>
      {shortcut && (
        <span style={{ fontSize: "11px", color: "var(--text-secondary, #999)", marginLeft: "20px" }}>
          {shortcut}
        </span>
      )}
    </button>
  );
}

function MenuDivider() {
  return <div style={{ height: "1px", background: "var(--border, #e0e0e0)", margin: "4px 0" }} />;
}
