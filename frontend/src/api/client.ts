const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export interface TextBlock {
  id: string;
  text: string;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  type: string;
  font_size: number | null;
  confidence: number;
  is_ocr: boolean;
}

export interface PageData {
  page_number: number;
  width_pt: number;
  height_pt: number;
  blocks: TextBlock[];
}

export interface SessionInfo {
  session_id: string;
  started_at: string;
  document: string;
  edit_count: number;
  action_count: number;
}

export interface IngestStatus {
  ingest_id: string;
  filename: string;
  pdf_path: string;
  status: "uploading" | "extracting" | "indexing" | "detecting_tbds" | "done" | "error";
  step: number;
  total_steps: number;
  message: string;
  progress_pct: number;
  pages: number;
  text_blocks: number;
  chunks_indexed: number;
  tbd_count: number;
  tbr_count: number;
  error: string | null;
  done: boolean;
}

export const api = {
  async startSession(): Promise<{ session_id: string }> {
    const res = await fetch(`${API_BASE}/session/start`, { method: "POST" });
    return res.json();
  },

  async getSession(): Promise<SessionInfo> {
    const res = await fetch(`${API_BASE}/session`);
    return res.json();
  },

  async openDocument(path: string): Promise<any> {
    const res = await fetch(
      `${API_BASE}/document/open?pdf_path=${encodeURIComponent(path)}`,
      { method: "POST" }
    );
    return res.json();
  },

  async getPage(pageNumber: number): Promise<PageData> {
    const res = await fetch(`${API_BASE}/document/page/${pageNumber}`);
    return res.json();
  },

  async editBlock(blockId: string, newText: string): Promise<any> {
    const res = await fetch(`${API_BASE}/document/block/${blockId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_text: newText }),
    });
    return res.json();
  },

  async undo(): Promise<any> {
    const res = await fetch(`${API_BASE}/document/undo`, { method: "POST" });
    if (!res.ok) return { status: "nothing_to_undo" };
    return res.json();
  },

  async redo(): Promise<any> {
    const res = await fetch(`${API_BASE}/document/redo`, { method: "POST" });
    if (!res.ok) return { status: "nothing_to_redo" };
    return res.json();
  },

  async getActions(): Promise<any> {
    const res = await fetch(`${API_BASE}/session/actions`);
    return res.json();
  },

  async saveSession(): Promise<any> {
    const res = await fetch(`${API_BASE}/session/save`, { method: "POST" });
    return res.json();
  },

  async exportPdf(): Promise<any> {
    const res = await fetch(`${API_BASE}/document/export`, { method: "POST" });
    return res.json();
  },

  getPageImageUrl(pageNumber: number): string {
    return `${API_BASE}/document/page/${pageNumber}/image`;
  },

  // ─── Search & RAG ──────────────────────────────────────────

  async listDocuments(): Promise<any> {
    const res = await fetch(`${API_BASE}/documents`);
    return res.json();
  },

  async getDocumentFamilies(): Promise<any> {
    const res = await fetch(`${API_BASE}/documents/families`);
    return res.json();
  },

  async getSessionCosts(): Promise<any> {
    const res = await fetch(`${API_BASE}/session/costs`);
    return res.json();
  },

  getSessionCostsExportUrl(): string {
    return `${API_BASE}/session/costs/export`;
  },

  async getRelatedVersions(pdfPath: string): Promise<any> {
    const res = await fetch(`${API_BASE}/documents/related?pdf_path=${encodeURIComponent(pdfPath)}`);
    return res.json();
  },

  async runVersionDiff(versionA: string, versionB: string, format: string = "markdown"): Promise<any> {
    const params = new URLSearchParams({ version_a: versionA, version_b: versionB, format });
    const res = await fetch(`${API_BASE}/documents/diff?${params}`, { method: "POST" });
    return res.json();
  },

  async summarizeDiffSection(versionA: string, versionB: string, sectionHeading: string): Promise<any> {
    const params = new URLSearchParams({ version_a: versionA, version_b: versionB, section_heading: sectionHeading });
    const res = await fetch(`${API_BASE}/documents/diff/summarize?${params}`, { method: "POST" });
    return res.json();
  },

  async search(query: string, k: number = 10, mode: string = "rrf", rag: boolean = false, model: string = ""): Promise<any> {
    const params = new URLSearchParams({
      query,
      k: String(k),
      mode,
      rag: String(rag),
    });
    if (model) params.set("model", model);
    const res = await fetch(`${API_BASE}/search?${params}`, { method: "POST" });
    return res.json();
  },

  // ─── TBD Dashboard ─────────────────────────────────────────

  async getTbdDashboard(filters?: { status?: string; item_type?: string; document?: string }): Promise<any> {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.item_type) params.set("item_type", filters.item_type);
    if (filters?.document) params.set("document", filters.document);
    const res = await fetch(`${API_BASE}/tbd-dashboard?${params}`);
    return res.json();
  },

  async ingestTbdDocuments(): Promise<any> {
    const res = await fetch(`${API_BASE}/tbd-dashboard/ingest`, { method: "POST" });
    return res.json();
  },

  async updateTbdItem(itemId: string, updates: { status?: string; owner?: string; resolution_value?: string }): Promise<any> {
    const params = new URLSearchParams();
    if (updates.status) params.set("status", updates.status);
    if (updates.owner) params.set("owner", updates.owner);
    if (updates.resolution_value) params.set("resolution_value", updates.resolution_value);
    const res = await fetch(`${API_BASE}/tbd-dashboard/item/${encodeURIComponent(itemId)}?${params}`, {
      method: "PUT",
    });
    return res.json();
  },

  // ─── Document Ingestion (Upload + Full Pipeline) ───────────

  ingestDocument(
    file: File,
    onUploadProgress?: (pct: number) => void
  ): Promise<{ ingest_id: string; status: string; filename: string }> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/document/ingest`);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onUploadProgress) {
          onUploadProgress(Math.round((e.loaded / e.total) * 100));
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
        }
      };

      xhr.onerror = () => reject(new Error("Network error during upload"));

      const formData = new FormData();
      formData.append("file", file);
      xhr.send(formData);
    });
  },

  async getIngestStatus(ingestId: string): Promise<IngestStatus> {
    const res = await fetch(`${API_BASE}/document/ingest/status/${ingestId}`);
    return res.json();
  },

  async deleteDocument(docStem: string): Promise<any> {
    const res = await fetch(`${API_BASE}/document/${encodeURIComponent(docStem)}`, {
      method: "DELETE",
    });
    return res.json();
  },

  // ─── Briefing Consolidation (Revision Compare) ─────────────

  async getBriefingFamilies(): Promise<BriefingFamiliesResponse> {
    const res = await fetch(`${API_BASE}/briefing/families`);
    return res.json();
  },

  async runBriefingCompare(versionA: string, versionB: string): Promise<BriefingCompareResponse> {
    const params = new URLSearchParams({ version_a: versionA, version_b: versionB });
    const res = await fetch(`${API_BASE}/briefing/compare?${params}`, { method: "POST" });
    return res.json();
  },
};

