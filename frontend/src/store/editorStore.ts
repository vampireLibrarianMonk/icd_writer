import { create } from "zustand";
import { api } from "../api/client";
import type { TextBlock, PageData } from "../api/client";

interface EditorState {
  // Document state
  documentLoaded: boolean;
  documentPath: string;
  totalPages: number;
  currentPage: number;
  pageData: PageData | null;

  // Selection
  selectedBlock: TextBlock | null;
  editText: string;

  // Compare highlight (section heading to highlight on current page)
  compareHighlight: string | null;
  compareHighlightPage: number | null;

  // Session
  sessionId: string | null;
  editCount: number;
  refreshTrigger: number;
  canUndo: boolean;
  canRedo: boolean;

  // Actions
  loadDocument: (path: string) => Promise<void>;
  goToPage: (page: number) => Promise<void>;
  selectBlock: (block: TextBlock | null) => void;
  setEditText: (text: string) => void;
  setCompareHighlight: (heading: string | null, page?: number | null) => void;
  applyEdit: () => Promise<void>;
  revertEdit: () => void;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
}

export const useEditorStore = create<EditorState>((set, get) => ({
  documentLoaded: false,
  documentPath: "",
  totalPages: 0,
  currentPage: 1,
  pageData: null,
  selectedBlock: null,
  editText: "",
  compareHighlight: null,
  compareHighlightPage: null,
  sessionId: null,
  editCount: 0,
  refreshTrigger: 0,
  canUndo: false,
  canRedo: false,

  loadDocument: async (path: string) => {
    // Start session
    const session = await api.startSession();

    // Open document
    const result = await api.openDocument(path);
    if (result.status === "ready") {
      set({
        documentLoaded: true,
        documentPath: path,
        totalPages: result.pages,
        currentPage: 1,
        sessionId: session.session_id,
      });
      // Load first page
      await get().goToPage(1);

      // Notify if related versions exist
      if (result.related_versions && result.related_versions.length > 0) {
        window.dispatchEvent(new CustomEvent("related-versions-found", {
          detail: { currentPath: path, relatedVersions: result.related_versions },
        }));
      }
    }
  },

  goToPage: async (page: number) => {
    const { totalPages } = get();
    if (page < 1 || page > totalPages) return;

    const pageData = await api.getPage(page);
    set({ currentPage: page, pageData, selectedBlock: null, editText: "" });
  },

  selectBlock: (block: TextBlock | null) => {
    set({ selectedBlock: block, editText: block?.text || "" });
  },

  setEditText: (text: string) => {
    set({ editText: text });
  },

  setCompareHighlight: (heading: string | null, page?: number | null) => {
    set({ compareHighlight: heading, compareHighlightPage: page ?? null });
  },

  applyEdit: async () => {
    const { selectedBlock, editText, currentPage } = get();
    if (!selectedBlock || editText === selectedBlock.text) return;

    await api.editBlock(selectedBlock.id, editText);

    // Refresh page data and undo state
    const pageData = await api.getPage(currentPage);
    const actions = await api.getActions();
    set((state) => ({
      pageData,
      editCount: state.editCount + 1,
      selectedBlock: pageData.blocks.find((b) => b.id === selectedBlock.id) || null,
      canUndo: actions.undo_available,
      canRedo: actions.redo_available,
      refreshTrigger: state.refreshTrigger + 1,
    }));
  },

  revertEdit: () => {
    const { selectedBlock } = get();
    if (selectedBlock) {
      set({ editText: selectedBlock.text });
    }
  },

  undo: async () => {
    try {
      const result = await api.undo();
      if (result.status === "undone") {
        const actions = await api.getActions();
        // Navigate to the affected page if different from current
        const targetPage = result.page || get().currentPage;
        const pageData = await api.getPage(targetPage);
        set((state) => ({
          currentPage: targetPage,
          pageData,
          editCount: Math.max(0, state.editCount - 1),
          selectedBlock: null,
          editText: "",
          refreshTrigger: state.refreshTrigger + 1,
          canUndo: actions.undo_available,
          canRedo: actions.redo_available,
        }));
      }
    } catch (e) {
      console.error("Undo failed:", e);
    }
  },

  redo: async () => {
    const result = await api.redo();
    if (result.status === "redone") {
      const actions = await api.getActions();
      const targetPage = result.page || get().currentPage;
      const pageData = await api.getPage(targetPage);
      set((state) => ({
        currentPage: targetPage,
        pageData,
        editCount: state.editCount + 1,
        selectedBlock: null,
        editText: "",
        refreshTrigger: state.refreshTrigger + 1,
        canUndo: actions.undo_available,
        canRedo: actions.redo_available,
      }));
    }
  },
}));
