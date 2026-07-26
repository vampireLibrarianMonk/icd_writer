import { useEditorStore } from "../store/editorStore";

export function EditPanel() {
  const { selectedBlock, editText, setEditText, applyEdit, revertEdit } =
    useEditorStore();

  if (!selectedBlock) {
    return (
      <div style={{ width: "350px", padding: "16px", borderLeft: "1px solid #ddd", color: "#999" }}>
        <p>Click a text block on the page to select it for editing.</p>
      </div>
    );
  }

  const hasChanges = editText !== selectedBlock.text;

  return (
    <div style={{ width: "350px", padding: "16px", borderLeft: "1px solid #ddd", overflow: "auto" }}>
      <h3 style={{ margin: "0 0 12px 0", fontSize: "14px" }}>Edit Block</h3>

      {/* Text editor */}
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

      {/* Action buttons */}
      <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
        <button
          onClick={applyEdit}
          disabled={!hasChanges}
          style={{
            padding: "6px 16px",
            background: hasChanges ? "#2196F3" : "#ccc",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: hasChanges ? "pointer" : "default",
          }}
        >
          Apply
        </button>
        <button
          onClick={revertEdit}
          disabled={!hasChanges}
          style={{
            padding: "6px 16px",
            background: "#f5f5f5",
            border: "1px solid #ccc",
            borderRadius: "4px",
            cursor: hasChanges ? "pointer" : "default",
          }}
        >
          Revert
        </button>
      </div>

      {/* Metadata */}
      <div style={{ marginTop: "16px", fontSize: "12px", color: "#666" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            <tr>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: "bold" }}>Block ID</td>
              <td style={{ padding: "2px 0" }}>{selectedBlock.id}</td>
            </tr>
            <tr>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: "bold" }}>Type</td>
              <td style={{ padding: "2px 0" }}>{selectedBlock.type}</td>
            </tr>
            <tr>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: "bold" }}>Font Size</td>
              <td style={{ padding: "2px 0" }}>{selectedBlock.font_size?.toFixed(1) || "—"}pt</td>
            </tr>
            <tr>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: "bold" }}>Position</td>
              <td style={{ padding: "2px 0" }}>
                ({selectedBlock.bbox.x0.toFixed(0)}, {selectedBlock.bbox.y0.toFixed(0)})
              </td>
            </tr>
            <tr>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: "bold" }}>Confidence</td>
              <td style={{ padding: "2px 0" }}>{(selectedBlock.confidence * 100).toFixed(0)}%</td>
            </tr>
            <tr>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: "bold" }}>Source</td>
              <td style={{ padding: "2px 0" }}>{selectedBlock.is_ocr ? "OCR" : "Native"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Low confidence warning */}
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
    </div>
  );
}
