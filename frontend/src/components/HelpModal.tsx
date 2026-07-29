import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

type HelpTab = "how-it-works" | "evaluation" | "about";

interface EvalQuery {
  query_id: string;
  query: string;
  expected_terms: string[];
  expected_pages: number[];
  category: string;
}

interface EvalSuite {
  documents: Record<string, EvalQuery[]>;
  total_queries: number;
  metrics_measured: string[];
}

interface HelpModalProps {
  initialTab?: HelpTab;
  onClose: () => void;
}

export function HelpModal({ initialTab = "how-it-works", onClose }: HelpModalProps) {
  const [activeTab, setActiveTab] = useState<HelpTab>(initialTab);
  const [evalData, setEvalData] = useState<EvalSuite | null>(null);

  useEffect(() => {
    if (activeTab === "evaluation" && !evalData) {
      fetch(`${API_BASE}/search/evaluation-suite`)
        .then((r) => r.json())
        .then(setEvalData)
        .catch(() => {});
    }
  }, [activeTab, evalData]);

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: "var(--bg-primary, #fff)", borderRadius: "12px", width: "700px", maxWidth: "90vw",
        maxHeight: "80vh", display: "flex", flexDirection: "column", boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 600, flex: 1 }}>Help</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: "18px", cursor: "pointer", color: "var(--text-secondary)" }}>✕</button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border)", padding: "0 20px" }}>
          <TabButton label="How It Works" active={activeTab === "how-it-works"} onClick={() => setActiveTab("how-it-works")} />
          <TabButton label="Evaluation Suite" active={activeTab === "evaluation"} onClick={() => setActiveTab("evaluation")} />
          <TabButton label="About" active={activeTab === "about"} onClick={() => setActiveTab("about")} />
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
          {activeTab === "how-it-works" && <HowItWorks />}
          {activeTab === "evaluation" && <EvaluationSuite data={evalData} />}
          {activeTab === "about" && <About />}
        </div>
      </div>
    </div>
  );
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      padding: "10px 16px", border: "none", background: "transparent", cursor: "pointer", fontSize: "13px",
      fontWeight: active ? 600 : 400, color: active ? "var(--text-primary)" : "var(--text-secondary)",
      borderBottom: active ? "2px solid var(--accent, #1976d2)" : "2px solid transparent",
    }}>{label}</button>
  );
}

/* ─── How It Works ─────────────────────────────────────────── */

