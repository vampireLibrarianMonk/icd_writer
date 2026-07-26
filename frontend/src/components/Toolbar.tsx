import { useEditorStore } from "../store/editorStore";
import { api } from "../api/client";

export function Toolbar() {
  const { documentLoaded, editCount, undo, redo } = useEditorStore();

  const handleOpen = async () => {
    const path = prompt("Enter PDF path:");
    if (path) {
      await useEditorStore.getState().loadDocument(path);
    }
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
      <button onClick={handleOpen}>Open</button>
      <button onClick={handleSave} disabled={!documentLoaded}>Save</button>
      <button onClick={handleExport} disabled={!documentLoaded}>Export PDF</button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      <button onClick={undo} disabled={!documentLoaded}>Undo</button>
      <button onClick={redo} disabled={!documentLoaded}>Redo</button>
      <span style={{ borderLeft: "1px solid #ccc", height: "20px", margin: "0 8px" }} />
      {documentLoaded && (
        <span style={{ fontSize: "12px", color: "#666" }}>
          {editCount} edit{editCount !== 1 ? "s" : ""}
        </span>
      )}
    </div>
  );
}
