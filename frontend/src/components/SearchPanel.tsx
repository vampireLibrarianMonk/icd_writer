import { useState, useRef, useEffect } from "react";
import { api } from "../api/client";

interface Citation {
  label: string;
  document_title: string;
  page_number: number;
  section_heading: string | null;
  chunk_text: string;
}

interface SearchHit {
  chunk_id: string;
  text: string;
  score: number;
  document_title: string;
  page_number: number;
  section_heading: string | null;
  content_type: string;
}

interface RAGResult {
  type: "rag";
  query: string;
  answer: string;
  confidence: string;
  citations: Citation[];
  warnings: string[];
  cost_usd: number;
  time_ms: number;
}

interface SearchResult {
  type: "search";
  query: string;
  total_hits: number;
  took_ms: number;
  hits: SearchHit[];
}

type Result = RAGResult | SearchResult;

interface HistoryEntry {
  query: string;
  result: Result;
}

export function SearchPanel() {
  const [query, setQuery] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (resultsRef.current) {
      resultsRef.current.scrollTop = resultsRef.current.scrollHeight;
    }
  }, [history]);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const result = await api.search(query.trim(), 8, "rrf", useRag);
      setHistory((prev) => [...prev, { query: query.trim(), result }]);
      setQuery("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px" }}>
      {/* Header */}
      <div style={{ marginBottom: "12px" }}>
        <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>ICD Search</h3>
        <p style={{ margin: "4px 0 0", fontSize: "11px", color: "var(--text-secondary)" }}>
          Ask questions about your ICDs in plain language
        </p>
      </div>

      {/* Results area */}
      <div
        ref={resultsRef}
        style={{
          flex: 1,
          overflowY: "auto",
          marginBottom: "12px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        {history.length === 0 && !loading && (
          <div style={{ color: "var(--text-secondary)", fontSize: "12px", textAlign: "center", padding: "40px 20px" }}>
            <p style={{ fontSize: "24px", margin: "0 0 12px" }}>🔍</p>
            <p>Try asking:</p>
            <ul style={{ listStyle: "none", padding: 0, margin: "8px 0" }}>
              <li style={{ margin: "4px 0", cursor: "pointer", color: "var(--accent)" }}
                  onClick={() => setQuery("What are the thermal limits for the spectrometer?")}>
                "What are the thermal limits for the spectrometer?"
              </li>
              <li style={{ margin: "4px 0", cursor: "pointer", color: "var(--accent)" }}
                  onClick={() => setQuery("Who is responsible for the thermal design?")}>
                "Who is responsible for the thermal design?"
              </li>
              <li style={{ margin: "4px 0", cursor: "pointer", color: "var(--accent)" }}
                  onClick={() => setQuery("What items are still TBD?")}>
                "What items are still TBD?"
              </li>
            </ul>
          </div>
        )}

        {history.map((entry, idx) => (
          <div key={idx}>
            {/* User query */}
            <div style={{
              background: "var(--bg-tertiary, #f0f4ff)",
              borderRadius: "8px",
              padding: "8px 12px",
              marginBottom: "8px",
              fontSize: "13px",
              fontWeight: 500,
            }}>
              {entry.query}
            </div>

            {/* Answer */}
            {entry.result.type === "rag" ? (
              <RAGAnswerView result={entry.result} />
            ) : (
              <SearchResultsView result={entry.result} />
            )}
          </div>
        ))}

        {loading && (
          <div style={{ textAlign: "center", padding: "20px", color: "var(--text-secondary)" }}>
            <span style={{ animation: "pulse 1.5s infinite" }}>Searching...</span>
          </div>
        )}

        {error && (
          <div style={{ color: "#d32f2f", fontSize: "12px", padding: "8px" }}>
            Error: {error}
          </div>
        )}
      </div>

      {/* Input area */}
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "12px" }}>
        <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
          <label style={{ fontSize: "11px", display: "flex", alignItems: "center", gap: "4px" }}>
            <input
              type="checkbox"
              checked={useRag}
              onChange={(e) => setUseRag(e.target.checked)}
            />
            AI Answer (with citations)
          </label>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your ICDs..."
            disabled={loading}
            style={{
              flex: 1,
              padding: "8px 12px",
              borderRadius: "6px",
              border: "1px solid var(--border)",
              fontSize: "13px",
              background: "var(--bg-primary)",
              color: "var(--text-primary)",
            }}
          />
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            style={{ padding: "8px 16px", borderRadius: "6px" }}
          >
            {loading ? "..." : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RAGAnswerView({ result }: { result: RAGResult }) {
  const [showCitations, setShowCitations] = useState(false);

  return (
    <div style={{ fontSize: "13px", lineHeight: 1.6 }}>
      {/* Answer text */}
      <div style={{
        whiteSpace: "pre-wrap",
        padding: "8px 0",
      }}>
        {result.answer}
      </div>

      {/* Warnings */}
      {result.warnings.map((w, i) => (
        <div key={i} style={{
          background: "#fff3e0",
          borderRadius: "4px",
          padding: "6px 10px",
          fontSize: "11px",
          margin: "4px 0",
          color: "#e65100",
        }}>
          ⚠️ {w}
        </div>
      ))}

      {/* Metadata bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "12px",
        marginTop: "8px",
        fontSize: "11px",
        color: "var(--text-secondary)",
      }}>
        <span style={{
          padding: "2px 6px",
          borderRadius: "3px",
          background: result.confidence === "high" ? "#e8f5e9" :
                      result.confidence === "medium" ? "#fff3e0" : "#ffebee",
          color: result.confidence === "high" ? "#2e7d32" :
                 result.confidence === "medium" ? "#e65100" : "#c62828",
          fontWeight: 500,
        }}>
          {result.confidence} confidence
        </span>
        <span>{result.time_ms.toFixed(0)}ms</span>
        <span>${result.cost_usd.toFixed(4)}</span>
        <button
          onClick={() => setShowCitations(!showCitations)}
          style={{
            background: "none",
            border: "none",
            color: "var(--accent)",
            cursor: "pointer",
            fontSize: "11px",
            padding: 0,
          }}
        >
          {showCitations ? "Hide" : "Show"} sources ({result.citations.length})
        </button>
      </div>

      {/* Citations */}
      {showCitations && (
        <div style={{
          marginTop: "8px",
          borderTop: "1px solid var(--border)",
          paddingTop: "8px",
        }}>
          {result.citations.map((c, i) => (
            <div key={i} style={{
              padding: "6px 8px",
              margin: "4px 0",
              background: "var(--bg-secondary)",
              borderRadius: "4px",
              fontSize: "11px",
            }}>
              <div style={{ fontWeight: 500, marginBottom: "2px" }}>
                [{i + 1}] {c.label}
              </div>
              <div style={{ color: "var(--text-secondary)" }}>
                {c.chunk_text}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SearchResultsView({ result }: { result: SearchResult }) {
  return (
    <div style={{ fontSize: "12px" }}>
      <div style={{ color: "var(--text-secondary)", marginBottom: "8px" }}>
        {result.total_hits} results in {result.took_ms}ms
      </div>
      {result.hits.map((hit, i) => (
        <div key={i} style={{
          padding: "8px",
          margin: "4px 0",
          background: "var(--bg-secondary)",
          borderRadius: "4px",
          borderLeft: "3px solid var(--accent)",
        }}>
          <div style={{ fontWeight: 500, marginBottom: "2px" }}>
            {hit.document_title} — p{hit.page_number}
            {hit.section_heading && <span style={{ fontWeight: 400 }}> / {hit.section_heading}</span>}
          </div>
          <div style={{ color: "var(--text-secondary)", fontSize: "11px" }}>
            {hit.text.slice(0, 150)}{hit.text.length > 150 ? "..." : ""}
          </div>
          <div style={{ fontSize: "10px", color: "#999", marginTop: "4px" }}>
            Score: {hit.score.toFixed(4)} | {hit.content_type}
          </div>
        </div>
      ))}
    </div>
  );
}
