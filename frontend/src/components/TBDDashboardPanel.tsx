import { useState, useEffect } from "react";
import { api } from "../api/client";
import { useEditorStore } from "../store/editorStore";

interface TBDStats {
  total_items: number;
  open_count: number;
  assigned_count: number;
  resolved_count: number;
  verified_count: number;
  tbd_count: number;
  tbr_count: number;
  in_shall_statements: number;
  correlated_pairs: number;
  conflicts: number;
  documents_count: number;
}

interface TBDItemData {
  item_id: string;
  item_type: string;
  status: string;
  document_title: string;
  page_number: number;
  section_heading: string | null;
  context: string;
  owner: string | null;
  in_shall_statement: boolean;
  correlated_items: string[];
  resolution_value: string | null;
}

interface Correlation {
  item_a_id: string;
  item_b_id: string;
  confidence: string;
  conflict: boolean;
  conflict_detail: string | null;
}

export function TBDDashboard() {
  const [stats, setStats] = useState<TBDStats | null>(null);
  const [items, setItems] = useState<TBDItemData[]>([]);
  const [correlations, setCorrelations] = useState<Correlation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterType, setFilterType] = useState<string>("");

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const filters: any = {};
      if (filterStatus) filters.status = filterStatus;
      if (filterType) filters.item_type = filterType;
      const data = await api.getTbdDashboard(filters);
      setStats(data.stats);
      setItems(data.items);
      setCorrelations(data.correlations || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load TBD data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [filterStatus, filterType]);

  const handleIngest = async () => {
    setLoading(true);
    try {
      const result = await api.ingestTbdDocuments();
      alert(`Ingested ${result.new_items} new TBD items from ${result.total_files} documents.`);
      await loadData();
    } catch (e) {
      setError("Ingestion failed");
    }
  };

  const handleStatusChange = async (itemId: string, newStatus: string) => {
    try {
      await api.updateTbdItem(itemId, { status: newStatus });
      await loadData();
    } catch (e) {
      setError("Update failed");
    }
  };

  const handleNavigateToItem = async (item: TBDItemData) => {
    const { totalPages, goToPage, documentLoaded, documentPath } = useEditorStore.getState();

    if (!documentLoaded) {
      // No doc loaded — try to find and open the matching one
      const confirmed = window.confirm(
        `No document is loaded.\n\nOpen "${item.document_title}" to navigate to this ${item.item_type} item?`
      );
      if (confirmed) {
        await switchToDocument(item.document_title, item.page_number, item.context);
      }
      return;
    }

    // Check if this item is from the currently-loaded document
    const loadedDocName = documentPath.split("/").pop()?.replace(".pdf", "").toLowerCase() || "";
    const itemDocName = item.document_title.toLowerCase();
    const isCurrentDoc = itemDocName.includes(loadedDocName) || loadedDocName.includes(itemDocName.slice(0, 10));

    if (!isCurrentDoc || item.page_number > totalPages) {
      // Offer to switch documents
      const confirmed = window.confirm(
        `This ${item.item_type} is on page ${item.page_number} of "${item.document_title}".\n\n` +
        `Switch to that document?`
      );
      if (confirmed) {
        await switchToDocument(item.document_title, item.page_number, item.context);
      }
      return;
    }

    // Same document — navigate directly
    goToPage(item.page_number);
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("navigate-to-tbd", {
        detail: { page: item.page_number, context: item.context, itemId: item.item_id, itemType: item.item_type },
      }));
    }, 300);
  };

  const switchToDocument = async (docTitle: string, page: number, context: string) => {
    try {
      // Find the matching PDF path — match by title, filename, or stem
      const docsRes = await api.listDocuments();
      const docs = docsRes.documents || [];
      const titleLower = docTitle.toLowerCase();

      const match = docs.find((d: any) => {
        const stemLower = d.stem.toLowerCase();
        const filenameLower = d.filename.toLowerCase();
        const pdfTitle = (d.title || "").toLowerCase();
        // Match if: TBD's document_title matches the PDF's metadata title
        if (pdfTitle && titleLower.includes(pdfTitle.slice(0, 15))) return true;
        if (pdfTitle && pdfTitle.includes(titleLower.slice(0, 15))) return true;
        // Or matches filename/stem
        if (titleLower.includes(stemLower)) return true;
        if (filenameLower.includes(titleLower.slice(0, 10))) return true;
        return false;
      });

      if (!match) {
        alert(`Could not find a PDF matching "${docTitle}" in the documents folder.`);
        return;
      }

      // Open the document
      await useEditorStore.getState().loadDocument(match.path);

      // Navigate to the page after load
      setTimeout(() => {
        useEditorStore.getState().goToPage(page);
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("navigate-to-tbd", {
            detail: { page, context, itemId: "", itemType: "" },
          }));
        }, 300);
      }, 500);
    } catch (e) {
      alert("Failed to switch document.");
    }
  };

  if (loading && !stats) {
    return <div style={{ padding: "20px", textAlign: "center" }}>Loading TBD Dashboard...</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ marginBottom: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>TBD Dashboard</h3>
          <button onClick={handleIngest} style={{ fontSize: "11px", padding: "4px 8px" }}>
            🔄 Refresh
          </button>
        </div>
        <p style={{ margin: "4px 0 0", fontSize: "11px", color: "var(--text-secondary)" }}>
          Cross-document TBD/TBR tracking
        </p>
      </div>

      {/* Stats cards */}
      {stats && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "8px",
          marginBottom: "12px",
        }}>
          <StatCard label="Open" value={stats.open_count} color="#e53935" />
          <StatCard label="Assigned" value={stats.assigned_count} color="#fb8c00" />
          <StatCard label="Resolved" value={stats.resolved_count} color="#43a047" />
          <StatCard label="Total" value={stats.total_items} color="#1565c0" />
        </div>
      )}

      {/* Warnings */}
      {stats && stats.in_shall_statements > 0 && (
        <div style={{
          background: "#fff3e0",
          borderRadius: "4px",
          padding: "6px 10px",
          fontSize: "11px",
          marginBottom: "8px",
          color: "#e65100",
        }}>
          ⚠️ {stats.in_shall_statements} item{stats.in_shall_statements > 1 ? "s" : ""} in "shall" statements (contractually blocking)
        </div>
      )}

      {stats && stats.conflicts > 0 && (
        <div style={{
          background: "#ffebee",
          borderRadius: "4px",
          padding: "6px 10px",
          fontSize: "11px",
          marginBottom: "8px",
          color: "#c62828",
        }}>
          ⚠️ {stats.conflicts} cross-document conflict{stats.conflicts > 1 ? "s" : ""} detected
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          style={{ fontSize: "11px", padding: "4px 6px", borderRadius: "4px", border: "1px solid var(--border)" }}
        >
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="assigned">Assigned</option>
          <option value="resolved">Resolved</option>
          <option value="verified">Verified</option>
        </select>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          style={{ fontSize: "11px", padding: "4px 6px", borderRadius: "4px", border: "1px solid var(--border)" }}
        >
          <option value="">All Types</option>
          <option value="TBD">TBD</option>
          <option value="TBR">TBR</option>
        </select>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: "11px", color: "var(--text-secondary)", alignSelf: "center" }}>
          {items.length} items
        </span>
      </div>

      {/* Item list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {error && (
          <div style={{ color: "#d32f2f", fontSize: "12px", padding: "8px" }}>{error}</div>
        )}

        {items.length === 0 && !loading && (
          <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-secondary)", fontSize: "12px" }}>
            <p>No TBD items found.</p>
            <p>Click 🔄 Refresh to scan indexed documents.</p>
          </div>
        )}

        {items.map((item) => (
          <TBDItemRow
            key={item.item_id}
            item={item}
            onStatusChange={handleStatusChange}
            onNavigate={handleNavigateToItem}
          />
        ))}

        {/* Correlations section */}
        {correlations.length > 0 && (
          <div style={{ marginTop: "16px", borderTop: "1px solid var(--border)", paddingTop: "12px" }}>
            <h4 style={{ fontSize: "12px", margin: "0 0 8px" }}>
              Cross-Document Correlations ({correlations.length})
            </h4>
            {correlations.map((corr, i) => (
              <div key={i} style={{
                padding: "6px 8px",
                margin: "4px 0",
                background: corr.conflict ? "#ffebee" : "var(--bg-secondary)",
                borderRadius: "4px",
                fontSize: "11px",
              }}>
                <span style={{ fontWeight: 500 }}>{corr.item_a_id}</span>
                {" ↔ "}
                <span style={{ fontWeight: 500 }}>{corr.item_b_id}</span>
                <span style={{ marginLeft: "8px", color: "var(--text-secondary)" }}>
                  ({corr.confidence})
                </span>
                {corr.conflict && (
                  <span style={{ marginLeft: "8px", color: "#c62828", fontWeight: 500 }}>
                    ⚠️ CONFLICT
                  </span>
                )}
                {corr.conflict_detail && (
                  <div style={{ marginTop: "2px", color: "#c62828" }}>
                    {corr.conflict_detail}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      background: "var(--bg-secondary)",
      borderRadius: "6px",
      padding: "8px",
      textAlign: "center",
      borderTop: `3px solid ${color}`,
    }}>
      <div style={{ fontSize: "18px", fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: "10px", color: "var(--text-secondary)" }}>{label}</div>
    </div>
  );
}

function TBDItemRow({ item, onStatusChange, onNavigate }: { item: TBDItemData; onStatusChange: (id: string, status: string) => void; onNavigate: (item: TBDItemData) => void }) {
  const statusColors: Record<string, string> = {
    open: "#e53935",
    assigned: "#fb8c00",
    resolved: "#43a047",
    verified: "#1565c0",
  };

  // All items are clickable — dialog handles cross-document navigation
  const isNavigable = true;

  return (
    <div
      onClick={() => onNavigate(item)}
      style={{
        padding: "8px 10px",
        margin: "4px 0",
        background: "var(--bg-secondary)",
        borderRadius: "6px",
        borderLeft: `3px solid ${statusColors[item.status] || "#999"}`,
        fontSize: "12px",
        cursor: isNavigable ? "pointer" : "default",
        opacity: isNavigable ? 1 : 0.7,
        transition: "box-shadow 0.15s",
      }}
      onMouseEnter={(e) => { if (isNavigable) (e.currentTarget as HTMLElement).style.boxShadow = "0 1px 4px rgba(0,0,0,0.12)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
      title={isNavigable ? "Click to navigate to this item in the document" : `From "${item.document_title}" — open that document to navigate`}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
        {/* Type badge */}
        <span style={{
          padding: "1px 5px",
          borderRadius: "3px",
          fontSize: "10px",
          fontWeight: 600,
          background: item.item_type === "TBD" ? "#e3f2fd" : "#f3e5f5",
          color: item.item_type === "TBD" ? "#1565c0" : "#7b1fa2",
        }}>
          {item.item_type}
        </span>

        {/* Shall warning */}
        {item.in_shall_statement && (
          <span style={{ fontSize: "10px", color: "#e65100" }} title="In a 'shall' statement — contractually blocking">
            ⚠️ SHALL
          </span>
        )}

        {/* Document and page */}
        <span style={{ color: "var(--text-secondary)", fontSize: "11px" }}>
          {!isNavigable && <span title="Different document">📄 </span>}
          {item.document_title.slice(0, 20)} p{item.page_number}
        </span>

        <span style={{ flex: 1 }} />

        {/* Status selector */}
        <select
          value={item.status}
          onChange={(e) => onStatusChange(item.item_id, e.target.value)}
          onClick={(e) => e.stopPropagation()}
          style={{
            fontSize: "10px",
            padding: "2px 4px",
            borderRadius: "3px",
            border: "1px solid var(--border)",
            color: statusColors[item.status],
            fontWeight: 500,
          }}
        >
          <option value="open">Open</option>
          <option value="assigned">Assigned</option>
          <option value="resolved">Resolved</option>
          <option value="verified">Verified</option>
        </select>
      </div>

      {/* Context */}
      <div style={{ color: "var(--text-secondary)", fontSize: "11px", fontFamily: "monospace" }}>
        {item.context.slice(0, 100)}{item.context.length > 100 ? "..." : ""}
      </div>

      {/* Owner */}
      {item.owner && (
        <div style={{ fontSize: "10px", marginTop: "4px", color: "var(--text-secondary)" }}>
          Owner: <span style={{ fontWeight: 500 }}>{item.owner}</span>
        </div>
      )}
    </div>
  );
}
