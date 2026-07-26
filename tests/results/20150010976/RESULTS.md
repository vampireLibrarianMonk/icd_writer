# Visual Fidelity Results: 20150010976.pdf (NASA LVC ICD)

**Pipeline:** Fully automated (no manual adjustments)
**Comparison DPI:** 150
**Pixel Match Threshold:** 30 (per-channel difference)

## Summary

| Metric | Value |
|--------|-------|
| Pages | 35 |
| Average Pixel Match | 94.4% |
| Average F1 Score | 73.8% |
| Best Page (Pixel) | 3 (100.0%) |
| Worst Page (Pixel) | 27 (88.0%) |

## Per-Page Results

| Page | Pixel Match | Recall | Precision | F1 |
|------|-------------|--------|-----------|----|
| 1 | 98.2% | 86.5% | 90.9% | 88.7% |
| 2 | 98.4% | 87.8% | 87.4% | 87.6% |
| 3 | 100.0% | 100.0% | 100.0% | 100.0% |
| 4 | 99.1% | 85.2% | 84.3% | 84.7% |
| 5 | 92.1% | 75.4% | 82.7% | 78.9% |
| 6 | 95.0% | 92.0% | 93.8% | 92.9% |
| 7 | 94.7% | 75.2% | 74.9% | 75.1% |
| 8 | 95.2% | 73.7% | 73.7% | 73.7% |
| 9 | 95.4% | 70.2% | 69.5% | 69.9% |
| 10 | 89.1% | 68.8% | 68.7% | 68.7% |
| 11 | 93.6% | 68.2% | 67.8% | 68.0% |
| 12 | 92.3% | 67.4% | 69.3% | 68.3% |
| 13 | 93.1% | 67.1% | 68.1% | 67.6% |
| 14 | 93.2% | 68.0% | 68.5% | 68.2% |
| 15 | 93.4% | 69.1% | 70.3% | 69.7% |
| 16 | 92.4% | 69.0% | 68.8% | 68.9% |
| 17 | 92.1% | 69.3% | 68.9% | 69.1% |
| 18 | 94.1% | 66.7% | 66.9% | 66.8% |
| 19 | 95.0% | 71.2% | 71.2% | 71.2% |
| 20 | 94.1% | 67.0% | 68.3% | 67.7% |
| 21 | 94.2% | 69.5% | 69.7% | 69.6% |
| 22 | 92.9% | 69.0% | 69.0% | 69.0% |
| 23 | 92.2% | 68.8% | 69.1% | 68.9% |
| 24 | 92.5% | 66.2% | 67.5% | 66.8% |
| 25 | 91.7% | 69.2% | 69.0% | 69.1% |
| 26 | 91.3% | 69.3% | 69.3% | 69.3% |
| 27 | 88.0% | 67.6% | 67.4% | 67.5% |
| 28 | 90.6% | 70.3% | 69.9% | 70.1% |
| 29 | 97.3% | 72.8% | 71.5% | 72.2% |
| 30 | 96.4% | 68.1% | 68.3% | 68.2% |
| 31 | 96.9% | 72.2% | 71.2% | 71.7% |
| 32 | 98.1% | 73.2% | 72.5% | 72.9% |
| 33 | 95.2% | 72.5% | 72.3% | 72.4% |
| 34 | 95.7% | 92.7% | 90.4% | 91.5% |
| 35 | 99.7% | 76.6% | 80.2% | 78.4% |

## Methodology

- Original PDF rendered to PNG at 150 DPI via PyMuPDF
- Regenerated PDF rendered to PNG at 150 DPI via PyMuPDF
- Pixel Match: percentage of pixels with per-channel difference < 30
- Recall: content pixels in original that appear in regenerated
- Precision: content pixels in regenerated that appear in original
- F1: harmonic mean of recall and precision
- Content pixels: any pixel where min(R,G,B) < 240
