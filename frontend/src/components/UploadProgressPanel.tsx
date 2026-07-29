import { useState, useEffect, useRef } from "react";
import { api } from "../api/client";
import type { IngestStatus } from "../api/client";

interface UploadProgressPanelProps {
  file: File;
  onProgress?: (status: IngestStatus) => void;
  onComplete: (status: IngestStatus) => void;
  onDismiss: () => void;
}

const STEP_LABELS: Record<string, string> = {
  uploading: "Uploading PDF",
  extracting: "Extracting text & structure",
  indexing: "Indexing into OpenSearch",
  detecting_tbds: "Detecting TBD/TBR items",
  done: "Complete",
  error: "Error",
};

const STEP_ICONS: Record<string, string> = {
  uploading: "📤",
  extracting: "📄",
  indexing: "🔍",
  detecting_tbds: "📋",
  done: "✅",
  error: "❌",
};

export function UploadProgressPanel({ file, onProgress, onComplete, onDismiss }: UploadProgressPanelProps) {
  const [uploadPct, setUploadPct] = useState(0);
  const [ingestId, setIngestId] = useState<string | null>(null);
  const [status, setStatus] = useState<IngestStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Start the upload + ingestion
  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        const result = await api.ingestDocument(file, (pct) => {
          if (!cancelled) setUploadPct(pct);
        });
        if (!cancelled) {
          setIngestId(result.ingest_id);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Upload failed");
        }
      }
    }

    start();
    return () => { cancelled = true; };
  }, [file]);

  // Poll for status once we have an ingest_id
  useEffect(() => {
    if (!ingestId) return;

    const poll = async () => {
      try {
        const s = await api.getIngestStatus(ingestId);
        setStatus(s);
        if (onProgress) onProgress(s);
        if (s.done) {
          if (pollingRef.current) clearInterval(pollingRef.current);
          onComplete(s);
        }
      } catch {
        // Keep polling on transient errors
      }
    };

    poll(); // immediate first poll
    pollingRef.current = setInterval(poll, 1000);

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [ingestId, onComplete]);

  const currentStatus = status?.status || "uploading";
  const progressPct = status?.progress_pct || uploadPct * 0.1; // upload is ~10% of total
  const message = status?.message || (uploadPct < 100 ? `Uploading ${file.name}... ${uploadPct}%` : "Processing...");

  const steps = ["uploading", "extracting", "indexing", "detecting_tbds", "done"];
  const currentStepIdx = steps.indexOf(currentStatus);

  return (
    <div style={{
      position: "fixed",
      top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.5)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 9999,
    }}>
      <div style={{
        background: "var(--bg-primary, #fff)",
        borderRadius: "12px",
        padding: "32px",
        width: "480px",
        maxWidth: "90vw",
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
      }}>
        {/* Header */}
        <div style={{ marginBottom: "20px" }}>
          <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
            {error ? "❌ Ingestion Failed" : currentStatus === "done" ? "✅ Document Ready" : "Processing Document"}
          </h3>
          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--text-secondary)" }}>
            {file.name}
          </p>
        </div>

        {/* Progress bar */}
        <div style={{
          height: "8px",
          background: "var(--bg-tertiary, #e0e0e0)",
          borderRadius: "4px",
          overflow: "hidden",
          marginBottom: "20px",
        }}>
          <div style={{
            height: "100%",
            width: `${progressPct}%`,
            background: error ? "#e53935" : currentStatus === "done" ? "#43a047" : "#1976d2",
            borderRadius: "4px",
            transition: "width 0.4s ease",
          }} />
        </div>

        {/* Status message */}
        <p style={{
          fontSize: "13px",
          color: "var(--text-primary)",
          margin: "0 0 20px",
          minHeight: "18px",
        }}>
          {error || message}
        </p>

        {/* Step indicators */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "20px" }}>
          {steps.map((step, idx) => {
            const isActive = idx === currentStepIdx;
            const isCompleted = idx < currentStepIdx || currentStatus === "done";
            const isPending = idx > currentStepIdx;

            return (
              <div key={step} style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                opacity: isPending ? 0.4 : 1,
              }}>
                <span style={{ fontSize: "14px", width: "20px", textAlign: "center" }}>
                  {isCompleted ? "✓" : isActive ? STEP_ICONS[step] : "○"}
                </span>
                <span style={{
                  fontSize: "12px",
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                }}>
                  {STEP_LABELS[step]}
                </span>
                {isActive && currentStatus !== "done" && (
                  <span style={{ fontSize: "11px", color: "var(--text-secondary)", marginLeft: "auto" }}>
                    {step === "uploading" && `${uploadPct}%`}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Summary stats (shown when done) */}
        {status?.done && !error && (
          <div style={{
            background: "var(--bg-tertiary, #f5f5f5)",
            borderRadius: "8px",
            padding: "12px 16px",
            marginBottom: "16px",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "8px",
            fontSize: "12px",
          }}>
            <div><strong>{status.pages}</strong> pages</div>
            <div><strong>{status.text_blocks}</strong> text blocks</div>
            <div><strong>{status.chunks_indexed}</strong> chunks indexed</div>
            <div>
              <strong>{status.tbd_count}</strong> TBDs
              {status.tbr_count > 0 && <>, <strong>{status.tbr_count}</strong> TBRs</>}
            </div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
          {(status?.done || error) && (
            <button
              onClick={onDismiss}
              style={{
                padding: "8px 16px",
                borderRadius: "6px",
                border: "none",
                background: currentStatus === "done" ? "#1976d2" : "var(--bg-tertiary, #e0e0e0)",
                color: currentStatus === "done" ? "#fff" : "var(--text-primary)",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: 500,
              }}
            >
              {currentStatus === "done" ? "Open Document" : "Dismiss"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
