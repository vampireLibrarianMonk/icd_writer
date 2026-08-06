import { useEffect, useState } from "react";
import { useEditorStore } from "../store/editorStore";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface HFEntry {
  text: string;
  alignment: string;
  x: number;
  y: number;
  font: string;
  size: number;
}

interface HFData {
  page_number: number;
  header: HFEntry[];
  footer: HFEntry[];
}

export function HeaderFooterEditor({ section }: { section?: "header" | "footer" }) {
  const currentPage = useEditorStore((s) => s.currentPage);
  const totalPages = useEditorStore((s) => s.totalPages);
  const [hfData, setHfData] = useState<HFData | null>(null);
  const [editing, setEditing] = useState<{ section: string; index: number } | null>(null);
  const [editText, setEditText] = useState("");

  useEffect(() => {
    if (!totalPages || !currentPage) return;
    fetch(`${API_BASE}/document/page/${currentPage}/header-footer`)
      .then((r) => r.json())
      .then(setHfData)
      .catch(() => setHfData(null));
  }, [currentPage, totalPages]);

  if (!hfData || (!hfData.header.length && !hfData.footer.length)) {
    return null;
  }

  const handleEdit = (section: string, index: number, text: string) => {
    setEditing({ section, index });
    setEditText(text);
  };

  const handleSave = async () => {
    if (!editing || !hfData) return;
    // Update locally
    const newData = { ...hfData };
    if (editing.section === "header") {
      newData.header = [...hfData.header];
      newData.header[editing.index] = { ...newData.header[editing.index], text: editText };
    } else {
      newData.footer = [...hfData.footer];
      newData.footer[editing.index] = { ...newData.footer[editing.index], text: editText };
    }
    setHfData(newData);
    // Persist to backend
    const entry = editing.section === "header"
      ? hfData.header[editing.index]
      : hfData.footer[editing.index];
    if (entry) {
      try {
        const params = new URLSearchParams({
          section: editing.section,
          alignment: entry.alignment,
          new_text: editText,
        });
        const res = await fetch(
          `${API_BASE}/document/page/${currentPage}/header-footer?${params.toString()}`,
          { method: "PUT" }
        );
        if (res.ok) {
          useEditorStore.setState((s) => ({
            refreshTrigger: s.refreshTrigger + 1,
            editCount: s.editCount + 1,
          }));
        }
      } catch (e) {
        console.error("Header/footer edit failed:", e);
      }
    }
    setEditing(null);
  };

  const handleCancel = () => setEditing(null);

  const renderEntries = (entries: HFEntry[], section: string) => (
    <div style={{ display: "flex", gap: "8px", justifyContent: "space-between", marginBottom: "4px" }}>
      {["left", "center", "right"].map((align) => {
        const entry = entries.find((e) => e.alignment === align);
        const idx = entry ? entries.indexOf(entry) : -1;
        const isEditing = editing?.section === section && editing?.index === idx;

        return (
          <div
            key={align}
            style={{
              flex: 1,
              textAlign: align as any,
              padding: "4px",
              borderRadius: "3px",
              border: "1px solid var(--border)",
              background: "var(--input-bg)",
              minHeight: "24px",
              fontSize: "11px",
              cursor: entry ? "pointer" : "default",
              color: entry ? "var(--text-primary)" : "var(--text-muted)",
            }}
            onClick={() => entry && handleEdit(section, idx, entry.text)}
            title={entry ? `${align}: click to edit` : `${align}: empty`}
          >
            {isEditing ? (
              <div style={{ display: "flex", gap: "2px" }}>
                <input
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSave();
                    if (e.key === "Escape") handleCancel();
                  }}
                  autoFocus
                  style={{
                    flex: 1,
                    border: "1px solid var(--accent)",
                    borderRadius: "2px",
                    padding: "1px 4px",
                    fontSize: "11px",
                    background: "var(--input-bg)",
                    color: "var(--text-primary)",
                  }}
                />
                <button onClick={handleSave} style={{ fontSize: "9px", padding: "0 3px" }}>✓</button>
                <button onClick={handleCancel} style={{ fontSize: "9px", padding: "0 3px" }}>✗</button>
              </div>
            ) : (
              entry?.text || "—"
            )}
          </div>
        );
      })}
    </div>
  );

  return (
    <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
      {(!section || section === "header") && hfData.header.length > 0 && (
        <div style={{ marginBottom: "6px" }}>
          <div style={{ fontSize: "10px", fontWeight: "bold", color: "var(--text-secondary)", marginBottom: "2px" }}>
            HEADER
          </div>
          {renderEntries(hfData.header, "header")}
        </div>
      )}
      {(!section || section === "footer") && hfData.footer.length > 0 && (
        <div>
          <div style={{ fontSize: "10px", fontWeight: "bold", color: "var(--text-secondary)", marginBottom: "2px" }}>
            FOOTER
          </div>
          {renderEntries(hfData.footer, "footer")}
        </div>
      )}
    </div>
  );
}
