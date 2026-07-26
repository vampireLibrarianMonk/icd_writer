# Visual Fidelity Results: HSI_SYS_015G.pdf (HESSI Spectrometer ICD)

## What This Test Does

This test takes the original NASA "High Energy Spectroscopic Imager (HESSI) Spacecraft to Spectrometer Interface Control Document" PDF (8 pages, created 1999) and runs it through the ICD Writer pipeline:

1. **Extract** — Read every text character, image, line, and shape from the original PDF along with their exact positions
2. **Represent** — Store everything in a structured intermediate format (YAML) that humans can read and edit
3. **Regenerate** — Produce a new PDF from that intermediate format

We then compare the regenerated PDF against the original, page by page, to measure how faithfully the pipeline reproduces the document.

## How to Read the Scores

| Term | What It Means |
|------|---------------|
| **Pixel Match** | Percentage of all pixels on the page that are the same (within tolerance) between original and regenerated. Higher = more visually identical. |
| **Recall** | Of the "ink" pixels in the original (text, lines, images), what percentage appear in the regenerated version? Low recall means content is missing. |
| **Precision** | Of the "ink" pixels in the regenerated version, what percentage actually exist in the original? Low precision means extra/spurious content is appearing. |
| **F1 Score** | The balanced average of Recall and Precision. Gives a single number for how well the content (not white space) matches. |

### Why Isn't It 100%?

This document was created in 1999 using Times New Roman. The pipeline uses Liberation Serif (a metric-compatible substitute) which has the same character widths but slightly different glyph shapes. Each character's edge pixels differ by 1-2 pixels, which accumulates across pages of dense text.

---

## Summary

| Metric | Value |
|--------|-------|
| Document | HESSI Spacecraft to Spectrometer ICD (Version G, 1999) |
| Author | Dave Curtis |
| Pages | 8 |
| Pipeline | Fully automated — no manual adjustments |
| Average Pixel Match | **94.3%** |
| Average F1 Score | **69.6%** |
| Best Page | Page 8 — 98.6% pixel match |
| Worst Page | Page 6 — 91.3% pixel match |

## Per-Page Results

| Page | Pixel Match | F1 | Page Content |
|------|-------------|----|--------------|
| 1 | 95.8% | 70.3% | Cover page (title, version, signatories) |
| 2 | 96.4% | 81.1% | Table of contents |
| 3 | 95.1% | 60.4% | Dense text with specifications |
| 4 | 91.8% | 67.1% | Interface specifications |
| 5 | 91.8% | 65.7% | Technical requirements |
| 6 | 91.3% | 68.2% | Detailed specifications |
| 7 | 93.2% | 78.9% | Tables and references |
| 8 | 98.6% | 64.9% | Final page (lighter content) |

---

## Methodology

- Original PDF rendered to PNG at 150 DPI using PyMuPDF
- Regenerated PDF rendered to PNG at 150 DPI using PyMuPDF
- **Pixel Match**: percentage of all page pixels where the per-channel RGB difference is less than 30 (out of 255)
- **Recall**: percentage of non-white pixels in the original that are also non-white in the regenerated version
- **Precision**: percentage of non-white pixels in the regenerated version that are also non-white in the original
- **F1 Score**: harmonic mean of Recall and Precision — `2 × (Recall × Precision) / (Recall + Precision)`
- **Non-white pixel**: any pixel where the minimum of R, G, B is less than 240 (i.e., has "ink")
