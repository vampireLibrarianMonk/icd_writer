# UI Design: ICD Editor

## Design Philosophy

This editor should feel like what people already know — a document viewer on the left, an edit panel on the right, and a toolbar at the top. No novel interactions. If it works in Word, Google Docs, or Adobe Acrobat, it works here.

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│  File   Edit   View   Tools   Help                           │
├──────────────────────────────────────────────────────────────┤
│ [Open] [Save] [Export PDF] │ [Undo] [Redo] │ [Find] │ Pg 3/15│
├─────────────────────────────┬────────────────────────────────┤
│                             │                                │
│                             │  EDIT PANEL                    │
│   DOCUMENT VIEW             │                                │
│                             │  Selected block:               │
│   ┌───────────────────┐    │  ┌──────────────────────────┐  │
│   │                   │    │  │ The system shall accept   │  │
│   │  (rendered page)  │    │  │ command frames at a rate  │  │
│   │                   │    │  │ of 1 Hz.                  │  │
│   │  Click any text   │    │  └──────────────────────────┘  │
│   │  to select it     │    │                                │
│   │                   │    │  Font: Liberation Serif 11pt   │
│   │                   │    │  Page: 7  Block: block-p07-b12 │
│   │                   │    │  Confidence: 99.2%             │
│   │                   │    │                                │
│   │                   │    │  [Apply] [Revert]              │
│   └───────────────────┘    │                                │
│                             │  ─────────────────────────     │
│  [◀] [▶]  Zoom: [−][+]     │  CHANGE LOG                   │
│                             │  (empty — no edits yet)        │
│                             │                                │
├─────────────────────────────┴────────────────────────────────┤
│  Status: Ready │ Document: HSI_SYS_015G.pdf │ 8 pages        │
└──────────────────────────────────────────────────────────────┘
```

## Core Interactions

### Opening a Document

1. User clicks **Open** or drags a PDF onto the window
2. System detects if PDF is digital (native text) or scanned (image-only)
3. Appropriate pipeline runs:
   - Digital: native extraction (instant, free)
   - Scanned: OCR pipeline (takes ~30s for 15 pages, costs ~$0.06)
4. Progress bar shows extraction status
5. Document appears in the viewer once complete

### Viewing

- Left panel shows the rendered page (PDF.js or image)
- Page navigation: arrow buttons, page number input, scroll
- Zoom: +/− buttons, fit-to-width, fit-to-page
- Text blocks have invisible hover outlines (light blue border on mouseover)
- Clicking a block selects it (highlighted) and opens it in the edit panel

### Selecting Text

- **Single click** on a text block → selects the entire block
- **Double click** on a word → selects just that word within the block
- Selected block is highlighted with a light blue overlay on the page
- Edit panel shows the block's content and metadata

### Editing

The edit panel is a plain text area. No rich text formatting — the font/style comes from the document's existing formatting.

- Type to change text
- **Apply** button saves the change to the IR and re-renders the affected page
- **Revert** button discards the edit
- **Undo/Redo** work across edits (Ctrl+Z, Ctrl+Y)
- Changed blocks get a yellow dot indicator in the page view

### Finding Text

- **Ctrl+F** opens a find bar at the top of the document view
- Type to search — highlights all matches on all pages
- Up/down arrows to navigate between matches
- Optional: filter by page range, block type, or confidence level

### Saving and Exporting

- **Save** writes the current IR state (YAML) to disk
- **Export PDF** regenerates the full PDF from the current IR
- For digital PDFs: HTML/CSS → WeasyPrint rendering
- For scanned PDFs: original image + patched text regions
- User chooses output location

## What the Edit Panel Shows

When a text block is selected:

| Field | Description |
|-------|-------------|
| **Text** | Editable text content (plain textarea) |
| **Page** | Which page this block is on |
| **Position** | Bounding box coordinates (read-only) |
| **Font** | Detected or original font name and size |
| **Type** | paragraph, heading, caption, header, footer |
| **Confidence** | OCR confidence (for scanned docs) — hidden for digital |
| **Source** | "native" or "ocr (textract)" |

## Toolbar Actions

| Button | Shortcut | Action |
|--------|----------|--------|
| Open | Ctrl+O | Open a PDF file |
| Save | Ctrl+S | Save IR to disk |
| Export PDF | Ctrl+E | Generate output PDF |
| Undo | Ctrl+Z | Undo last edit |
| Redo | Ctrl+Y | Redo undone edit |
| Find | Ctrl+F | Open search bar |

## Page View Overlays

Visual indicators on the document view:

| Indicator | Meaning |
|-----------|---------|
| Light blue border (hover) | Hovering over a selectable block |
| Blue filled highlight | Currently selected block |
| Yellow dot (top-left of block) | Block has been edited |
| Red dot (top-left of block) | Low OCR confidence — review suggested |
| Green dot (top-left of block) | Human-verified after OCR |

## Change Log Panel

Below the edit panel, a scrollable list of all edits made in this session:

```
 #3  Page 7, block-p07-b12
     "1 Hz" → "2 Hz"
     2026-07-26 13:24

 #2  Page 4, block-p04-b03
     "Rev B" → "Rev C"
     2026-07-26 13:22

 #1  Page 1, block-p01-b04
     "February 26, 2015" → "August 1, 2026"
     2026-07-26 13:20
