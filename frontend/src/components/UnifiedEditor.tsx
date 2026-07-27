import { useEditorStore } from "../store/editorStore";
import { useState, useEffect } from "react";

// Unified selection — any clickable element on the page
interface SelectedElement {
  type: "header" | "footer" | "table_cell" | "text_block";
  label: string; // human-readable label like "Header (left)" or "Table Row 3, Col 2"
  text: string;
  id: string | null; // block_id if available
  page: number;
  metadata: Record<string, string>;
}

export function UnifiedEditor({ width }: { width: number }) {
  const { currentPage, totalPages, documentLoaded } = useEditorStore();
  const [selected, setSelected] = useState<SelectedElement | null>(null);
  const [editText, setEditText] = useState("");
  const [pageElements, setPageElements] = useState<SelectedElement[]>([]);

  // Load all editable elements for the current page
  useEffect(() => {
    if (!documentLoaded || !currentPage) return;

    Promise.all([
      fetch(`http://localhost:8000/document/page/${currentPage}/header-footer`).then((r) => r.json()),
      fetch(`http://localhost:8000/document/page/${currentPage}/table`).then((r) => r.json()),
      fetch(`http://localhost:8000/document/page/${currentPage}`).then((r) => r.json()),
    ]).then(([hf, table, pageData]) => {
      const elements: SelectedElement[] = [];

      // Headers
      for (const h of hf.header || []) {
        elements.push({
          type: "header",
          label: `Header (${h.alignment})`,
          text: h.text,
          id: null,
          page: currentPage,
          metadata: { alignment: h.alignment, font: h.font, size: `${h.size}pt` },
        });
      }

      // Footers
      for (const f of hf.footer || []) {
        elements.push({
          type: "footer",
          label: `Footer (${f.alignment})`,
          text: f.text,
          id: null,
          page: currentPage,
          metadata: { alignment: f.alignment, font: f.font, size: `${f.size}pt` },
        });
      }

      // Table cells
      if (table.has_table) {
        for (let row = 0; row < table.data.length; row++) {
          for (let col = 0; col < table.data[row].length; col++) {
            const cell = table.data[row][col];
            if (cell.text) {
              elements.push({
                type: "table_cell",
                label: `Table Row ${row + 1}, Col ${col + 1}`,
                text: cell.text,
                id: cell.block_id,
                page: currentPage,
                metadata: { row: `${row + 1}`, col: `${col + 1}` },
              });
            }
          }
        }
      }

      // Text blocks (excluding those in header/footer/table regions)
      const headerY = 60;
      const footerY = 700;
      for (const block of pageData.blocks || []) {
        if (block.bbox.y0 < headerY || block.bbox.y0 > footerY) continue;
        // Skip if table covers this area
        if (table.has_table && block.bbox.y0 >= (table.row_y_min || 0) && block.bbox.y0 <= (table.row_y_max || 999)) continue;

        elements.push({
          type: "text_block",
          label: block.type === "heading" ? "Heading" : "Paragraph",
          text: block.text,
          id: block.id,
          page: currentPage,
          metadata: {
            type: block.type,
            font_size: block.font_size ? `${block.font_size}pt` : "—",
            confidence: `${(block.confidence * 100).toFixed(0)}%`,
          },
        });
      }

      setPageElements(elements);
    });

    setSelected(null);
    setEditText("");
  }, [currentPage, documentLoaded, totalPages]);

  const handleSelect = (elem: SelectedElement) => {
    setSelected(elem);
    setEditText(elem.text);
  };

  const handleApply = async () => {
    if (!selected || editText === selected.text) return;

    if (selected.id) {
      await fetch(`http://localhost:8000/document/block/${selected.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_text: editText }),
      });
    } else {
      // For header/footer/table cells without block_id, use table-cell endpoint
      await fetch(
        `http://localhost:8000/document/table-cell?page=${currentPage}&old_text=${encodeURIComponent(selected.text)}&new_text=${encodeURIComponent(editText)}`,
        { method: "PUT" }
      );
    }

    // Update local state
    setSelected({ ...selected, text: editText });

    // Update store
    const actions = await fetch("http://localhost:8000/session/actions").then((r) => r.json());
    useEditorStore.setState((state) => ({
      editCount: state.editCount + 1,
      canUndo: actions.undo_available,
      canRedo: actions.redo_available,
      refreshTrigger: state.refreshTrigger + 1,
    }));
  };

  const handleRevert = () => {
    if (selected) setEditText(selected.text);
  };

  if (!documentLoaded) {
    return (
      <div style={{ width: `${width}px`, padding: "16px", color: "var(--text-muted)", background: "var(--bg-panel)" }}>
        Open a document to begin editing.
      </div>
    );
  }

  return (
    <div style={{ width: `${width}px`, display: "flex", flexDirection: "column", background: "var(--bg-panel)", overflow: "hidden" }}>
      {/* Element list — scrollable */}
      <div style={{ flex: 1, overflow: "auto", borderBottom: selected ? "1px solid var(--border)" : "none" }}>
        <div style={{ padding: "8px" }}>
          <div style={{ fontSize: "11px", fontWeight: "bold", color: "var(--text-secondary)", marginBottom: "6px" }}>
            PAGE {currentPage} ELEMENTS
          </div>

          {/* Group by type */}
          {renderGroup("Headers & Footers", pageElements.filter((e) => e.type === "header" || e.type === "footer"), selected, handleSelect)}
          {renderGroup("Table Cells", pageElements.filter((e) => e.type === "table_cell"), selected, handleSelect)}
          {renderGroup("Text Blocks", pageElements.filter((e) => e.type === "text_block"), selected, handleSelect)}
        </div>
      </div>

      {/* Editor — shows when something is selected */}
      {selected && (
        <div style={{ padding: "12px", borderTop: "1px solid var(--border)" }}>
          <div style={{ fontSize: "11px", fontWeight: "bold", color: "var(--accent)", marginBottom: "4px" }}>
            {selected.label}
          </div>
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            style={{
              width: "100%",
              minHeight: "80px",
              padding: "6px",
              fontSize: "12px",
              fontFamily: "serif",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              background: "var(--input-bg)",
              color: "var(--text-primary)",
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: "6px", marginTop: "6px" }}>
            <button
              onClick={handleApply}
              disabled={editText === selected.text}
              style={{
                padding: "4px 12px",
                background: editText !== selected.text ? "var(--accent)" : "var(--border)",
                color: "white",
                border: "none",
                borderRadius: "3px",
                fontSize: "12px",
                cursor: editText !== selected.text ? "pointer" : "default",
              }}
            >
              Apply
            </button>
            <button
              onClick={handleRevert}
              disabled={editText === selected.text}
              style={{ padding: "4px 12px", fontSize: "12px" }}
            >
              Revert
            </button>
          </div>
          {/* Metadata */}
          <div style={{ marginTop: "8px", fontSize: "10px", color: "var(--text-muted)" }}>
            {Object.entries(selected.metadata).map(([k, v]) => (
              <span key={k} style={{ marginRight: "10px" }}><b>{k}:</b> {v}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function renderGroup(
  title: string,
  items: any[],
  selected: any,
  onSelect: (item: any) => void
) {
  if (!items.length) return null;
  return (
    <div style={{ marginBottom: "8px" }}>
      <div style={{ fontSize: "10px", color: "var(--text-muted)", marginBottom: "2px", textTransform: "uppercase" }}>
        {title} ({items.length})
      </div>
      {items.map((item, i) => (
        <div
          key={`${item.type}-${i}`}
          onClick={() => onSelect(item)}
          style={{
            padding: "4px 6px",
            marginBottom: "2px",
            borderRadius: "3px",
            cursor: "pointer",
            fontSize: "11px",
            background: selected === item ? "var(--accent-light)" : "transparent",
            border: selected === item ? "1px solid var(--accent)" : "1px solid transparent",
            color: "var(--text-primary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={item.text}
        >
          <span style={{ color: "var(--text-muted)", marginRight: "4px" }}>{item.label}:</span>
          {item.text.slice(0, 40)}
        </div>
      ))}
    </div>
  );
}
