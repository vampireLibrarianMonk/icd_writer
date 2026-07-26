import { useEditorStore } from "../store/editorStore";
import { api } from "../api/client";
import { useRef } from "react";

export function Toolbar() {
  const { documentLoaded, editCount, undo, redo, canUndo, canRedo } = useEditorStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    const result = await api.exportPdf();
    alert(`Exported to: ${result.path}`);
  };

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "8px 16px",
      borderBottom: "1px solid #ddd",
      background: "#f8f9fa",
    }}>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        style={{ display: "none" }}
        onChange={handleFileSelected}
      />
      <button onClick={handleOpen}>Open</button>
      <button onClick={handleSave} disabled={!documentLoaded}>Save</button>
      <button onClick={handleExport} disabled={!documentLoaded}>Export PDF</button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      <button onClick={undo} disabled={!canUndo}>Undo</button>
      <button onClick={redo} disabled={!canRedo}>Redo</button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      {documentLoaded && (
        <span style={{ fontSize: "12px", color: "#666" }}>
          {editCount} edit{editCount !== 1 ? "s" : ""}
        </span>
      )}
    </div>
  );
}
