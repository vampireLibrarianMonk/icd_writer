import { useEffect, useState } from "react";
import { useEditorStore } from "../store/editorStore";

interface TableCell {
  text: string;
  block_id: string | null;
}

interface TableData {
  has_table: boolean;
  columns: number;
  rows: number;
  data: TableCell[][];
}

export function TableEditor() {
  const currentPage = useEditorStore((s) => s.currentPage);
  const totalPages = useEditorStore((s) => s.totalPages);
  const [tableData, setTableData] = useState<TableData | null>(null);
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const [cellText, setCellText] = useState("");

  useEffect(() => {
    if (!totalPages || !currentPage) {
      setTableData(null);
      return;
    }
    fetch(`http://localhost:8000/document/page/${currentPage}/table`)
      .then((res) => res.json())
      .then((data) => {
        setTableData(data);
      })
      .catch(() => setTableData(null));
  }, [currentPage, totalPages]);

  if (!tableData || !tableData.has_table) {
    return null;
  }

  const handleCellClick = (row: number, col: number) => {
    const cell = tableData.data[row][col];
    setEditingCell({ row, col });
    setCellText(cell.text);
  };

  const handleCellSave = async () => {
    if (!editingCell) return;
    const cell = tableData.data[editingCell.row][editingCell.col];
    if (cellText !== cell.text) {
      // Update locally
      const newData = { ...tableData };
      newData.data = [...tableData.data];
      newData.data[editingCell.row] = [...newData.data[editingCell.row]];
      newData.data[editingCell.row][editingCell.col] = { ...cell, text: cellText };
      setTableData(newData as TableData);

      // Persist via block edit if block_id exists, otherwise use table-cell endpoint
      if (cell.block_id) {
        await fetch(`http://localhost:8000/document/block/${cell.block_id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_text: cellText }),
        });
      } else {
        await fetch(
          `http://localhost:8000/document/table-cell?page=${currentPage}&old_text=${encodeURIComponent(cell.text)}&new_text=${encodeURIComponent(cellText)}`,
          { method: "PUT" }
        );
      }
    }
    setEditingCell(null);
  };

  const handleCellCancel = () => {
    setEditingCell(null);
  };

  return (
    <div style={{ padding: "12px", borderBottom: "1px solid #ddd", background: "#fafafa" }}>
      <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#333" }}>
        📋 Table ({tableData.rows} × {tableData.columns})
      </h4>
      <div style={{ overflow: "auto", maxHeight: "400px", border: "1px solid #ddd", borderRadius: "4px" }}>
        <table style={{ borderCollapse: "collapse", fontSize: "11px", width: "100%" }}>
          <tbody>
            {tableData.data.map((row, rowIdx) => (
              <tr key={rowIdx}>
                {row.map((cell, colIdx) => {
                  const isEditing =
                    editingCell?.row === rowIdx && editingCell?.col === colIdx;
                  const isHeader = rowIdx === 0;
                  return (
                    <td
                      key={colIdx}
                      onClick={() => handleCellClick(rowIdx, colIdx)}
                      style={{
                        border: "1px solid #ddd",
                        padding: "4px 6px",
                        cursor: "pointer",
                        background: isEditing
                          ? "#E3F2FD"
                          : isHeader
                          ? "#e8e8e8"
                          : "white",
                        fontWeight: isHeader ? "bold" : "normal",
                        minWidth: "50px",
                        maxWidth: "180px",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        verticalAlign: "top",
                      }}
                      title={cell.text}
                    >
                      {isEditing ? (
                        <div style={{ display: "flex", gap: "2px", alignItems: "center" }}>
                          <input
                            value={cellText}
                            onChange={(e) => setCellText(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleCellSave();
                              if (e.key === "Escape") handleCellCancel();
                            }}
                            autoFocus
                            style={{
                              width: "100%",
                              border: "1px solid #2196F3",
                              outline: "none",
                              padding: "2px 4px",
                              fontSize: "11px",
                              borderRadius: "2px",
                            }}
                          />
                          <button
                            onClick={handleCellSave}
                            style={{ fontSize: "10px", padding: "1px 4px", background: "#2196F3", color: "white", border: "none", borderRadius: "2px", cursor: "pointer" }}
                          >
                            ✓
                          </button>
                          <button
                            onClick={handleCellCancel}
                            style={{ fontSize: "10px", padding: "1px 4px", background: "#eee", border: "1px solid #ccc", borderRadius: "2px", cursor: "pointer" }}
                          >
                            ✗
                          </button>
                        </div>
                      ) : (
                        cell.text || "—"
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