function HowItWorks() {
  return (
    <div style={{ fontSize: "13px", lineHeight: 1.7, color: "var(--text-primary)" }}>
      <p style={{ color: "var(--text-secondary)", marginBottom: "16px" }}>
        When you upload a PDF, the system runs a multi-stage pipeline to make it searchable, editable, and trackable.
      </p>

      <PipelineStep number={1} title="Extraction" >
        Your PDF is parsed using PyMuPDF (a Python binding for MuPDF) into structured text blocks.
        Each block preserves its bounding box coordinates, font name, font size, reading order, and
        page position. The system detects whether a block is a paragraph, heading, list item, table,
        header, or footer based on font size, position, and content patterns.
      </PipelineStep>

      <PipelineStep number={2} title="Chunking (Text Segmentation)">
        The extracted text is split into searchable segments called "chunks." Four strategies run in parallel
        to maximize retrieval quality:
        <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
          <li><strong>Paragraph</strong> — Each text block becomes a chunk (natural document boundaries)</li>
          <li><strong>Section</strong> — Full sections from one heading to the next (broader context)</li>
          <li><strong>Sliding Window</strong> — 256-token overlapping windows (catches cross-paragraph concepts)</li>
          <li><strong>Fixed Words</strong> — 512-token non-overlapping windows (consistent sizing)</li>
        </ul>
        Each chunk retains metadata: source document, page number, section heading, and content type.
      </PipelineStep>

      <PipelineStep number={3} title="Embedding (Vector Representation)">
        Each chunk is sent to Amazon Web Services (AWS) Bedrock to generate a 1024-dimensional
        embedding vector — a mathematical fingerprint capturing the chunk's semantic meaning.
        Two embedding models are used:
        <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
          <li><strong>Amazon Titan Embed Text V2</strong> — 1024 dimensions, optimized for technical text</li>
          <li><strong>Cohere Embed English V3</strong> — 1024 dimensions, strong on synonyms and paraphrasing</li>
        </ul>
        Texts with similar meanings produce similar vectors, even if they use completely different words.
      </PipelineStep>

      <PipelineStep number={4} title="Indexing (OpenSearch Storage)">
        Chunks and their vectors are stored in OpenSearch (an open-source search engine) across
        4 index configurations (2 models × 2 chunking strategies). Each index supports:
        <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
          <li><strong>BM25 keyword search</strong> — Exact word matching with term frequency ranking</li>
          <li><strong>k-Nearest Neighbor (kNN) vector search</strong> — Semantic similarity via HNSW algorithm</li>
          <li><strong>Hybrid Reciprocal Rank Fusion (RRF)</strong> — Merges keyword and vector results by position</li>
        </ul>
      </PipelineStep>

      <PipelineStep number={5} title="Retrieval-Augmented Generation (RAG)">
        When you ask a question, the system:
        <ol style={{ margin: "8px 0", paddingLeft: "20px" }}>
          <li>Retrieves the top-k most relevant chunks via hybrid search</li>
          <li>Builds a context window with numbered passages and metadata</li>
          <li>Sends the context + your question to Amazon Nova Pro (a large language model)</li>
          <li>The model generates an answer citing only the provided passages</li>
          <li>Confidence is assessed based on retrieval scores and answer coverage</li>
        </ol>
        The model is instructed to never use outside knowledge — answers come exclusively from your documents.
      </PipelineStep>

      <PipelineStep number={6} title="TBD/TBR Detection">
        The system scans all text blocks for unresolved item markers:
        <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
          <li><strong>TBD</strong> — To Be Determined (value not yet known)</li>
          <li><strong>TBR</strong> — To Be Reviewed (value needs verification)</li>
          <li><strong>TBC</strong> — To Be Confirmed</li>
          <li><strong>TBS</strong> — To Be Supplied</li>
        </ul>
        Items appearing in "shall" statements are flagged as contractually blocking.
        Cross-document correlation identifies related TBD items across different Interface Control Documents.
      </PipelineStep>
    </div>
  );
}

function PipelineStep({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
        <span style={{
          width: "24px", height: "24px", borderRadius: "50%", background: "var(--accent, #1976d2)",
          color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "12px", fontWeight: 600, flexShrink: 0,
        }}>{number}</span>
        <strong style={{ fontSize: "14px" }}>{title}</strong>
      </div>
      <div style={{ paddingLeft: "34px" }}>{children}</div>
    </div>
  );
}

/* ─── Evaluation Suite ─────────────────────────────────────── */

