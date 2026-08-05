import { useEffect, useState } from "react";
import { useEditorStore } from "../store/editorStore";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface JournalEntry {
  id: string;
  timestamp: string;
  action_type: string;
  page: number | null;
  block_id: string | null;
  summary: string;
}

interface JournalData {
  session_id: string;
  document: string;
  entries: JournalEntry[];
  edit_count: number;
  undo_available: boolean;
  redo_available: boolean;
}

export function SessionPanel() {
  const [journal, setJournal] = useState<JournalData | null>(null);
  const [loading, setLoading] = useState(true);
  const refreshTrigger = useEditorStore((s) => s.refreshTrigger);
  const editCount = useEditorStore((s) => s.editCount);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/session/journal`)
      .then((r) => r.json())
      .then(setJournal)
      .catch(() => setJournal(null))
      .finally(() => setLoading(false));
  }, [refreshTrigger, editCount]);

  if (loading) {
    return <div style={{ padding: "16px", color: "var(--text-muted)" }}>Loading session...</div>;
  }

  if (!journal) {
    return <div style={{ padding: "16px", color: "var(--text-muted)" }}>No active session.</div>;
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  const getIcon = (type: string) => {
    switch (type) {
      case "document_opened": return "📂";
      case "block_edited": return "✏️";
      case "document_saved": return "💾";
      case "document_exported": return "📤";
      case "undo": return "↩️";
      case "redo": return "↪️";
      default: return "•";
    }
  };

  return (
    <div style={{ padding: "12px", overflow: "auto", height: "100%" }}>
      <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "12px" }}>
        <strong>Session:</strong> {journal.session_id}<br />
        <strong>Document:</strong> {journal.document.split("/").pop() || "none"}<br />
        <strong>Edits:</strong> {journal.edit_count} | <strong>Undo:</strong> {journal.undo_available ? "yes" : "no"} | <strong>Redo:</strong> {journal.redo_available ? "yes" : "no"}
      </div>

      <div style={{ fontSize: "11px", fontWeight: "bold", color: "var(--text-secondary)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
        Action Timeline
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {journal.entries.map((entry, idx) => (
          <div
            key={entry.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "12px",
              background: idx === journal.entries.length - 1 ? "var(--accent-light, rgba(33,150,243,0.08))" : "transparent",
            }}
          >
            <span style={{ fontSize: "14px" }}>{getIcon(entry.action_type)}</span>
            <span style={{ color: "var(--text-muted)", minWidth: "60px", fontFamily: "monospace", fontSize: "10px" }}>
              {formatTime(entry.timestamp)}
            </span>
            <span style={{ color: "var(--text-primary)", flex: 1 }}>
              {entry.summary}
            </span>
            {entry.page && (
              <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>
                p.{entry.page}
              </span>
            )}
          </div>
        ))}
        {journal.entries.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: "12px", padding: "8px" }}>
            No actions recorded yet. Make an edit to start.
          </div>
        )}
      </div>
    </div>
  );
}
