import { useEditorStore } from "../store/editorStore";
import { api } from "../api/client";
import { useRef, useState, useEffect } from "react";

interface DocInfo {
  path: string;
  filename: string;
  stem: string;
  indexed: boolean;
}

export function Toolbar() {
  const { documentLoaded, editCount, undo, redo, canUndo, canRedo, documentPath } = useEditorStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [darkMode, setDarkMode] = useState(false);
  const [availableDocs, setAvailableDocs] = useState<DocInfo[]>([]);

  // Load available documents on mount
  useEffect(() => {
    api.listDocuments().then((res) => {
      setAvailableDocs(res.documents || []);
    }).catch(() => {});
  }, []);

  const handleDocSwitch = async (path: string) => {
    if (path === documentPath) return;
    await useEditorStore.getState().loadDocument(path);
    // Refresh available docs (indexed status may change)
    api.listDocuments().then((res) => setAvailableDocs(res.documents || []));
  };

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.setAttribute("data-theme", !darkMode ? "dark" : "light");
  };

  const handleOpen = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Upload file to backend
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("http://localhost:8000/document/upload", {
      method: "POST",
      body: formData,
    });
    const result = await res.json();

    if (result.status === "ready" || result.saved_path) {
      await useEditorStore.getState().loadDocument(result.saved_path);
    }

    // Reset input so same file can be re-selected
    e.target.value = "";
  };

  const handleSave = async () => {
    await api.saveSession();
    alert("Session saved.");
  };

  const handleExport = async () => {
    // Direct download via hidden iframe to force save-as
    const origName = useEditorStore.getState().documentPath.split("/").pop()?.replace(".pdf", "") || "document";
    const exportName = `${origName}_edited.pdf`;

    // First trigger the export on backend
    await fetch("http://localhost:8000/document/export", { method: "POST" });

    // Then download via window.location (forces browser download behavior)
    window.location.href = `http://localhost:8000/document/export-download?filename=${encodeURIComponent(exportName)}`;
  };

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "8px 16px",
      borderBottom: "1px solid var(--border)",
      background: "var(--bg-secondary)",
    }}>
      <button onClick={toggleDarkMode} title="Toggle dark/light mode">
        {darkMode ? "☀️" : "🌙"}
      </button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        style={{ display: "none" }}
        onChange={handleFileSelected}
      />
      <button onClick={handleOpen}>Open</button>
      {availableDocs.length > 0 && (
        <select
          value={documentPath || ""}
          onChange={(e) => e.target.value && handleDocSwitch(e.target.value)}
          style={{
            fontSize: "12px",
            padding: "4px 6px",
            borderRadius: "4px",
            border: "1px solid var(--border)",
            maxWidth: "180px",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
          }}
          title="Switch between indexed documents"
        >
          <option value="">— Select Document —</option>
          {availableDocs.map((doc) => (
            <option key={doc.path} value={doc.path}>
              {doc.indexed ? "●" : "○"} {doc.filename}
            </option>
          ))}
        </select>
      )}
      <button onClick={handleSave} disabled={!documentLoaded}>Save</button>
      <button onClick={handleExport} disabled={!documentLoaded}>Export PDF</button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      <button onClick={undo} disabled={!canUndo}>Undo</button>
      <button onClick={redo} disabled={!canRedo}>Redo</button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      {documentLoaded && (
        <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
          {editCount} edit{editCount !== 1 ? "s" : ""}
        </span>
      )}
      <span style={{ flex: 1 }} />
    </div>
  );
}
