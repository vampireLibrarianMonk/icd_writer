# Phase 5 Requirements: Text Reflow & Page Overflow Management

**Document Version:** 1.0
**Date:** 2026-07-27
**Status:** Draft

---

## Problem Statement

When a user edits text in an ICD (changes "28V" to "28.0 ± 0.5 VDC at 25°C ambient"), the modified text may exceed the original bounding box. The current pipeline uses absolute word-level positioning — every word has a fixed (x, y) coordinate. There is no mechanism to reflow surrounding content when a block grows or shrinks.

Without reflow:
- Longer text overflows its bounding box and overlaps the next element
- Shorter text leaves gaps
- Added paragraphs have nowhere to go
- The exported PDF has visual collisions or truncated content

## Approach: Hybrid Block Reflow + Overflow Indicator (Option C)

ICD editors are precise about page layout. They do NOT want automatic reflow silently rearranging diagrams, tables, and figures on downstream pages. The hybrid approach gives users control:

1. Text reflows **within its block** (word-wrap respecting column width)
2. When a block grows, subsequent blocks on that page **push down**
3. When content would overflow the page boundary, a **visual warning** appears
4. The user decides: manually split content, or trigger a **"reflow from here"** command

This matches how technical document editors actually work — they want to control page breaks, not have software decide for them.

---

## Implementation Steps

### Step 1: Word-Wrap Within Block

**What:** When edited text exceeds the block's horizontal width, wrap to the next line within the same bounding box.

**Details:**
- Each text block has constraints: x0, x1 (left/right margins), font, font_size
- Compute available width: `x1 - x0`
- Word-wrap the edited text using the block's font metrics
- If wrapped text requires more vertical space, expand the block's y1 downward
- Preserve alignment (left-aligned, centered, right-aligned) per original

**Acceptance criteria:**
- Editing a single-line block to multi-line wraps correctly
- Font metrics match the original (using same font family/size)
- Horizontal overflow never occurs

### Step 2: Block Push-Down (Intra-Page Reflow)

**What:** When a block expands vertically, shift all subsequent blocks on that page downward by the overflow amount.

**Details:**
- Blocks are ordered by y-position on each page
- When block N grows by Δy points, blocks N+1, N+2, ... shift down by Δy
- Headers and footers are EXEMPT (they stay at fixed positions)
- Table grid elements move as a unit (the entire table shifts, not individual cells)
- Figures/images shift with their captions

**Acceptance criteria:**
- Expanding a paragraph pushes everything below it down
- Headers/footers remain at page top/bottom
- Tables move as atomic units
- The shift amount equals exactly the block's growth (no cumulative drift)
- Shrinking a block pulls subsequent content up

### Step 3: Page Overflow Detection

**What:** When pushed-down content would exceed the page's printable area (below the footer zone), flag it visually.

**Details:**
- Define page bottom margin (typically `page_height - 72pt` for 1-inch margin)
- After push-down, check if any block's y1 exceeds the bottom margin
- If so, mark the page as "overflowing" with the overflow amount in points
- In the UI: show a red indicator bar at the page bottom: "⚠️ Overflow: 42pt (3 lines)"
- In the API: return `overflow_pt` field in page data response
- Do NOT automatically push content to the next page

**Acceptance criteria:**
- Overflow detected accurately (within 1pt)
- Overflow amount reported to frontend
- Visual indicator shows in document view
- Non-overflowing pages show no indicator
- Export PDF warns user if pages overflow

### Step 4: Manual Reflow Command

**What:** A user-triggered command that reflows content from a given page through subsequent pages, handling cross-page overflow.

**Details:**
- CLI: `python3 -m src.cli reflow <pdf> --from-page N`
- API: `POST /document/reflow?from_page=N`
- UI: Button in the overflow indicator: "Reflow from here"
- Algorithm:
  1. Take all blocks from page N that overflow past the bottom margin
  2. Move them to the top of page N+1 (after the header)
  3. Push existing page N+1 blocks down accordingly
  4. If page N+1 now overflows, repeat for page N+2, etc.
  5. If the last page overflows, create a new page
