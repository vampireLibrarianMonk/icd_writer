import { useEffect, useState } from "react";
import { useEditorStore } from "../store/editorStore";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface TableCell {
  text: string;
  block_id: string | null;
}

interface TableData {
  has_table: boolean;
  columns: number;
  rows: number;
  data: TableCell[][];
  row_y_min?: number;
  row_y_max?: number;
}

interface TableZone {
  y_min: number;
  y_max: number;
  label: string;
}

export function TableEditor({ yMin, yMax }: { yMin?: number; yMax?: number }) {
  const currentPage = useEditorStore((s) => s.currentPage);
  const totalPages = useEditorStore((s) => s.totalPages);
  const refreshTrigger = useEditorStore((s) => s.refreshTrigger);

  // Auto-detect table zones if no yMin/yMax provided
  const [zones, setZones] = useState<TableZone[]>([]);
  const [activeZoneIdx, setActiveZoneIdx] = useState<number>(0);
  const isAutoDetect = yMin === undefined && yMax === undefined;

  const [tableData, setTableData] = useState<TableData | null>(null);
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const [cellText, setCellText] = useState("");
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [hasStructuralChanges, setHasStructuralChanges] = useState(false);

  // Fetch table zones for auto-detect mode
  useEffect(() => {
    if (!isAutoDetect || !totalPages || !currentPage) {
      setZones([]);
      return;
    }
    fetch(`${API_BASE}/document/page/${currentPage}/table-zones`)
      .then((r) => r.json())
      .then((data) => {
        const z = (data.zones || []).map((zone: { y_min: number; y_max: number }, idx: number) => ({
          ...zone,
          label: `Table ${idx + 1}`,
        }));
        setZones(z);
        setActiveZoneIdx(0);
      })
      .catch(() => setZones([]));
  }, [currentPage, totalPages, refreshTrigger, isAutoDetect]);

  // Determine effective y bounds
  const effectiveYMin = isAutoDetect
    ? (zones[activeZoneIdx]?.y_min ?? 0)
    : (yMin ?? 0);
  const effectiveYMax = isAutoDetect
    ? (zones[activeZoneIdx]?.y_max ?? 9999)
    : (yMax ?? 9999);

  // Fetch table data for the active zone
  useEffect(() => {
    if (!totalPages || !currentPage) {
      setTableData(null);
      return;
    }
    if (isAutoDetect && zones.length === 0) {
      setTableData(null);
      return;
    }
    fetch(`${API_BASE}/document/page/${currentPage}/table?y_min=${effectiveYMin}&y_max=${effectiveYMax}`)
      .then((r) => r.json())
      .then((data) => {
        setTableData(data);
        setSelectedRow(null);
        setEditingCell(null);
      })
      .catch(() => setTableData(null));
  }, [currentPage, totalPages, refreshTrigger, effectiveYMin, effectiveYMax]);

  // If no tables detected, show nothing
  if (isAutoDetect && zones.length === 0) {
    return null;
  }
  if (!tableData || !tableData.has_table) {
    return null;
  }

  const handleCellClick = (row: number, col: number) => {
    setEditingCell({ row, col });
    setCellText(tableData.data[row][col].text);
    setSelectedRow(row);
  };

  const handleCellSave = async () => {
    if (!editingCell || !tableData) return;
    const cell = tableData.data[editingCell.row][editingCell.col];
    if (cellText !== cell.text) {
      // Update local state
      const newData = { ...tableData };
      newData.data = [...tableData.data];
      newData.data[editingCell.row] = [...newData.data[editingCell.row]];
      newData.data[editingCell.row][editingCell.col] = { ...cell, text: cellText };
      setTableData(newData as TableData);

      // Use table-rebuild for all cell edits (atomic, avoids positioning bugs)
      setSaving(true);
      try {
        const data2d = newData.data.map((row) => row.map((c) => c.text));
        const res = await fetch(`${API_BASE}/document/page/${currentPage}/table-rebuild`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            y_min: newData.row_y_min ?? effectiveYMin,
            y_max: newData.row_y_max ?? effectiveYMax,
            data: data2d,
          }),
        });

        if (res.ok) {
          const actions = await fetch(`${API_BASE}/session/actions`).then((r) => r.json());
          useEditorStore.setState({
            editCount: useEditorStore.getState().editCount + 1,
            canUndo: actions.undo_available,
            canRedo: actions.redo_available,
            refreshTrigger: Date.now(),
          });
        }
      } finally {
        setSaving(false);
      }
    }
    setEditingCell(null);
  };

  const handleCellCancel = () => {
    setEditingCell(null);
  };

  const handleAddRow = () => {
    if (!tableData) return;
    const newRow: TableCell[] = Array(tableData.columns)
      .fill(null)
      .map(() => ({ text: "", block_id: null }));
    const newData = {
      ...tableData,
      data: [...tableData.data, newRow],
      rows: tableData.rows + 1,
    };
    setTableData(newData);
    setHasStructuralChanges(true);
    const newRowIdx = newData.data.length - 1;
    setSelectedRow(newRowIdx);
    setEditingCell({ row: newRowIdx, col: 0 });
    setCellText("");
  };

  const handleDeleteRow = () => {
    if (!tableData || selectedRow === null) return;
    if (selectedRow === 0) return; // Don't delete header
    const newData = {
      ...tableData,
      data: tableData.data.filter((_, idx) => idx !== selectedRow),
      rows: tableData.rows - 1,
    };
    setTableData(newData);
    setHasStructuralChanges(true);
    setSelectedRow(null);
    setEditingCell(null);
  };

  const handleApplyChanges = async () => {
    if (!tableData) return;
    setSaving(true);

    try {
      const res = await fetch(`${API_BASE}/document/page/${currentPage}/table-rebuild`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          y_min: tableData.row_y_min ?? effectiveYMin,
          y_max: tableData.row_y_max ?? effectiveYMax,
          data: tableData.data.map((row) => row.map((cell) => cell.text)),
        }),
      });

      if (res.ok) {
        const actions = await fetch(`${API_BASE}/session/actions`).then((r) => r.json());
        useEditorStore.setState({
          editCount: useEditorStore.getState().editCount + 1,
          canUndo: actions.undo_available,
          canRedo: actions.redo_available,
          refreshTrigger: Date.now(),
        });
        setHasStructuralChanges(false);
      } else {
        const err = await res.json().catch(() => ({ detail: "Rebuild failed" }));
        console.error("Table rebuild failed:", err);
      }
    } catch (e) {
      console.error("Table rebuild failed:", e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
      {/* Zone selector dropdown (only in auto-detect mode with multiple tables) */}
      {isAutoDetect && zones.length > 1 && (
        <select
          value={activeZoneIdx}
          onChange={(e) => setActiveZoneIdx(Number(e.target.value))}
          style={{
            width: "100%",
            marginBottom: "8px",
            fontSize: "12px",
            padding: "4px 8px",
            borderRadius: "4px",
            border: "1px solid var(--border)",
            background: "var(--input-bg, #fff)",
            color: "var(--text-primary)",
          }}
        >
          {zones.map((z, idx) => (
            <option key={idx} value={idx}>
              {z.label} (y: {z.y_min} - {z.y_max})
            </option>
          ))}
        </select>
      )}

      {/* Header with row controls */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
        <h4 style={{ margin: 0, fontSize: "13px", color: "var(--text-primary)" }}>
          {isAutoDetect && zones.length === 1 ? zones[0].label + " " : ""}
          ({tableData.data.length} x {tableData.columns})
        </h4>
        <div style={{ display: "flex", gap: "4px" }}>
          <button
            onClick={handleAddRow}
            style={{
              fontSize: "11px",
              padding: "3px 8px",
              background: "#4caf50",
              color: "white",
              border: "none",
              borderRadius: "3px",
              cursor: "pointer",
            }}
            title="Add a new empty row at the bottom"
          >
            + Row
          </button>
          <button
            onClick={handleDeleteRow}
            disabled={selectedRow === null || selectedRow === 0}
            style={{
              fontSize: "11px",
              padding: "3px 8px",
              background: selectedRow !== null && selectedRow !== 0 ? "#f44336" : "#ccc",
              color: "white",
              border: "none",
              borderRadius: "3px",
              cursor: selectedRow !== null && selectedRow !== 0 ? "pointer" : "default",
            }}
            title="Delete the selected row (click a row first)"
          >
            - Row
          </button>
        </div>
      </div>

      {/* Table grid */}
      <div style={{ overflow: "auto", maxHeight: "400px", border: "1px solid var(--border)", borderRadius: "4px" }}>
        <table style={{ borderCollapse: "collapse", fontSize: "11px", width: "100%" }}>
          <tbody>
            {tableData.data.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                onClick={() => setSelectedRow(rowIdx)}
                style={{
                  background: selectedRow === rowIdx ? "rgba(33,150,243,0.08)" : undefined,
                }}
              >
                {row.map((cell, colIdx) => {
                  const isEditing =
                    editingCell?.row === rowIdx && editingCell?.col === colIdx;
                  const isHeader = rowIdx === 0;
                  return (
                    <td
                      key={colIdx}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCellClick(rowIdx, colIdx);
                      }}
                      style={{
                        border: "1px solid var(--border)",
                        padding: "4px 6px",
                        cursor: "pointer",
                        background: isEditing
                          ? "var(--accent-light, #e3f2fd)"
                          : isHeader
                          ? "var(--table-header, #f0f4f8)"
                          : "var(--table-cell, #fff)",
                        fontWeight: isHeader ? "bold" : "normal",
                        color: "var(--text-primary)",
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
                              border: "1px solid var(--accent, #2196F3)",
                              outline: "none",
                              padding: "2px 4px",
                              fontSize: "11px",
                              borderRadius: "2px",
                              background: "var(--input-bg, #fff)",
                              color: "var(--text-primary)",
                            }}
                          />
                          <button
                            onClick={handleCellSave}
                            style={{ fontSize: "10px", padding: "1px 4px", background: "#2196F3", color: "white", border: "none", borderRadius: "2px", cursor: "pointer" }}
                          >
                            OK
                          </button>
                          <button
                            onClick={handleCellCancel}
                            style={{ fontSize: "10px", padding: "1px 4px", background: "#eee", border: "1px solid #ccc", borderRadius: "2px", cursor: "pointer" }}
                          >
                            X
                          </button>
                        </div>
                      ) : (
                        cell.text || "\u2014"
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Apply button — only active after structural changes (add/delete row) */}
      {hasStructuralChanges && (
      <button
        onClick={handleApplyChanges}
        disabled={saving}
        style={{
          marginTop: "8px",
          width: "100%",
          fontSize: "12px",
          padding: "6px 12px",
          background: saving ? "#ccc" : "#4caf50",
          color: "white",
          border: "none",
          borderRadius: "4px",
          cursor: saving ? "default" : "pointer",
          fontWeight: 500,
        }}
      >
        {saving ? "Applying..." : "Apply Table Changes"}
      </button>
      )}
    </div>
  );
}
