const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────

export interface ConnectorInfo {
  type: string;
  configured: boolean;
  enabled: boolean;
  url: string;
}

export interface RemoteSpace {
  id: string;
  name: string;
  key: string;
  description: string;
}

export interface RemotePage {
  id: string;
  title: string;
  space_id: string;
  parent_id: string | null;
  version: number;
  modified_at: string;
  author: string;
  has_children: boolean;
}

export interface RemoteFile {
  id: string;
  filename: string;
  size_bytes: number;
  media_type: string;
  download_url: string;
  modified_at: string;
  version_count: number;
}

export interface RemoteVersion {
  id: string;
  modified_at: string;
  size_bytes: number;
  author: string;
}

// ─── API Methods ──────────────────────────────────────────────────────

export const connectorsApi = {
  async listConnectors(): Promise<{ connectors: ConnectorInfo[] }> {
    const res = await fetch(`${API_BASE}/connectors`);
    return res.json();
  },

  async configure(
    type: "confluence" | "sharepoint",
    url: string,
    token: string,
    siteId?: string
  ): Promise<{ status: string; connected: boolean }> {
    const body: Record<string, string> = { url, token };
    if (siteId) body.site_id = siteId;
    const res = await fetch(`${API_BASE}/connectors/${type}/configure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return res.json();
  },

  async testConnection(type: string): Promise<{ connected: boolean }> {
    const res = await fetch(`${API_BASE}/connectors/${type}/test`);
    return res.json();
  },

  async listSpaces(type: string): Promise<{ spaces: RemoteSpace[] }> {
    const res = await fetch(`${API_BASE}/connectors/${type}/spaces`);
    if (!res.ok) throw new Error(`Failed to list spaces: ${res.status}`);
    return res.json();
  },

  async listPages(type: string, spaceId: string): Promise<{ pages: RemotePage[] }> {
    const res = await fetch(`${API_BASE}/connectors/${type}/spaces/${spaceId}/pages`);
    if (!res.ok) throw new Error(`Failed to list pages: ${res.status}`);
    return res.json();
  },

  async listFiles(type: string, pageId: string): Promise<{ files: RemoteFile[] }> {
    const res = await fetch(`${API_BASE}/connectors/${type}/pages/${pageId}/files`);
    if (!res.ok) throw new Error(`Failed to list files: ${res.status}`);
    return res.json();
  },

  async getVersions(type: string, fileId: string): Promise<{ versions: RemoteVersion[] }> {
    const res = await fetch(`${API_BASE}/connectors/${type}/files/${fileId}/versions`);
    if (!res.ok) throw new Error(`Failed to get versions: ${res.status}`);
    return res.json();
  },
};
