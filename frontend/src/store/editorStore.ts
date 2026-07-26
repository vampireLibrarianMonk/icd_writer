import { create } from "zustand";
import { api, TextBlock, PageData } from "../api/client";

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

  // Session
  sessionId: string | null;
  editCount: number;

  // Actions
  loadDocument: (path: string) => Promise<void>;
  goToPage: (page: number) => Promise<void>;
  selectBlock: (block: TextBlock | null) => void;
  setEditText: (text: string) => void;
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
  sessionId: null,
  editCount: 0,

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

  applyEdit: async () => {
    const { selectedBlock, editText, currentPage } = get();
    if (!selectedBlock || editText === selectedBlock.text) return;

    await api.editBlock(selectedBlock.id, editText);

    // Refresh page data
    const pageData = await api.getPage(currentPage);
    set((state) => ({
      pageData,
      editCount: state.editCount + 1,
      selectedBlock: pageData.blocks.find((b) => b.id === selectedBlock.id) || null,
    }));
  },

  revertEdit: () => {
    const { selectedBlock } = get();
    if (selectedBlock) {
      set({ editText: selectedBlock.text });
    }
  },

  undo: async () => {
    await api.undo();
    const { currentPage } = get();
    const pageData = await api.getPage(currentPage);
    set((state) => ({
      pageData,
      editCount: Math.max(0, state.editCount - 1),
      selectedBlock: null,
      editText: "",
    }));
  },

  redo: async () => {
    await api.redo();
    const { currentPage } = get();
    const pageData = await api.getPage(currentPage);
    set((state) => ({
      pageData,
      editCount: state.editCount + 1,
      selectedBlock: null,
      editText: "",
    }));
  },
}));