function EvaluationSuite({ data }: { data: EvalSuite | null }) {
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  if (!data) {
    return <div style={{ textAlign: "center", padding: "40px", color: "var(--text-secondary)" }}>Loading evaluation data...</div>;
  }

  const docKeys = Object.keys(data.documents).filter((k) => k !== "_expanded");

  return (
    <div style={{ fontSize: "13px", color: "var(--text-primary)" }}>
      <p style={{ color: "var(--text-secondary)", marginBottom: "12px" }}>
        The search quality is validated against <strong>{data.total_queries} ground truth queries</strong> across {docKeys.length} documents.
        Each query has expected terms and page numbers that must appear in the top results.
      </p>

      {/* Metrics */}
      <div style={{ background: "var(--bg-secondary)", borderRadius: "6px", padding: "12px", marginBottom: "16px" }}>
        <div style={{ fontWeight: 600, marginBottom: "6px" }}>Quality Metrics Measured:</div>
        <ul style={{ margin: 0, paddingLeft: "20px" }}>
          {data.metrics_measured.map((m, i) => (
            <li key={i} style={{ margin: "4px 0" }}>{m}</li>
          ))}
        </ul>
      </div>

      {/* Per-document queries */}
      {docKeys.map((docKey) => {
        const queries = data.documents[docKey];
        const expanded = expandedDoc === docKey;
        return (
          <div key={docKey} style={{ marginBottom: "8px", border: "1px solid var(--border)", borderRadius: "6px" }}>
            <div
              onClick={() => setExpandedDoc(expanded ? null : docKey)}
              style={{ padding: "10px 12px", cursor: "pointer", display: "flex", alignItems: "center", gap: "8px" }}
            >
              <span>{expanded ? "▼" : "▶"}</span>
              <strong>{docKey}</strong>
              <span style={{ color: "var(--text-secondary)", marginLeft: "auto" }}>{queries.length} queries</span>
            </div>
            {expanded && (
              <div style={{ padding: "0 12px 12px", borderTop: "1px solid var(--border)" }}>
                <table style={{ width: "100%", fontSize: "11px", borderCollapse: "collapse", marginTop: "8px" }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border)" }}>
                      <th style={{ padding: "4px 6px", width: "55px" }}>ID</th>
                      <th style={{ padding: "4px 6px" }}>Query</th>
                      <th style={{ padding: "4px 6px", width: "80px" }}>Category</th>
                      <th style={{ padding: "4px 6px" }}>Expected Terms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queries.map((q) => (
                      <tr key={q.query_id} style={{ borderBottom: "1px solid var(--border-light, #eee)" }}>
                        <td style={{ padding: "4px 6px", fontFamily: "monospace", color: "var(--text-secondary)" }}>{q.query_id}</td>
                        <td style={{ padding: "4px 6px" }}>{q.query}</td>
                        <td style={{ padding: "4px 6px" }}>
                          <span style={{
                            fontSize: "10px", padding: "1px 4px", borderRadius: "3px",
                            background: "var(--bg-tertiary, #f0f0f0)",
                          }}>{q.category}</span>
                        </td>
                        <td style={{ padding: "4px 6px", color: "var(--text-secondary)" }}>{q.expected_terms.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}

      {/* Expanded queries */}
      {data.documents["_expanded"] && data.documents["_expanded"].length > 0 && (
        <div style={{ marginTop: "12px", padding: "10px 12px", background: "var(--bg-secondary)", borderRadius: "6px" }}>
          <div style={{ fontWeight: 600, marginBottom: "4px" }}>
            Expanded Query Set ({data.documents["_expanded"].length} additional queries)
          </div>
          <p style={{ color: "var(--text-secondary)", margin: "4px 0", fontSize: "11px" }}>
            Additional queries added for statistical confidence across all documents and categories.
          </p>
        </div>
      )}
    </div>
  );
}

/* ─── About ────────────────────────────────────────────────── */

function About() {
  return (
    <div style={{ fontSize: "13px", color: "var(--text-primary)" }}>
      <h3 style={{ margin: "0 0 16px", fontSize: "18px" }}>ICD Writer</h3>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <tbody>
          <InfoRow label="Version" value="1.1.0" />
          <InfoRow label="Purpose" value="NASA Interface Control Document editor with semantic search, TBD tracking, and version comparison" />
          <InfoRow label="Backend" value="Python 3.10, FastAPI, PyMuPDF, WeasyPrint, OpenSearch" />
          <InfoRow label="Frontend" value="React 19, TypeScript, Vite, Zustand" />
          <InfoRow label="Search" value="OpenSearch 2.17 (BM25 + kNN hybrid), AWS Bedrock embeddings" />
          <InfoRow label="AI Generation" value="Amazon Nova Pro via Retrieval-Augmented Generation" />
          <InfoRow label="Embedding Models" value="Amazon Titan Embed Text V2, Cohere Embed English V3 (1024 dimensions)" />
          <InfoRow label="License" value="MIT" />
        </tbody>
      </table>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <tr style={{ borderBottom: "1px solid var(--border-light, #eee)" }}>
      <td style={{ padding: "8px 12px", fontWeight: 500, whiteSpace: "nowrap", verticalAlign: "top", width: "140px" }}>{label}</td>
      <td style={{ padding: "8px 12px", color: "var(--text-secondary)" }}>{value}</td>
    </tr>
  );
}
