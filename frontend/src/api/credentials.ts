const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export interface StoredCredential {
  id: string;
  service: string;
  name: string;
  url: string;
  site_id: string;
  notes: string;
  token_preview: string;
  created_at: string;
  last_tested: string | null;
  last_test_result: string | null;
}

export interface CreateCredentialRequest {
  service: string;
  name: string;
  url: string;
  token: string;
  site_id?: string;
  notes?: string;
}

export const credentialsApi = {
  async list(): Promise<{ credentials: StoredCredential[] }> {
    const res = await fetch(`${API_BASE}/credentials`);
    return res.json();
  },

  async create(req: CreateCredentialRequest): Promise<{ id: string; status: string }> {
    const res = await fetch(`${API_BASE}/credentials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    return res.json();
  },

  async update(id: string, fields: Partial<CreateCredentialRequest>): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE}/credentials/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });
    return res.json();
  },

  async delete(id: string): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE}/credentials/${id}`, { method: "DELETE" });
    return res.json();
  },

  async test(id: string): Promise<{ connected: boolean; error: string | null; tested_at: string }> {
    const res = await fetch(`${API_BASE}/credentials/${id}/test`, { method: "POST" });
    return res.json();
  },
};
