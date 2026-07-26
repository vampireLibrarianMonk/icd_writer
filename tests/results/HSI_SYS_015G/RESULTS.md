# Visual Fidelity Results: HSI_SYS_015G.pdf (HESSI Spectrometer ICD)

**Pipeline:** Fully automated (no manual adjustments)
**Comparison DPI:** 150
**Pixel Match Threshold:** 30 (per-channel difference)

## Summary

| Metric | Value |
|--------|-------|
| Pages | 8 |
| Average Pixel Match | 94.3% |
| Average F1 Score | 69.6% |
| Best Page (Pixel) | 8 (98.6%) |
| Worst Page (Pixel) | 6 (91.3%) |

## Per-Page Results

| Page | Pixel Match | Recall | Precision | F1 |
|------|-------------|--------|-----------|----|
| 1 | 95.8% | 76.1% | 65.3% | 70.3% |
| 2 | 96.4% | 80.8% | 81.3% | 81.1% |
| 3 | 95.1% | 61.2% | 59.7% | 60.4% |
| 4 | 91.8% | 67.0% | 67.2% | 67.1% |
| 5 | 91.8% | 65.6% | 65.7% | 65.7% |
| 6 | 91.3% | 68.0% | 68.3% | 68.2% |
| 7 | 93.2% | 78.2% | 79.5% | 78.9% |
| 8 | 98.6% | 64.1% | 65.8% | 64.9% |

## Methodology

- Original PDF rendered to PNG at 150 DPI via PyMuPDF
- Regenerated PDF rendered to PNG at 150 DPI via PyMuPDF
- Pixel Match: percentage of pixels with per-channel difference < 30
- Recall: content pixels in original that appear in regenerated
- Precision: content pixels in regenerated that appear in original
- F1: harmonic mean of recall and precision
- Content pixels: any pixel where min(R,G,B) < 240
