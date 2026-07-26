# Text Accuracy Report: HSI_SYS_015G.pdf

Comparing text content between original and regenerated PDF.
Pages compared: 8

## Per-Page Results

| Page | Status | Words Orig | Missing | Extra | Notes |
|------|--------|-----------|---------|-------|-------|
| 1 | ✓ Exact | 34 | 0 | 0 |  |
| 2 | ✗ Differs | 98 | 2 | 1 | Missing: ['Preliminary', 'Draft'] Extra: ['PreliminaryDraft'] |
| 3 | ✗ Differs | 89 | 8 | 6 | Missing: ['Bus...................................5', 'Documents', 'Responsibilities'] Extra: ['5', 'ThermalDesign', 'Documents.........................................................................................1'] |
| 4 | ✗ Differs | 197 | 3 | 3 | Missing: ['Berkeley)', '(University', 'typically'] Extra: ['(Universityof', 'Berkeley)and', 'typicallyfollowed'] |
| 5 | ✗ Differs | 210 | 2 | 1 | Missing: ['maximum', '(with'] Extra: ['maximum(with'] |
| 6 | ✓ Exact | 193 | 0 | 0 |  |
| 7 | ✓ Exact | 159 | 0 | 0 |  |
| 8 | ✓ Exact | 42 | 0 | 0 |  |

## Summary

| Metric | Value |
|--------|-------|
| Pages with exact text match | 4/8 |
| Word retention | 98.5% |
| Total unique words in original | 1,022 |
| Total missing words | 15 |
| Total extra words | 11 |

## Detailed Differences

Below are the specific text differences found. These help identify what content may need attention.

### Page 2

**Missing words** (2):

- `Draft`
- `Preliminary`

**Extra words** (1):

- `PreliminaryDraft`

### Page 3

**Missing words** (8):

- `................................................................................................2`
- `.........................................................................................1`
- `...................................................................3`
- `Bus...................................5`
- `Design`
- `Documents`
- `Drawing`
- `Responsibilities`

**Extra words** (6):

- `5`
- `Bus...................................`
- `Documents.........................................................................................1`
- `Drawing................................................................................................2`
- `Responsibilities...................................................................3`
- `ThermalDesign`

### Page 4

**Missing words** (3):

- `(University`
- `Berkeley)`
- `typically`

**Extra words** (3):

- `(Universityof`
- `Berkeley)and`
- `typicallyfollowed`

### Page 5

**Missing words** (2):

- `(with`
- `maximum`

**Extra words** (1):

- `maximum(with`

---

## How to Read This Report

- **✓ Exact**: The text on this page is character-for-character identical
- **~ Whitespace**: All words are present but spacing differs (e.g., double space → single space)
- **✗ Differs**: Some words are missing or extra (may be from z-order hiding or image-embedded text)
- **Missing words**: Words in the original PDF that don't appear in the regenerated version
- **Extra words**: Words in the regenerated version that don't appear in the original