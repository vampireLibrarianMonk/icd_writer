import { useEditorStore } from "../store/editorStore";

export function StatusBar() {
  const { documentLoaded, documentPath, totalPages, currentPage, editCount, sessionId } =
    useEditorStore();

  if (!documentLoaded) {
    return (
      <div style={{
        padding: "4px 16px",
        borderTop: "1px solid #ddd",
        background: "#f8f9fa",
        fontSize: "12px",
        color: "#666",
      }}>
        Ready
      </div>
    );
  }

  const filename = documentPath.split("/").pop() || documentPath;

  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      padding: "4px 16px",
      borderTop: "1px solid var(--border)",
      background: "var(--bg-secondary)",
      fontSize: "12px",
      color: "var(--text-secondary)",
    }}>
      <span>
        {filename} — {totalPages} pages — Page {currentPage}
      </span>
      <span>
        {editCount > 0 && `${editCount} unsaved edit${editCount > 1 ? "s" : ""} · `}
        Session: {sessionId?.slice(0, 8)}
      </span>
    </div>
  );
}
