import { useEditorStore } from "../store/editorStore";
import type { TextBlock } from "../api/client";
import { useEffect, useState } from "react";

export function DocumentView() {
  const { pageData, currentPage, totalPages, selectedBlock, goToPage, selectBlock } =
    useEditorStore();
  const [hasTable, setHasTable] = useState(false);
  const [tableYRange, setTableYRange] = useState<[number, number]>([0, 0]);

  // Check if current page has a table and get its y-range
  useEffect(() => {
    if (!totalPages || !currentPage) return;
    fetch(`http://localhost:8000/document/page/${currentPage}/table`)
      .then((res) => res.json())
      .then((data) => {
        if (data.has_table && data.data?.length > 0) {
          setHasTable(true);
          // Get the y-range of the table from row positions
          if (data.row_y_min !== undefined) {
            setTableYRange([data.row_y_min, data.row_y_max]);
          } else {
            setTableYRange([100, 400]); // fallback estimate
          }
        } else {
          setHasTable(false);
        }
      })
      .catch(() => setHasTable(false));
  }, [currentPage, totalPages]);

  if (!pageData) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#999" }}>
        No document loaded. Click Open to begin.
      </div>
    );
  }

  const scale = 0.75;
  const pageImageUrl = `http://localhost:8000/document/page/${currentPage}/image`;

  // Filter out blocks that are in the table area (let table editor handle those)
  // Keep blocks outside the table y-range clickable
  const visibleBlocks = hasTable
    ? pageData.blocks.filter((b) => {
        // Hide blocks whose y0 falls within the table region
        return b.bbox.y0 < tableYRange[0] || b.bbox.y0 > tableYRange[1];
      })
    : pageData.blocks;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Page navigation */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px", borderBottom: "1px solid #eee" }}>
        <button onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1}>◀</button>
        <span>Page {currentPage} / {totalPages}</span>
        <button onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= totalPages}>▶</button>
      </div>

      {/* Page with image background and text block overlays */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px", background: "#e8e8e8" }}>
        <div
          style={{
            position: "relative",
            width: `${pageData.width_pt * scale}px`,
            height: `${pageData.height_pt * scale}px`,
            margin: "0 auto",
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
          }}
        >
          {/* Page image as background */}
          <img
            src={pageImageUrl}
            alt={`Page ${currentPage}`}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
            }}
            draggable={false}
          />

          {/* Text blocks as clickable overlays (disabled on table pages) */}
          {visibleBlocks.map((block) => (
            <BlockOverlay
              key={block.id}
              block={block}
              scale={scale}
              isSelected={selectedBlock?.id === block.id}
              onClick={() => selectBlock(block)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function BlockOverlay({
  block,
  scale,
  isSelected,
  onClick,
}: {
  block: TextBlock;
  scale: number;
  isSelected: boolean;
  onClick: () => void;
}) {
  const width = (block.bbox.x1 - block.bbox.x0) * scale;
  const height = (block.bbox.y1 - block.bbox.y0) * scale;

  return (
    <div
      onClick={onClick}
      style={{
        position: "absolute",
        left: `${block.bbox.x0 * scale}px`,
        top: `${block.bbox.y0 * scale}px`,
        width: `${width}px`,
        height: `${height}px`,
        border: isSelected
          ? "2px solid #2196F3"
          : "1px solid transparent",
        background: isSelected
          ? "rgba(33, 150, 243, 0.15)"
          : "transparent",
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          (e.currentTarget as HTMLElement).style.background = "rgba(33, 150, 243, 0.05)";
          (e.currentTarget as HTMLElement).style.border = "1px solid #90CAF9";
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          (e.currentTarget as HTMLElement).style.background = "transparent";
          (e.currentTarget as HTMLElement).style.border = "1px solid transparent";
        }
      }}
      title={block.text}
    />
  );
}
