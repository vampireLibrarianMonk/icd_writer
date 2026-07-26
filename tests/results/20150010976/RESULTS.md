# Visual Fidelity Results: 20150010976.pdf (NASA LVC ICD)

## What This Test Does

This test takes the original NASA "Live Virtual Constructive (LVC) Interface Control Document" PDF (35 pages) and runs it through the ICD Writer pipeline:

1. **Extract** — Read every text character, image, line, and shape from the original PDF along with their exact positions
2. **Represent** — Store everything in a structured intermediate format (YAML) that humans can read and edit
3. **Regenerate** — Produce a new PDF from that intermediate format

We then compare the regenerated PDF against the original, page by page, to measure how faithfully the pipeline reproduces the document.

## How to Read the Scores

| Term | What It Means |
|------|---------------|
| **Pixel Match** | Percentage of all pixels on the page that are the same (within tolerance) between original and regenerated. Higher = more visually identical. A score of 95% means 95 out of every 100 pixels match. |
| **Recall** | Of the "ink" pixels in the original (text, lines, images), what percentage appear in the regenerated version? Low recall means content is missing. |
| **Precision** | Of the "ink" pixels in the regenerated version, what percentage actually exist in the original? Low precision means extra/spurious content is appearing. |
| **F1 Score** | The balanced average of Recall and Precision. Gives a single number for how well the content (not white space) matches. |

### What Do These Numbers Mean in Practice?

- **98-100% pixel match**: Virtually indistinguishable from the original at normal viewing
- **94-97% pixel match**: Looks correct to the eye; differences only visible at zoom with side-by-side comparison
- **88-93% pixel match**: Structurally correct; differences are in text character rendering (slightly different font shapes)

### Why Isn't It 100%?

The pipeline uses **substitute fonts** (e.g., Liberation Serif instead of Times New Roman). These fonts have the same character widths but slightly different shapes at the subpixel level. Every character's antialiased edge differs by 1-2 pixels. On a page with 2,000 characters, those tiny edge differences add up in the statistics while remaining invisible to the human eye.

---

## Summary

| Metric | Value |
|--------|-------|
| Document | NASA LVC ICD (Interface Control Document for the LVC Gateway, Flight Test 3) |
| Pages | 35 |
| Pipeline | Fully automated — no manual adjustments, no per-page tuning |
| Average Pixel Match | **94.4%** |
| Average F1 Score | **73.8%** |
| Best Page | Page 3 — 100.0% (full-page image, pixel-perfect reproduction) |
| Worst Page | Page 27 — 88.0% (densest body text page) |

## Per-Page Results

| Page | Pixel Match | F1 | Page Content |
|------|-------------|----|--------------|
| 1 | 98.2% | 88.7% | Cover page (NASA logo + title) |
| 2 | 98.4% | 87.6% | Title and author information |
| 3 | 100.0% | 100.0% | Full-page image (pixel-perfect) |
| 4 | 99.1% | 84.7% | Revision history table |
| 5 | 92.1% | 78.9% | System architecture diagram |
| 6 | 95.0% | 92.9% | High-level architecture diagram + references |
| 7 | 94.7% | 75.1% | Message type definition table |
| 8 | 95.2% | 73.7% | Client names table |
| 9 | 95.4% | 69.9% | Code/data structure definitions |
| 10 | 89.1% | 68.7% | Dense body text (paragraphs) |
| 11 | 93.6% | 68.0% | Data structure definitions |
| 12 | 92.3% | 68.3% | Message format specifications |
| 13 | 93.1% | 67.6% | Aircraft flight state data |
| 14 | 93.2% | 68.2% | Flight plan definitions |
| 15 | 93.4% | 69.7% | Data type definitions |
| 16 | 92.4% | 68.9% | Data type descriptions |
| 17 | 92.1% | 69.1% | Sense and Avoid section |
| 18 | 94.1% | 66.8% | Conflict data structures |
| 19 | 95.0% | 71.2% | Table 3 — message definitions |
| 20 | 94.1% | 67.7% | Engineering data structures |
| 21 | 94.2% | 69.6% | Latitude/longitude structures |
| 22 | 92.9% | 69.0% | Trial planning functions |
| 23 | 92.2% | 68.9% | Release message definitions |
| 24 | 92.5% | 66.8% | Boolean data structures |
| 25 | 91.7% | 69.1% | Alert level descriptions |
| 26 | 91.3% | 69.3% | OmniBand interval data |
| 27 | 88.0% | 67.5% | Advanced mode text (densest page) |
| 28 | 90.6% | 70.1% | Alert descriptions |
| 29 | 97.3% | 72.2% | Byte size definitions (lighter content) |
| 30 | 96.4% | 68.2% | Acronym list |
| 31 | 96.9% | 71.7% | Appendix A — ARINC characteristics |
| 32 | 98.1% | 72.9% | Clear of Conflict definitions |
| 33 | 95.2% | 72.4% | Binary data tables |
| 34 | 95.7% | 91.5% | Appendix B (image + text) |
| 35 | 99.7% | 78.4% | "This page intentionally left blank" |

## Score Patterns

| Page Type | Typical Pixel Match | Typical F1 | Why |
|-----------|--------------------:|----------:|-----|
| Image-only pages | 99-100% | 100% | Images are extracted and placed exactly — no font rendering involved |
| Cover/title pages | 97-99% | 85-89% | Large bold text with few characters — less antialiasing disagreement |
| Table pages | 94-99% | 72-85% | Grid lines render precisely; table text has some font differences |
| Diagram pages | 91-95% | 78-93% | Vector shapes render well; small embedded images have interpolation differences |
| Dense text pages | 88-95% | 67-70% | Hundreds of characters per page, each with 1-2 pixel edge differences from font substitution |

---

## Methodology

- Original PDF rendered to PNG at 150 DPI using PyMuPDF
- Regenerated PDF rendered to PNG at 150 DPI using PyMuPDF
- **Pixel Match**: percentage of all page pixels where the per-channel RGB difference is less than 30 (out of 255)
- **Recall**: percentage of non-white pixels in the original that are also non-white in the regenerated version
- **Precision**: percentage of non-white pixels in the regenerated version that are also non-white in the original
- **F1 Score**: harmonic mean of Recall and Precision — `2 × (Recall × Precision) / (Recall + Precision)`
- **Non-white pixel**: any pixel where the minimum of R, G, B is less than 240 (i.e., has "ink")
