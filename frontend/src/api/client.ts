const API_BASE = "http://localhost:8000";

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
};
