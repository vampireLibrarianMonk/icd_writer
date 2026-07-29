import { useState, useEffect } from "react";
import { api } from "../api/client";
import { useEditorStore } from "../store/editorStore";

interface DiffSection {
  section_heading: string;
  change_type: string;
  classification: string;
  has_requirement_change: boolean;
  has_tbd_change: boolean;
  page_old: number | null;
  page_new: number | null;
  old_text: string;
  new_text: string;
  ai_summary: string | null;
}

interface DiffSummary {
  sections_modified: number;
  sections_added: number;
  sections_removed: number;
  requirement_changes: number;
  tbd_changes: number;
  editorial_changes: number;
  text_overlap: number;
  total_diff_tokens: number;
  estimated_llm_cost: number;
}

export function VersionDiffPanel() {
  const { documentPath } = useEditorStore();
  const [relatedVersions, setRelatedVersions] = useState<any[]>([]);
  const [diffSummary, setDiffSummary] = useState<DiffSummary | null>(null);
  const [diffs, setDiffs] = useState<DiffSection[]>([]);
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState<string | null>(null);
  const [needsOcr, setNeedsOcr] = useState<string | null>(null);
  const [ocrRunning, setOcrRunning] = useState(false);
  const [aiSummaries, setAiSummaries] = useState<Record<string, string>>({});
  const [aiLoading, setAiLoading] = useState<string | null>(null);

  // Listen for related versions notification
  useEffect(() => {
    const handler = (e: CustomEvent) => {
      setRelatedVersions(e.detail.relatedVersions);
      setDiffSummary(null);
      setDiffs([]);
    };
    window.addEventListener("related-versions-found" as any, handler);
    return () => window.removeEventListener("related-versions-found" as any, handler);
  }, []);

  // Reset when document changes
  useEffect(() => {
    setDiffSummary(null);
    setDiffs([]);
    setComparing(null);
    setNeedsOcr(null);
    setAiSummaries({});
    // Check for related versions
    if (documentPath) {
      api.getRelatedVersions(documentPath).then((res) => {
        if (res.has_related) {
          setRelatedVersions(res.other_versions);
        } else {
          setRelatedVersions([]);
        }
      }).catch(() => setRelatedVersions([]));
    }
  }, [documentPath]);

  const handleRunDiff = async (otherPath: string) => {
    // Check if the other version is flattened (needs OCR)
    const otherFilename = otherPath.split("/").pop() || "";
    const isFlattened = otherFilename.includes("flat") || otherPath.includes("/flat/");

    if (isFlattened) {
      setComparing(otherPath);
      setNeedsOcr(otherPath);
      return;
    }

    setLoading(true);
    setComparing(otherPath);
    setNeedsOcr(null);
    try {
      const result = await api.runVersionDiff(documentPath, otherPath);
      setDiffSummary(result.summary);
      setDiffs(result.diffs);
    } catch (e) {
      alert("Diff failed: " + (e instanceof Error ? e.message : "unknown error"));
    } finally {
      setLoading(false);
    }
  };

  const handleRunOcr = async () => {
    if (!needsOcr) return;
    setOcrRunning(true);
    try {
      const res = await fetch(`http://localhost:8000/document/open-ocr?pdf_path=${encodeURIComponent(needsOcr)}`, { method: "POST" });
      const result = await res.json();
      if (result.status === "ready") {
        // OCR complete — now run diff
        setNeedsOcr(null);
        setLoading(true);
        const diffResult = await api.runVersionDiff(documentPath, needsOcr!);
        setDiffSummary(diffResult.summary);
        setDiffs(diffResult.diffs);
        setLoading(false);
      } else {
        alert("OCR processing: " + (result.message || JSON.stringify(result)));
      }
    } catch (e) {
      alert("OCR failed: " + (e instanceof Error ? e.message : "unknown error"));
    } finally {
      setOcrRunning(false);
    }
  };

  const handleAiSummarize = async (sectionHeading: string) => {
    if (!comparing) return;
    setAiLoading(sectionHeading);
    try {
      const result = await api.summarizeDiffSection(documentPath, comparing, sectionHeading);
      if (result.ai_summary) {
        setAiSummaries((prev) => ({ ...prev, [sectionHeading]: result.ai_summary }));
      }
    } catch (e) {
      // Silently fail
    } finally {
      setAiLoading(null);
    }
  };

  if (!documentPath) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "var(--text-secondary)", fontSize: "12px" }}>
        Open a document to check for version differences.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px", overflow: "hidden" }}>
      <div style={{ marginBottom: "12px" }}>
        <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Version Diff</h3>
        <p style={{ margin: "4px 0 0", fontSize: "11px", color: "var(--text-secondary)" }}>
          Compare document versions and track changes
        </p>
      </div>

      {/* Related versions */}
      {relatedVersions.length > 0 && !diffSummary && (
        <div style={{
          background: "var(--info-bg)",
          color: "var(--info-text)",
          borderRadius: "6px",
          padding: "10px",
          marginBottom: "12px",
        }}>
          <div style={{ fontSize: "12px", fontWeight: 500, marginBottom: "6px" }}>
            📋 Related versions detected:
          </div>
          {relatedVersions.map((v, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px", margin: "4px 0" }}>
              <span style={{ fontSize: "11px", flex: 1, color: "var(--text-primary)" }}>
                {v.filename} ({v.page_count}pg{v.revision ? `, Rev ${v.revision}` : ""}, {v.doc_type})
              </span>
              <button
                onClick={() => handleRunDiff(v.path)}
                disabled={loading}
                style={{ fontSize: "10px", padding: "3px 8px" }}
              >
                Compare
              </button>
            </div>
          ))}
        </div>
      )}

      {relatedVersions.length === 0 && !diffSummary && (
        <div style={{ textAlign: "center", padding: "30px", color: "var(--text-secondary)", fontSize: "12px" }}>
          No related versions found for this document.
        </div>
      )}

      {loading && (
        <div style={{ textAlign: "center", padding: "20px" }}>Analyzing differences...</div>
      )}

      {/* OCR required message */}
      {needsOcr && !loading && !diffSummary && !ocrRunning && (
        <div style={{
          background: "var(--warning-bg)",
          color: "var(--warning-text)",
          borderRadius: "6px",
          padding: "14px",
          marginBottom: "12px",
        }}>
          <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "8px" }}>
            ⚠️ OCR Required
          </div>
          <p style={{ fontSize: "12px", margin: "0 0 8px", lineHeight: 1.5, color: "var(--text-primary)" }}>
            The document <strong>{needsOcr.split("/").pop()}</strong> is a flattened/scanned PDF with no extractable text.
            Differential analysis cannot be performed until OCR (Optical Character Recognition) is run to recover the text content.
          </p>
          <p style={{ fontSize: "11px", margin: "0 0 12px", color: "var(--text-secondary)" }}>
            OCR uses AWS Textract to extract text from page images. This incurs a small cost (~$0.0015/page).
          </p>
          <button
            onClick={handleRunOcr}
            disabled={ocrRunning}
            style={{ padding: "6px 14px", fontSize: "12px", borderRadius: "4px" }}
          >
            Run OCR & Compare
          </button>
          <button
            onClick={() => { setNeedsOcr(null); setComparing(null); }}
            style={{ marginLeft: "8px", padding: "6px 14px", fontSize: "12px", borderRadius: "4px", background: "transparent", border: "1px solid var(--border)" }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* OCR Progress */}
      {ocrRunning && (
        <OcrProgress filename={needsOcr?.split("/").pop() || ""} />
      )}

      {/* Diff Summary (Level 1 — always free) */}
      {diffSummary && (
        <div style={{ flex: 1, overflowY: "auto" }}>
          {/* Comparison header — tells user what's being compared */}
          <div style={{
            background: "var(--success-bg)",
            color: "var(--success-text)",
            borderRadius: "6px",
            padding: "8px 10px",
            marginBottom: "8px",
            fontSize: "11px",
          }}>
            <div style={{ fontWeight: 600, marginBottom: "4px" }}>Comparing:</div>
            <div style={{ color: "var(--text-primary)" }}>📄 <b>Current:</b> {documentPath.split("/").pop()}</div>
            <div style={{ color: "var(--text-primary)" }}>📄 <b>Against:</b> {comparing?.split("/").pop()}</div>
          </div>

          <div style={{
            background: "var(--bg-secondary)",
            borderRadius: "6px",
            padding: "10px",
            marginBottom: "12px",
          }}>
            <div style={{ fontSize: "12px", fontWeight: 600, marginBottom: "6px" }}>Summary</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", fontSize: "11px" }}>
              <span>Modified: {diffSummary.sections_modified}</span>
              <span>Added: {diffSummary.sections_added}</span>
              <span>Removed: {diffSummary.sections_removed}</span>
              <span>Text overlap: {(diffSummary.text_overlap * 100).toFixed(0)}%</span>
              <span style={{ color: diffSummary.requirement_changes > 0 ? "#e65100" : "inherit" }}>
                ⚠️ Req changes: {diffSummary.requirement_changes}
              </span>
              <span>TBD changes: {diffSummary.tbd_changes}</span>
            </div>
            <div style={{ fontSize: "10px", color: "var(--text-secondary)", marginTop: "6px" }}>
              AI summary cost (all sections): ${diffSummary.estimated_llm_cost.toFixed(5)}
            </div>
          </div>

          {/* Per-section diffs (Level 2 — free, expandable) */}
          {diffs.map((diff, i) => (
            <DiffSectionRow
              key={i}
              diff={diff}
              expanded={expandedSection === diff.section_heading}
              onToggle={() => setExpandedSection(
                expandedSection === diff.section_heading ? null : diff.section_heading
              )}
              aiSummary={aiSummaries[diff.section_heading]}
              onAiSummarize={() => handleAiSummarize(diff.section_heading)}
              aiLoading={aiLoading === diff.section_heading}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DiffSectionRow({ diff, expanded, onToggle, aiSummary, onAiSummarize, aiLoading }: {
  diff: DiffSection;
  expanded: boolean;
  onToggle: () => void;
  aiSummary?: string;
  onAiSummarize: () => void;
  aiLoading: boolean;
}) {
  const typeColors: Record<string, string> = {
    modified: "#ff9800",
    added: "#4caf50",
    removed: "#f44336",
  };
  const classIcons: Record<string, string> = {
    technical: "⚠️",
    structural: "🔧",
    editorial: "📝",
  };

  return (
    <div style={{
      margin: "4px 0",
      borderRadius: "4px",
      borderLeft: `3px solid ${typeColors[diff.change_type] || "#999"}`,
      background: "var(--bg-secondary)",
      fontSize: "11px",
    }}>
      <div
        onClick={onToggle}
        style={{
          padding: "6px 8px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <span>{classIcons[diff.classification] || ""}</span>
        <span style={{ fontWeight: 500, flex: 1 }}>{diff.section_heading.slice(0, 50)}</span>
        <span style={{
          fontSize: "9px",
          padding: "1px 4px",
          borderRadius: "2px",
          background: typeColors[diff.change_type] + "22",
          color: typeColors[diff.change_type],
        }}>
          {diff.change_type}
        </span>
        {diff.has_requirement_change && <span title="Requirement changed">⚠️</span>}
        {diff.has_tbd_change && <span title="TBD changed">📋</span>}
        <span>{expanded ? "▼" : "▶"}</span>
      </div>

      {expanded && (
        <div style={{ padding: "6px 8px", borderTop: "1px solid var(--border)" }}>
          {diff.old_text && (
            <div style={{ margin: "4px 0" }}>
              <div style={{ fontSize: "10px", color: "#c62828", fontWeight: 500 }}>Old:</div>
              <div style={{ fontFamily: "monospace", fontSize: "10px", color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                {diff.old_text.slice(0, 200)}{diff.old_text.length > 200 ? "..." : ""}
              </div>
            </div>
          )}
          {diff.new_text && (
            <div style={{ margin: "4px 0" }}>
              <div style={{ fontSize: "10px", color: "#2e7d32", fontWeight: 500 }}>New:</div>
              <div style={{ fontFamily: "monospace", fontSize: "10px", color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                {diff.new_text.slice(0, 200)}{diff.new_text.length > 200 ? "..." : ""}
              </div>
            </div>
          )}

          {/* AI Summary (Level 3 — on demand) */}
          {aiSummary ? (
            <div style={{ margin: "6px 0", padding: "6px", background: "var(--highlight-bg)", color: "var(--highlight-text)", borderRadius: "4px", fontSize: "11px" }}>
              <div style={{ fontWeight: 500, marginBottom: "2px" }}>🤖 AI Analysis:</div>
              <span style={{ color: "var(--text-primary)" }}>{aiSummary}</span>
            </div>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); onAiSummarize(); }}
              disabled={aiLoading}
              style={{ fontSize: "10px", padding: "2px 6px", marginTop: "4px" }}
            >
              {aiLoading ? "Analyzing..." : "🤖 Summarize with AI (~$0.00005)"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}


function OcrProgress({ filename }: { filename: string }) {
  const [elapsed, setElapsed] = useState(0);
  const [statusMessage, setStatusMessage] = useState("Initializing OCR pipeline...");

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1;
        // Update status messages based on time
        if (next < 3) setStatusMessage("Connecting to AWS Textract...");
        else if (next < 8) setStatusMessage("Uploading page images...");
        else if (next < 15) setStatusMessage("Extracting text from pages...");
        else if (next < 25) setStatusMessage("Processing text blocks...");
        else if (next < 40) setStatusMessage("Running text recognition (this may take a moment)...");
        else if (next < 60) setStatusMessage("Assembling document structure...");
        else setStatusMessage("Still processing — large documents take longer...");
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Indeterminate progress animation
  const progressWidth = Math.min(95, (elapsed / 60) * 100);

  return (
    <div style={{
      background: "var(--bg-secondary)",
      borderRadius: "6px",
      padding: "14px",
      marginBottom: "12px",
    }}>
      <div style={{ fontSize: "12px", fontWeight: 600, marginBottom: "8px" }}>
        🔄 Running OCR on {filename}
      </div>

      {/* Progress bar */}
      <div style={{
        width: "100%",
        height: "6px",
        background: "var(--bg-tertiary, #e0e0e0)",
        borderRadius: "3px",
        overflow: "hidden",
        marginBottom: "8px",
      }}>
        <div style={{
          width: `${progressWidth}%`,
          height: "100%",
          background: "linear-gradient(90deg, #1976d2, #42a5f5)",
          borderRadius: "3px",
          transition: "width 1s linear",
        }} />
      </div>

      {/* Status message */}
      <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
        {statusMessage}
      </div>
      <div style={{ fontSize: "10px", color: "var(--text-secondary)", marginTop: "4px" }}>
        Elapsed: {elapsed}s
      </div>
    </div>
  );
}
