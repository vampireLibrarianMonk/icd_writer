import { useEditorStore } from "../store/editorStore";
import { api } from "../api/client";
import { useState, useEffect } from "react";
import type { IngestStatus } from "../api/client";

interface StatusBarProps {
  ingestStatus?: IngestStatus | null;
}

export function StatusBar({ ingestStatus }: StatusBarProps) {
  const { documentLoaded, documentPath, totalPages, currentPage, editCount, sessionId } =
    useEditorStore();
  const loadingMessage = useEditorStore((s) => s.loadingMessage);
  const [totalCost, setTotalCost] = useState(0);

  // Poll costs every 5 seconds
  useEffect(() => {
    const fetchCost = () => {
      api.getSessionCosts().then((data) => {
        setTotalCost(data.total_cost_usd || 0);
      }).catch(() => {});
    };

    fetchCost();
    const interval = setInterval(fetchCost, 5000);
    return () => clearInterval(interval);
  }, []);

  // Also refresh after ingest completes
  useEffect(() => {
    if (ingestStatus?.done) {
      api.getSessionCosts().then((data) => {
        setTotalCost(data.total_cost_usd || 0);
      }).catch(() => {});
    }
  }, [ingestStatus?.done]);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      borderTop: "1px solid var(--border, #ddd)",
      background: "var(--bg-secondary, #f8f9fa)",
      fontSize: "12px",
    }}>
      {/* Ingestion progress bar */}
      {ingestStatus && !ingestStatus.done && (
        <div style={{ padding: "4px 16px", borderBottom: "1px solid var(--border, #eee)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "3px" }}>
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
              {ingestStatus.status === "uploading" && "📤"}
              {ingestStatus.status === "extracting" && "📄"}
              {ingestStatus.status === "indexing" && "🔍"}
              {ingestStatus.status === "detecting_tbds" && "📋"}
              {" "}{ingestStatus.message}
            </span>
          </div>
          <div style={{
            height: "3px",
            background: "var(--bg-tertiary, #e0e0e0)",
            borderRadius: "2px",
            overflow: "hidden",
          }}>
            <div style={{
              height: "100%",
              width: `${ingestStatus.progress_pct}%`,
              background: "#1976d2",
              borderRadius: "2px",
              transition: "width 0.4s ease",
            }} />
          </div>
        </div>
      )}

      {/* Ingestion complete summary */}
      {ingestStatus && ingestStatus.done && ingestStatus.status === "done" && (
        <div style={{
          padding: "4px 16px",
          borderBottom: "1px solid var(--border, #eee)",
          color: "#2e7d32",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}>
          <span>✅ {ingestStatus.filename}: {ingestStatus.pages} pages, {ingestStatus.chunks_indexed} chunks indexed</span>
          {(ingestStatus.tbd_count > 0 || ingestStatus.tbr_count > 0) && (
            <span style={{ color: "#e65100", fontWeight: 500 }}>
              — {ingestStatus.tbd_count} TBDs{ingestStatus.tbr_count > 0 ? `, ${ingestStatus.tbr_count} TBRs` : ""}
            </span>
          )}
        </div>
      )}

      {/* Ingestion error */}
      {ingestStatus && ingestStatus.done && ingestStatus.status === "error" && (
        <div style={{
          padding: "4px 16px",
          borderBottom: "1px solid var(--border, #eee)",
          color: "#c62828",
        }}>
          ❌ {ingestStatus.message}
        </div>
      )}

      {/* Main status line */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "4px 16px",
        color: "var(--text-secondary, #666)",
      }}>
        {loadingMessage ? (
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ display: "inline-block", width: "10px", height: "10px", border: "2px solid var(--accent, #1976d2)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
            <span style={{ color: "var(--accent, #1976d2)", fontWeight: 500 }}>{loadingMessage}</span>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </span>
        ) : !documentLoaded ? (
          <span>Ready — Upload a PDF or open an indexed document</span>
        ) : (
          <span>
            {documentPath.split("/").pop()} — {totalPages} pages — Page {currentPage}
          </span>
        )}
        <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {documentLoaded && editCount > 0 && `${editCount} unsaved edit${editCount > 1 ? "s" : ""} · `}
          {sessionId && `Session: ${sessionId.slice(0, 8)}`}
          {totalCost > 0 && (
            <>
              <span style={{ borderLeft: "1px solid var(--border, #ccc)", height: "12px", margin: "0 4px" }} />
              <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                ${totalCost.toFixed(4)}
              </span>
              <button
                onClick={() => window.location.href = api.getSessionCostsExportUrl()}
                title="Download itemized cost receipt (CSV)"
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  padding: "0 2px", fontSize: "12px", color: "var(--text-secondary)",
                }}
              >
                📥
              </button>
            </>
          )}
        </span>
      </div>
    </div>
  );
}