```

Each entry shows: page, block ID, before/after text (truncated), and timestamp. Clicking an entry navigates to that block.

## Review Mode (Scanned Documents)

For OCR-ingested documents, an additional "Review" button appears in the toolbar. This opens a mode where:

1. Blocks with confidence < 80% are highlighted in orange
2. Blocks with confidence < 60% are highlighted in red
3. User clicks each flagged block, verifies the text, clicks "Confirm" or edits
4. Confirmed blocks turn green
5. Progress indicator: "14/18 blocks reviewed"

## Error States

| Situation | UI Response |
|-----------|-------------|
| OCR fails on a page | Show error banner, skip page, continue |
| PDF can't be opened | Error dialog with message |
| Export fails | Error dialog, suggest checking fonts |
| Network error (OCR) | Retry button, option to skip cloud models |
| Unsaved changes on close | "Save changes?" dialog |

## Technology Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Framework | React + TypeScript | Industry standard, component-based |
| PDF viewing | PDF.js | Mozilla's viewer, handles any PDF |
| Text editor | `<textarea>` | Simple, no rich formatting needed |
| State management | React Context or Zustand | Lightweight, no Redux overhead |
| Backend communication | REST (fetch) | Simple, well-understood |
| Styling | Tailwind CSS | Fast to build, no custom CSS needed |

## What This Is NOT

- Not a full word processor (no formatting toolbar, no font picker)
- Not a collaborative editor (single user, no real-time sync in MVP)
- Not a design tool (no drawing, no drag-to-position)
- Not a replacement for Word (can't create documents from scratch)

It is: a focused viewer+editor for existing ICD documents, where you load a PDF, fix or update specific text, and export a new PDF.

## File Operations

| Operation | What Happens |
|-----------|--------------|
| **Open digital PDF** | Runs native extraction → IR → displays immediately |
| **Open scanned PDF** | Runs OCR pipeline → IR → displays (with cost notification) |
| **Save** | Writes `document_ir.yaml` to the output directory |
| **Export PDF (digital)** | IR → HTML/CSS → WeasyPrint → PDF |
| **Export PDF (scanned)** | Original images + patched edited regions → PDF |
| **Close** | Prompts to save if unsaved changes |

## MVP Scope

Build first:
1. Open PDF (digital path only — no OCR in v1 UI)
2. View pages with page navigation
3. Click to select blocks
4. Edit text in the panel
5. Apply and see re-rendered page
6. Export PDF

Add later:
- OCR ingestion from UI
- Review mode for flagged blocks
- Find/replace
- Change log persistence
- Multi-document tabs
