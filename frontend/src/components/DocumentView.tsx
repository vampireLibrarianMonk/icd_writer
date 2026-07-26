import { useEditorStore } from "../store/editorStore";
import { TextBlock } from "../api/client";

export function DocumentView() {
  const { pageData, currentPage, totalPages, selectedBlock, goToPage, selectBlock } =
    useEditorStore();

  if (!pageData) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#999" }}>
        No document loaded. Click Open to begin.
      </div>
    );
  }

  const scale = 0.75; // render at 75% of actual point size

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Page navigation */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px", borderBottom: "1px solid #eee" }}>
        <button onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1}>◀</button>
        <span>Page {currentPage} / {totalPages}</span>
        <button onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= totalPages}>▶</button>
      </div>

      {/* Page canvas with text block overlays */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px", background: "#e8e8e8" }}>
        <div
          style={{
            position: "relative",
            width: `${pageData.width_pt * scale}px`,
            height: `${pageData.height_pt * scale}px`,
            background: "white",
            margin: "0 auto",
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
          }}
        >
          {/* Text blocks as clickable overlays */}
          {pageData.blocks.map((block) => (
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
  const fontSize = Math.max(8, (block.font_size || 11) * scale);

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
          ? "rgba(33, 150, 243, 0.08)"
          : "transparent",
        cursor: "pointer",
        overflow: "hidden",
        fontSize: `${fontSize}px`,
        lineHeight: `${height}px`,
        whiteSpace: "nowrap",
        color: "#000",
        fontFamily: "serif",
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          (e.currentTarget as HTMLElement).style.border = "1px solid #90CAF9";
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          (e.currentTarget as HTMLElement).style.border = "1px solid transparent";
        }
      }}
      title={block.text}
    >
      {block.text}
    </div>
  );
}
