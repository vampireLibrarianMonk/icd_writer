import { useEditorStore } from "../store/editorStore";
import { TableEditor } from "./TableEditor";

export function EditPanel({ width }: { width: number }) {
  const { selectedBlock, editText, setEditText, applyEdit, revertEdit, documentLoaded } =
    useEditorStore();

  return (
    <div style={{ width: `${width}px`, borderLeft: "none", overflow: "auto", display: "flex", flexDirection: "column" }}>
      {/* Table editor at the top — most important for table pages */}
      {documentLoaded && <TableEditor />}

      {/* Block editor below */}
      <div style={{ padding: "16px" }}>
        {!selectedBlock ? (
          <p style={{ color: "#999", fontSize: "13px" }}>
            Click a text block on the page to edit, or use the table above.
          </p>
        ) : (
          <>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "14px" }}>Edit Block</h3>

            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              style={{
                width: "100%",
                minHeight: "120px",
                padding: "8px",
                fontFamily: "serif",
                fontSize: "13px",
                border: "1px solid #ccc",
                borderRadius: "4px",
                resize: "vertical",
              }}
            />

            <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
              <button
                onClick={applyEdit}
                disabled={editText === selectedBlock.text}
                style={{
                  padding: "6px 16px",
                  background: editText !== selectedBlock.text ? "#2196F3" : "#ccc",
                  color: "white",
                  border: "none",
                  borderRadius: "4px",
                  cursor: editText !== selectedBlock.text ? "pointer" : "default",
                }}
              >
                Apply
              </button>
              <button
                onClick={revertEdit}
                disabled={editText === selectedBlock.text}
                style={{
                  padding: "6px 16px",
                  background: "#f5f5f5",
                  border: "1px solid #ccc",
                  borderRadius: "4px",
                  cursor: editText !== selectedBlock.text ? "pointer" : "default",
                }}
              >
                Revert
              </button>
            </div>

            <div style={{ marginTop: "12px", fontSize: "11px", color: "#666" }}>
              <div><b>ID:</b> {selectedBlock.id}</div>
              <div><b>Type:</b> {selectedBlock.type}</div>
              <div><b>Font:</b> {selectedBlock.font_size?.toFixed(1) || "—"}pt</div>
              <div><b>Confidence:</b> {(selectedBlock.confidence * 100).toFixed(0)}%</div>
              <div><b>Source:</b> {selectedBlock.is_ocr ? "OCR" : "Native"}</div>
            </div>

            {selectedBlock.confidence < 0.8 && (
              <div style={{
                marginTop: "12px",
                padding: "8px",
                background: "#FFF3E0",
                border: "1px solid #FFB74D",
                borderRadius: "4px",
                fontSize: "12px",
              }}>
                ⚠️ Low OCR confidence — verify this text is correct.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