// ─── Briefing Types ───────────────────────────────────────────

export interface BriefingFamilyVersion {
  stem: string;
  filename: string;
  path: string;
  revision: string;
  date: string;
  page_count: number;
  doc_type: string;
}

export interface BriefingFamily {
  family_name: string;
  status: string;
  versions: BriefingFamilyVersion[];
}

export interface BriefingFamiliesResponse {
  families: BriefingFamily[];
}

export interface BriefingDocSummary {
  stem: string;
  filename: string;
  path: string;
  revision: string;
  date: string;
  page_count: number;
  tbd_count: number;
  tbr_count: number;
  doc_type: string;
}

export interface BriefingValueChange {
  parameter: string;
  old_value: number;
  new_value: number;
  unit: string;
  old_context: string;
  new_context: string;
}

export interface BriefingTbdDelta {
  resolved: { id: string; item_type: string; context: string }[];
  introduced: { id: string; item_type: string; context: string }[];
  net_change: number;
}

export interface BriefingSectionResult {
  section_heading: string;
  change_type: "modified" | "added" | "removed" | "unchanged";
  summary_line: string;
  classification: string;
  has_requirement_change: boolean;
  page_old: number | null;
  page_new: number | null;
  paragraphs_modified: number;
  paragraphs_added: number;
  paragraphs_removed: number;
  text_snippets: string[];
  value_changes: BriefingValueChange[];
  tbd_delta: BriefingTbdDelta;
}

export interface BriefingCrossRef {
  source_document: string;
  target_document: string;
  reference_text: string;
  section: string;
  page: number;
  ref_type: string;
}

export interface BriefingValueConflict {
  parameter: string;
  value_a: number;
  value_b: number;
  unit: string;
  context_a: string;
  context_b: string;
  document_a: string;
  document_b: string;
}

export interface BriefingMaturityScore {
  section: string;
  score: number;
  rating: string;
  tbd_count: number;
  total_blocks: number;
}

export interface BriefingCompareResponse {
  document_a: BriefingDocSummary;
  document_b: BriefingDocSummary;
  stats: {
    total_value_changes: number;
    total_tbds_resolved: number;
    total_tbds_introduced: number;
    total_sections_changed: number;
    total_sections_unchanged: number;
  };
  sections: BriefingSectionResult[];
  global_changes: string[];
  cross_references: BriefingCrossRef[];
  value_conflicts: BriefingValueConflict[];
  maturity_a: BriefingMaturityScore[];
  maturity_b: BriefingMaturityScore[];
  generated_at: string;
}
