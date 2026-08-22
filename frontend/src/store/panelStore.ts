import { create } from "zustand";

// ─── Types ────────────────────────────────────────────────────────────

export type PanelGroup = "editor" | "discover" | "sources" | "compare" | "session";

export type DiscoverTab = "search" | "tbd";
export type SourcesTab = "local" | "confluence" | "sharepoint" | "lineage";
export type SessionTab = "timeline" | "costs" | "credentials";

export interface SubTabs {
  discover: DiscoverTab;
  sources: SourcesTab;
  session: SessionTab;
}

export interface PanelVisibility {
  search: boolean;
  tbd: boolean;
  local: boolean;
  confluence: boolean;
  sharepoint: boolean;
  lineage: boolean;
  compare: boolean;
  timeline: boolean;
  costs: boolean;
  credentials: boolean;
}

// ─── Store ────────────────────────────────────────────────────────────

interface PanelState {
  activeGroup: PanelGroup;
  subTabs: SubTabs;
  visibility: PanelVisibility;
  panelManagerOpen: boolean;

  setActiveGroup: (group: PanelGroup) => void;
  setSubTab: <G extends keyof SubTabs>(group: G, tab: SubTabs[G]) => void;
  toggleVisibility: (panel: keyof PanelVisibility) => void;
  setVisibility: (panel: keyof PanelVisibility, visible: boolean) => void;
  setPanelManagerOpen: (open: boolean) => void;
}

// ─── Persistence ──────────────────────────────────────────────────────

const STORAGE_KEY = "icd-writer-panel-state";

function loadPersistedState(): Partial<Pick<PanelState, "activeGroup" | "subTabs" | "visibility">> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // Ignore corrupt localStorage
  }
  return {};
}

function persistState(state: Pick<PanelState, "activeGroup" | "subTabs" | "visibility">) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      activeGroup: state.activeGroup,
      subTabs: state.subTabs,
      visibility: state.visibility,
    }));
  } catch {
    // localStorage full or unavailable
  }
}

// ─── Defaults ─────────────────────────────────────────────────────────

const defaultVisibility: PanelVisibility = {
  search: true,
  tbd: true,
  local: true,
  confluence: false,  // disabled until configured
  sharepoint: false,  // disabled until configured
  lineage: true,
  compare: true,
  timeline: true,
  costs: false,
  credentials: true,
};

const defaultSubTabs: SubTabs = {
  discover: "search",
  sources: "local",
  session: "timeline",
};

// ─── Create Store ─────────────────────────────────────────────────────

const persisted = loadPersistedState();

export const usePanelStore = create<PanelState>((set, get) => ({
  activeGroup: persisted.activeGroup || "editor",
  subTabs: { ...defaultSubTabs, ...persisted.subTabs },
  visibility: { ...defaultVisibility, ...persisted.visibility },
  panelManagerOpen: false,

  setActiveGroup: (group) => {
    set({ activeGroup: group });
    persistState(get());
  },

  setSubTab: (group, tab) => {
    set((s) => ({
      subTabs: { ...s.subTabs, [group]: tab },
    }));
    persistState(get());
  },

  toggleVisibility: (panel) => {
    set((s) => ({
      visibility: { ...s.visibility, [panel]: !s.visibility[panel] },
    }));
    persistState(get());
  },

  setVisibility: (panel, visible) => {
    set((s) => ({
      visibility: { ...s.visibility, [panel]: visible },
    }));
    persistState(get());
  },

  setPanelManagerOpen: (open) => set({ panelManagerOpen: open }),
}));