- Preserve:
  - Headers/footers on each page (regenerated from template)
  - Page numbers (updated)
  - Section headings stay with their content (no orphan headings)
  - Tables don't split mid-row
  - Figures stay with their captions

**Acceptance criteria:**
- Single-page overflow resolves to next page
- Cascading overflow propagates correctly
- New pages created when needed
- Headers/footers regenerated on new pages
- Tables not split across pages (push entire table if it doesn't fit)
- Headings not orphaned (if heading is last item on page, push to next with its content)
- Undo restores pre-reflow state

### Step 5: Content Shrink (Pull-Up)

**What:** When text is shortened or deleted, pull subsequent content upward to fill the gap.

**Details:**
- Same logic as push-down but in reverse
- If a page now has excess space at the bottom AND the next page has content, optionally pull content from the next page
- Pull-up is ONLY triggered by explicit reflow command (not automatic)
- Automatic behavior: only shrink the gap within the current page

**Acceptance criteria:**
- Deleting text closes the gap on the current page
- Cross-page pull-up only on explicit command
- Pulled content respects the same rules (no split tables, no orphan headings)

---

## Constraints & Edge Cases

### Elements That Don't Reflow
- **Page headers/footers** — fixed position, regenerated per page
- **Watermarks/background images** — fixed, untouched
- **Page numbers** — fixed position, but value updated if pages change

### Elements That Move As Units
- **Tables** — entire table moves; never split mid-row
- **Figures with captions** — image + caption move together
- **Bulleted/numbered lists** — move as a group if possible
- **Section heading + first paragraph** — heading never orphaned at page bottom

### Cross-Reference Updates
When reflow changes page numbers:
- TOC entries need updating (page references shift)
- "See page N" references in body text need updating
- This is a separate pass AFTER reflow completes
- Flag changed references for user review

### What Reflow Does NOT Do
- Change font sizes to fit content
- Alter column widths
- Reformat tables to fit page
- Split images or diagrams
- Change section ordering
- Alter margins

---

## Non-Functional Requirements

- **Performance:** Reflow of a single page completes in < 500ms. Full-document reflow (35 pages) in < 5 seconds.
- **Reversibility:** Every reflow operation is undoable (single undo restores entire pre-reflow state).
- **Accuracy:** Pushed blocks land at exact calculated positions (no cumulative floating-point drift).
- **Preview:** Before applying reflow, show a preview of affected pages (how many pages shift, any new pages created).

---

## Out of Scope (Phase 5)

- Multi-column reflow (ICDs are single-column)
- Automatic hyphenation
- Widow/orphan control (single-line paragraph at page top/bottom)
- Style reflow (changing fonts/sizes to fit)
- Collaborative concurrent editing
- Real-time streaming reflow (reflow runs on explicit trigger only)

---

## Dependencies

| Dependency | Risk | Mitigation |
|-----------|------|-----------|
| Font metrics accuracy | Wrong metrics = wrong wrap positions | Use same font measurement as rendering (WeasyPrint or PyMuPDF metrics) |
| Block ordering | Incorrect y-sort = wrong push order | Validate block order matches visual order on every page |
| Table detection | Must know which blocks form a table | Existing table zone detection provides this |
| Header/footer identification | Must exclude from reflow | Existing page_analysis identifies these |

---

## Implementation Priority

| Step | Effort | Value | Order |
|------|--------|-------|-------|
| Step 1: Word-wrap within block | 1 day | High — prevents overflow for small edits | 1st |
| Step 2: Block push-down | 1 day | High — keeps page layout coherent | 2nd |
| Step 3: Overflow detection | 0.5 day | Medium — user visibility into problems | 3rd |
| Step 4: Manual reflow command | 3-4 days | Medium — handles large edits | 4th |
| Step 5: Content shrink/pull-up | 1-2 days | Low — nice-to-have | 5th |

**Total estimated effort:** 7-9 days

---

## Future Enhancement: Auto-Reflow Mode

For users who prefer Word-like behavior, a future toggle could enable:
- Automatic cross-page reflow on every edit
- Real-time page count updates
- Continuous TOC/reference updating

This would build on Steps 1-5 but run automatically instead of on-demand. Deferred to Phase 6+.
