import { useState, useEffect, useMemo } from "react";
import { api } from "../api/client";
import type {
  BriefingFamily,
  BriefingFamilyVersion,
  BriefingCompareResponse,
  BriefingSectionResult,
} from "../api/client";
import { useEditorStore } from "../store/editorStore";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

type AnalysisMode = "standard" | "advanced";

/**
 * Revision Compare Panel — scoped to the currently opened document.
 * Supports Standard (free, structural) and Advanced (AI-assisted) modes.
 * Handles flattened PDFs by offering OCR before comparison.
 */
export function RevisionComparePanel() {
  const { documentPath } = useEditorStore();
  const [family, setFamily] = useState<BriefingFamily | null>(null);
  const [fromRev, setFromRev] = useState<string>("");
  const [toRev, setToRev] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [loadingFamily, setLoadingFamily] = useState(false);
  const [result, setResult] = useState<BriefingCompareResponse | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [hideUnchanged, setHideUnchanged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // OCR state
  const [needsOcr, setNeedsOcr] = useState<string | null>(null);
  const [ocrRunning, setOcrRunning] = useState(false);

  // Analysis mode (persisted)
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>(
    () => (localStorage.getItem("analysisMode") as AnalysisMode) || "standard"
  );
  const [sessionCost, setSessionCost] = useState(0);
  const [aiSummaries, setAiSummaries] = useState<Record<string, string>>({});
  const [aiLoading, setAiLoading] = useState<string | null>(null);

  // Persist mode
  useEffect(() => {
    localStorage.setItem("analysisMode", analysisMode);
  }, [analysisMode]);

  // When the open document changes, find its family
  useEffect(() => {
    if (!documentPath) {
      setFamily(null);
      setResult(null);
      setFromRev("");
      setToRev("");
      setError(null);
      setExpandedSections(new Set());
      setAiSummaries({});
      return;
    }

    // If the new document is part of the current comparison, don't reset results
    const openFilename = documentPath.split(/[/\\]/).pop() || "";
    if (family) {
      const isInFamily = family.versions.some(
        (v: BriefingFamilyVersion) => v.filename === openFilename || v.path === documentPath
      );
      if (isInFamily) {
        // Same family — keep results intact (user navigated via page link)
        return;
      }
    }

    // Different family or first load — reset and fetch
    setResult(null);
    setFromRev("");
    setToRev("");
    setError(null);
    setExpandedSections(new Set());
    setAiSummaries({});

    setLoadingFamily(true);
    api.getBriefingFamilies()
      .then((res) => {
        const match = res.families?.find((f: BriefingFamily) =>
          f.versions.some((v: BriefingFamilyVersion) =>
            v.filename === openFilename || v.path === documentPath
          )
        );
        setFamily(match || null);
        if (match && match.versions.length >= 2) {
          const versions = match.versions;
          setFromRev(versions[versions.length - 2].path);
          setToRev(versions[versions.length - 1].path);
        }
      })
      .catch(() => setFamily(null))
      .finally(() => setLoadingFamily(false));
  }, [documentPath]);

  const versions = family?.versions || [];

  const toOptions = useMemo(() => {
    if (!fromRev) return [];
    const fromIdx = versions.findIndex((v) => v.path === fromRev);
    if (fromIdx < 0) return [];
    return versions.slice(fromIdx + 1);
  }, [versions, fromRev]);

  useEffect(() => {
    if (fromRev && toRev) {
      const fromIdx = versions.findIndex((v) => v.path === fromRev);
      const toIdx = versions.findIndex((v) => v.path === toRev);
      if (toIdx <= fromIdx) setToRev("");
    }
  }, [fromRev]);

  const handleCompare = async () => {
    if (!fromRev || !toRev) return;

    // Check if either version is flattened (needs OCR first)
    const isFlattened = (path: string) => {
      const name = path.split(/[/\\]/).pop() || "";
      return name.includes("flat") || path.includes("/flat/") || path.includes("\\flat\\");
    };
    const flatPath = isFlattened(toRev) ? toRev : isFlattened(fromRev) ? fromRev : null;
    if (flatPath) {
      setNeedsOcr(flatPath);
      return;
    }

    await runComparison();
  };

  const runComparison = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setNeedsOcr(null);
    setExpandedSections(new Set());
    setAiSummaries({});
    try {
      const res = await api.runBriefingCompare(fromRev, toRev);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRunOcr = async () => {
    if (!needsOcr) return;
    setOcrRunning(true);
    try {
      const res = await fetch(`${API_BASE}/document/open-ocr?pdf_path=${encodeURIComponent(needsOcr)}`, { method: "POST" });
      const result = await res.json();
      if (result.status === "ready") {
        setNeedsOcr(null);
        await runComparison();
      } else {
        setError("OCR processing: " + (result.message || JSON.stringify(result)));
      }
    } catch (e) {
      setError("OCR failed: " + (e instanceof Error ? e.message : "unknown"));
    } finally {
      setOcrRunning(false);
    }
  };

  const handleAiSummarize = async (sectionHeading: string) => {
    if (!fromRev || !toRev) return;
    setAiLoading(sectionHeading);
    try {
      const res = await api.summarizeDiffSection(fromRev, toRev, sectionHeading);
      if (res.ai_summary) {
        setAiSummaries((prev) => ({ ...prev, [sectionHeading]: res.ai_summary }));
      }
      if (res.cost_usd) {
        setSessionCost((prev) => prev + res.cost_usd);
      }
      // If AI call failed on the backend, show the error as the summary
      if (!res.ai_summary && res.error) {
        setAiSummaries((prev) => ({ ...prev, [sectionHeading]: `[Error: ${res.error}]` }));
      }
    } catch (e) {
      setAiSummaries((prev) => ({
        ...prev,
        [sectionHeading]: `[Request failed: ${e instanceof Error ? e.message : "unknown"}]`,
      }));
    } finally {
      setAiLoading(null);
    }
  };

  const toggleSection = (heading: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      next.has(heading) ? next.delete(heading) : next.add(heading);
      return next;
    });
  };

  const sortedSections = useMemo(() => {
    if (!result) return [];
    const changed = result.sections.filter((s) => s.change_type !== "unchanged");
    const unchanged = result.sections.filter((s) => s.change_type === "unchanged");
    return [...changed, ...unchanged];
  }, [result]);

  const visibleSections = hideUnchanged
    ? sortedSections.filter((s) => s.change_type !== "unchanged")
    : sortedSections;

  // ─── No document open ───────────────────────────────────────
  if (!documentPath) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "var(--text-secondary)", fontSize: "12px" }}>
        Open a document to compare revisions.
      </div>
    );
  }
  if (loadingFamily) {
    return (
      <div style={{ padding: "20px", textAlign: "center", fontSize: "12px", color: "var(--text-secondary)" }}>
        Checking for related revisions...
      </div>
    );
  }

  // ─── Only one revision available ────────────────────────────
  if (!family || versions.length < 2) {
    const openFilename = documentPath.split(/[/\\]/).pop() || "this document";
    return (
      <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px" }}>
        <div style={{ marginBottom: "10px" }}>
          <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Revision Compare</h3>
        </div>
        <div style={{ background: "var(--bg-secondary, #f5f5f5)", borderRadius: "6px", padding: "16px", textAlign: "center" }}>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.6 }}>
            <strong>{openFilename}</strong> is the only indexed revision in its family.
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "8px", lineHeight: 1.5 }}>
            Upload another revision of this document to enable comparison.
          </div>
        </div>
      </div>
    );
  }

  // ─── Multiple revisions available ──────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ marginBottom: "8px" }}>
        <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Revision Compare</h3>
        <p style={{ margin: "4px 0 0", fontSize: "11px", color: "var(--text-secondary)", lineHeight: 1.4 }}>
          Compare revisions of <strong>{family.family_name}</strong> ({versions.length} available).
        </p>
      </div>

      {/* Analysis Mode Toggle */}
      <div style={{
        background: "var(--bg-secondary, #f5f5f5)",
        borderRadius: "6px",
        padding: "8px 10px",
        marginBottom: "10px",
        fontSize: "11px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: analysisMode === "advanced" ? "6px" : "0" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
            <input
              type="radio" name="analysisMode" value="standard"
              checked={analysisMode === "standard"}
              onChange={() => setAnalysisMode("standard")}
            />
            <span>Standard</span>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
            <input
              type="radio" name="analysisMode" value="advanced"
              checked={analysisMode === "advanced"}
              onChange={() => setAnalysisMode("advanced")}
            />
            <span>Advanced (AI-assisted)</span>
          </label>
        </div>
        {analysisMode === "advanced" && (
          <div style={{ color: "var(--text-secondary)", fontSize: "10px" }}>
            AI features enabled. Session cost: <strong>${sessionCost.toFixed(6)}</strong>
          </div>
        )}
        {analysisMode === "standard" && (
          <div style={{ color: "var(--text-secondary)", fontSize: "10px", marginTop: "2px" }}>
            All analysis is local. No AI charges.
          </div>
        )}
      </div>

      {/* From / To dropdowns */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "10px" }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "11px", color: "var(--text-secondary)", display: "block", marginBottom: "3px" }}>From (older):</label>
          <select value={fromRev} onChange={(e) => setFromRev(e.target.value)}
            style={{ width: "100%", padding: "5px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)" }}>
            <option value="">Select...</option>
            {versions.slice(0, -1).map((v) => (
              <option key={v.path} value={v.path}>{formatVersion(v)}</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "11px", color: "var(--text-secondary)", display: "block", marginBottom: "3px" }}>To (newer):</label>
          <select value={toRev} onChange={(e) => setToRev(e.target.value)} disabled={!fromRev}
            style={{ width: "100%", padding: "5px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)" }}>
            <option value="">Select...</option>
            {toOptions.map((v) => (
              <option key={v.path} value={v.path}>{formatVersion(v)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Compare button */}
      <button onClick={handleCompare} disabled={!fromRev || !toRev || loading}
        style={{
          padding: "7px 16px", fontSize: "12px", fontWeight: 500, borderRadius: "4px", border: "none",
          background: fromRev && toRev ? "var(--accent, #1976d2)" : "var(--bg-tertiary, #e0e0e0)",
          color: fromRev && toRev ? "#fff" : "var(--text-secondary)",
          cursor: fromRev && toRev && !loading ? "pointer" : "default", marginBottom: "12px",
        }}>
        {loading ? "Comparing..." : "Compare"}
      </button>

      {error && (
        <div style={{ background: "var(--error-bg, #ffebee)", color: "var(--error-text, #c62828)", borderRadius: "6px", padding: "10px", marginBottom: "10px", fontSize: "12px" }}>
          {error}
        </div>
      )}

      {/* OCR Required */}
      {needsOcr && !ocrRunning && (
        <div style={{ background: "var(--warning-bg, #fff8e1)", color: "var(--warning-text, #e65100)", borderRadius: "6px", padding: "14px", marginBottom: "12px" }}>
          <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "8px" }}>OCR Required</div>
          <p style={{ fontSize: "12px", margin: "0 0 8px", lineHeight: 1.5, color: "var(--text-primary)" }}>
            <strong>{needsOcr.split(/[/\\]/).pop()}</strong> is a flattened/scanned PDF.
            OCR must run first to extract text for comparison.
          </p>
          <p style={{ fontSize: "11px", margin: "0 0 12px", color: "var(--text-secondary)" }}>
            Uses AWS Textract (~$0.0015/page).
          </p>
          <button onClick={handleRunOcr} style={{ padding: "6px 14px", fontSize: "12px", borderRadius: "4px", border: "none", background: "var(--accent, #1976d2)", color: "#fff", cursor: "pointer" }}>
            Run OCR & Compare
          </button>
          <button onClick={() => setNeedsOcr(null)} style={{ marginLeft: "8px", padding: "6px 14px", fontSize: "12px", borderRadius: "4px", background: "transparent", border: "1px solid var(--border)", cursor: "pointer" }}>
            Cancel
          </button>
        </div>
      )}

      {/* OCR Progress */}
      {ocrRunning && <OcrProgress filename={needsOcr?.split(/[/\\]/).pop() || ""} />}

      {/* Results */}
      {result && (
        <div style={{ flex: 1, overflowY: "auto", borderTop: "1px solid var(--border)", paddingTop: "10px" }}>
          <StatsBanner result={result} />

          {/* Global changes (boilerplate extracted from all sections) */}
          {result.global_changes && result.global_changes.length > 0 && (
            <div style={{ background: "var(--bg-secondary, #f5f5f5)", borderRadius: "6px", padding: "8px 10px", margin: "8px 0", fontSize: "11px" }}>
              <div style={{ fontWeight: 600, marginBottom: "4px", color: "var(--text-secondary)" }}>
                Global changes (header/footer updates across all pages):
              </div>
              {result.global_changes.map((gc, i) => (
                <div key={i} style={{ fontFamily: "monospace", fontSize: "10px", color: "var(--text-secondary)", margin: "2px 0", paddingLeft: "8px" }}>
                  {gc}
                </div>
              ))}
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "10px 0 8px" }}>
            <span style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
              {result.stats.total_sections_changed} changed, {result.stats.total_sections_unchanged} unchanged
            </span>
            <label style={{ fontSize: "11px", color: "var(--text-secondary)", cursor: "pointer" }}>
              <input type="checkbox" checked={hideUnchanged} onChange={(e) => setHideUnchanged(e.target.checked)} style={{ marginRight: "4px" }} />
              Hide unchanged
            </label>
          </div>

          <div>
            {visibleSections.map((section) => (
              <SectionRow
                key={section.section_heading}
                section={section}
                expanded={expandedSections.has(section.section_heading)}
                onToggle={() => toggleSection(section.section_heading)}
                advancedMode={analysisMode === "advanced"}
                aiSummary={aiSummaries[section.section_heading]}
                aiLoading={aiLoading === section.section_heading}
                onAiSummarize={() => handleAiSummarize(section.section_heading)}
                toRevPath={toRev}
              />
            ))}
          </div>

          {result.cross_references.length > 0 && (
            <div style={{ marginTop: "16px", borderTop: "1px solid var(--border)", paddingTop: "10px" }}>
              <h4 style={{ fontSize: "12px", fontWeight: 600, margin: "0 0 6px" }}>Cross-References ({result.cross_references.length})</h4>
              {result.cross_references.map((cr, i) => (
                <div key={i} style={{ fontSize: "11px", color: "var(--text-secondary)", margin: "3px 0", paddingLeft: "8px", borderLeft: "2px solid var(--accent, #1976d2)" }}>
                  <strong>{cr.source_document}</strong> references <strong>{cr.target_document}</strong> &mdash; &ldquo;{cr.reference_text}&rdquo; (p.{cr.page})
                </div>
              ))}
            </div>
          )}

          {result.value_conflicts.length > 0 && (
            <div style={{ marginTop: "16px", borderTop: "1px solid var(--border)", paddingTop: "10px" }}>
              <h4 style={{ fontSize: "12px", fontWeight: 600, margin: "0 0 6px", color: "var(--warning-text, #e65100)" }}>Value Conflicts ({result.value_conflicts.length})</h4>
              {result.value_conflicts.map((vc, i) => (
                <div key={i} style={{ fontSize: "11px", margin: "4px 0", padding: "6px 8px", background: "var(--warning-bg, #fff8e1)", borderRadius: "4px" }}>
                  <strong>{vc.parameter || "parameter"}</strong>: {vc.value_a}{vc.unit} ({vc.document_a}) vs {vc.value_b}{vc.unit} ({vc.document_b})
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────────

function StatsBanner({ result }: { result: BriefingCompareResponse }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", background: "var(--bg-secondary, #f5f5f5)", borderRadius: "6px", padding: "10px", fontSize: "11px" }}>
      <div><span style={{ color: "var(--text-secondary)" }}>From: </span><strong>{result.document_a.filename}</strong> <span style={{ color: "var(--text-secondary)" }}>({result.document_a.page_count}pg, {result.document_a.tbd_count} TBDs)</span></div>
      <div><span style={{ color: "var(--text-secondary)" }}>To: </span><strong>{result.document_b.filename}</strong> <span style={{ color: "var(--text-secondary)" }}>({result.document_b.page_count}pg, {result.document_b.tbd_count} TBDs)</span></div>
      <div><span style={{ color: "#4caf50" }}>+{result.stats.total_tbds_resolved} TBDs resolved</span></div>
      <div><span style={{ color: "#f44336" }}>+{result.stats.total_tbds_introduced} TBDs introduced</span></div>
      <div><span style={{ color: "var(--text-secondary)" }}>{result.stats.total_value_changes} values changed</span></div>
      <div><span style={{ color: "var(--text-secondary)" }}>{result.stats.total_sections_changed} sections modified</span></div>
    </div>
  );
}

function SectionRow({
  section, expanded, onToggle, advancedMode, aiSummary, aiLoading, onAiSummarize, toRevPath,
}: {
  section: BriefingSectionResult;
  expanded: boolean;
  onToggle: () => void;
  advancedMode: boolean;
  aiSummary?: string;
  aiLoading: boolean;
  onAiSummarize: () => void;
  toRevPath: string;
}) {
  const isUnchanged = section.change_type === "unchanged";
  const isExpandable = !isUnchanged;
  const icon = { modified: "●", added: "+", removed: "−", unchanged: "○" }[section.change_type];
  const iconColor = { modified: "#ff9800", added: "#4caf50", removed: "#f44336", unchanged: "#bdbdbd" }[section.change_type];

  const handlePageClick = async (e: React.MouseEvent, page: number | null) => {
    e.stopPropagation();
    if (!page) return;
    const store = useEditorStore.getState();

    const toFilename = toRevPath.split(/[/\\]/).pop() || "";
    const currentFilename = store.documentPath.split(/[/\\]/).pop() || "";

    if (!store.documentLoaded || currentFilename !== toFilename) {
      await store.loadDocument(toRevPath);
      useEditorStore.getState().goToPage(page);
    } else if (store.currentPage !== page) {
      store.goToPage(page);
    }

    // Set in store — DocumentView will pick it up when overlays are ready on the right page
    useEditorStore.getState().setCompareHighlight(section.section_heading, page);
  };

  return (
    <div style={{ borderBottom: "1px solid var(--border, #eee)", marginBottom: "1px" }}>
      <div onClick={isExpandable ? onToggle : undefined}
        style={{ display: "flex", alignItems: "center", gap: "8px", padding: "7px 4px", cursor: isExpandable ? "pointer" : "default", fontSize: "12px", opacity: isUnchanged ? 0.6 : 1 }}>
        <span style={{ width: "12px", fontSize: "10px", color: "var(--text-secondary)" }}>{isExpandable ? (expanded ? "▾" : "▸") : ""}</span>
        <span style={{ color: iconColor, fontWeight: 700, fontSize: "14px", lineHeight: 1 }}>{icon}</span>
        <span style={{ flex: 1, fontWeight: isExpandable ? 500 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{section.section_heading}</span>
        {/* Page indicator — clickable to navigate */}
        {section.page_new && (
          <span
            onClick={(e) => handlePageClick(e, section.page_new)}
            title={`Go to page ${section.page_new}`}
            style={{ fontSize: "10px", color: "var(--accent, #1976d2)", cursor: "pointer", textDecoration: "underline", whiteSpace: "nowrap", marginRight: "4px" }}
          >
            p.{section.page_new}
          </span>
        )}
        <span style={{ fontSize: "10px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{section.summary_line}</span>
      </div>
      {expanded && isExpandable && (
        <SectionDetail section={section} advancedMode={advancedMode} aiSummary={aiSummary} aiLoading={aiLoading} onAiSummarize={onAiSummarize} />
      )}
    </div>
  );
}

function SectionDetail({ section, advancedMode, aiSummary, aiLoading, onAiSummarize }: {
  section: BriefingSectionResult;
  advancedMode: boolean;
  aiSummary?: string;
  aiLoading: boolean;
  onAiSummarize: () => void;
}) {
  return (
    <div style={{ padding: "6px 12px 12px 32px", fontSize: "11px", lineHeight: 1.6 }}>
      {/* Value changes */}
      {section.value_changes.length > 0 && (
        <div style={{ marginBottom: "8px" }}>
          <div style={{ fontWeight: 600, marginBottom: "3px" }}>Values changed:</div>
          {section.value_changes.map((vc, i) => (
            <div key={i} style={{ paddingLeft: "8px", color: "var(--text-secondary)" }}>
              ● {vc.parameter || "spec"}: <strong>{vc.old_value}{vc.unit}</strong> → <strong>{vc.new_value}{vc.unit}</strong>
            </div>
          ))}
        </div>
      )}

      {/* TBD changes */}
      {(section.tbd_delta.resolved.length > 0 || section.tbd_delta.introduced.length > 0) && (
        <div style={{ marginBottom: "8px" }}>
          <div style={{ fontWeight: 600, marginBottom: "3px" }}>TBD changes:</div>
          {section.tbd_delta.resolved.map((t, i) => (
            <div key={`r-${i}`} style={{ paddingLeft: "8px", color: "#4caf50" }}>✓ Resolved: {t.id} &mdash; {t.context}</div>
          ))}
          {section.tbd_delta.introduced.map((t, i) => (
            <div key={`i-${i}`} style={{ paddingLeft: "8px", color: "#f44336" }}>! Introduced: {t.id} &mdash; {t.context}</div>
          ))}
        </div>
      )}

      {/* Text changes — show specific diffs */}
      {(section.paragraphs_modified > 0 || section.paragraphs_added > 0 || section.paragraphs_removed > 0) && (
        <div style={{ marginBottom: "8px" }}>
          <div style={{ fontWeight: 600, marginBottom: "3px" }}>Text changes:</div>
          {section.text_snippets && section.text_snippets.length > 0 ? (
            <div style={{ paddingLeft: "8px" }}>
              {section.text_snippets.map((snippet, i) => (
                <div key={i} style={{
                  fontSize: "10px",
                  fontFamily: "monospace",
                  color: snippet.startsWith("+") ? "#2e7d32" : snippet.startsWith("-") ? "#c62828" : "var(--text-secondary)",
                  margin: "2px 0",
                  lineHeight: 1.4,
                }}>
                  {snippet}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ paddingLeft: "8px", color: "var(--text-secondary)" }}>
              {section.paragraphs_modified > 0 && <span>{section.paragraphs_modified} modified </span>}
              {section.paragraphs_added > 0 && <span style={{ color: "#4caf50" }}>+{section.paragraphs_added} added </span>}
              {section.paragraphs_removed > 0 && <span style={{ color: "#f44336" }}>-{section.paragraphs_removed} removed</span>}
            </div>
          )}
        </div>
      )}

      {/* Classification badges */}
      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap", marginBottom: advancedMode ? "10px" : "0" }}>
        {/* If AI summary exists, parse its classification; otherwise show local */}
        {(() => {
          const aiClass = aiSummary && !aiSummary.startsWith("[")
            ? parseAiClassification(aiSummary)
            : null;
          const displayClass = aiClass || section.classification;
          const isAiOverride = aiClass && aiClass !== section.classification;
          return (
            <span style={{
              fontSize: "10px", padding: "2px 6px", borderRadius: "3px",
              background: displayClass === "technical" ? "#fff3e0" : displayClass === "structural" ? "#e3f2fd" : "#f5f5f5",
              color: displayClass === "technical" ? "#e65100" : displayClass === "structural" ? "#1565c0" : "#757575",
              textDecoration: isAiOverride ? "none" : "none",
            }}>
              {displayClass}{isAiOverride ? " (AI)" : ""}
            </span>
          );
        })()}
        {section.has_requirement_change && !aiSummary && (
          <span style={{ fontSize: "10px", padding: "2px 6px", borderRadius: "3px", background: "#ffebee", color: "#c62828" }}>requirement change</span>
        )}
        {section.page_old && section.page_new && section.page_old !== section.page_new && (
          <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>moved: p.{section.page_old} → p.{section.page_new}</span>
        )}
      </div>

      {/* AI buttons (Advanced mode only) */}
      {advancedMode && (
        <div style={{ borderTop: "1px dashed var(--border, #ddd)", paddingTop: "8px", marginTop: "4px" }}>
          {aiSummary ? (
            <div style={{ background: "#f3e5f5", borderRadius: "4px", padding: "8px", fontSize: "11px", lineHeight: 1.5, color: "#4a148c" }}>
              <strong>AI Summary:</strong> {aiSummary}
            </div>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); onAiSummarize(); }}
              disabled={aiLoading}
              style={{
                fontSize: "10px", padding: "4px 10px", borderRadius: "4px",
                border: "1px solid #ce93d8", background: "#fce4ec", color: "#6a1b9a",
                cursor: aiLoading ? "wait" : "pointer",
              }}
            >
              {aiLoading ? "Summarizing..." : "Explain changes — ~$0.02"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────

function formatVersion(v: BriefingFamilyVersion): string {
  const parts: string[] = [];
  if (v.revision) parts.push(`Rev ${v.revision}`);
  if (v.date) parts.push(v.date);
  parts.push(`${v.page_count}pg`);
  const label = parts.join(" · ");
  if (!v.revision && !v.date) return `${v.filename} (${v.page_count}pg)`;
  return label;
}

/** Extract classification from AI summary text (looks for "Classification: X" pattern) */
function parseAiClassification(summary: string): string | null {
  const match = summary.match(/\*?\*?[Cc]lassification:?\*?\*?\s*(\w+)/);
  if (match) {
    const cls = match[1].toLowerCase();
    if (cls === "editorial" || cls === "technical" || cls === "structural") return cls;
  }
  return null;
}

function OcrProgress({ filename }: { filename: string }) {
  const [elapsed, setElapsed] = useState(0);
  const [statusMessage, setStatusMessage] = useState("Initializing OCR pipeline...");

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1;
        if (next < 3) setStatusMessage("Connecting to AWS Textract...");
        else if (next < 8) setStatusMessage("Uploading page images...");
        else if (next < 15) setStatusMessage("Extracting text from pages...");
        else if (next < 25) setStatusMessage("Processing text blocks...");
        else if (next < 40) setStatusMessage("Running text recognition...");
        else if (next < 60) setStatusMessage("Assembling document structure...");
        else setStatusMessage("Still processing — large documents take longer...");
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const progressWidth = Math.min(95, (elapsed / 60) * 100);

  return (
    <div style={{ background: "var(--bg-secondary, #f5f5f5)", borderRadius: "6px", padding: "14px", marginBottom: "12px" }}>
      <div style={{ fontSize: "12px", fontWeight: 600, marginBottom: "8px" }}>
        Running OCR on {filename}
      </div>
      <div style={{ width: "100%", height: "6px", background: "var(--bg-tertiary, #e0e0e0)", borderRadius: "3px", overflow: "hidden", marginBottom: "8px" }}>
        <div style={{ width: `${progressWidth}%`, height: "100%", background: "linear-gradient(90deg, #1976d2, #42a5f5)", borderRadius: "3px", transition: "width 1s linear" }} />
      </div>
      <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>{statusMessage}</div>
      <div style={{ fontSize: "10px", color: "var(--text-secondary)", marginTop: "4px" }}>Elapsed: {elapsed}s</div>
    </div>
  );
}
