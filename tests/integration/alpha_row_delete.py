"""Alpha loop: delete a row from table 1 on page 7 of HSI_SYS_015G.pdf
and verify that text below shifts correctly (1:1 content match, just moved up).

Steps:
1. Open the document, capture all text spans below table 1 BEFORE edit
2. Delete one row from table 1
3. Capture all text spans below the new table bottom AFTER edit
4. Compare: every original span should exist at (same x, same text, y - delta)
"""
import json
import fitz
import shutil
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"
PDF_PATH = "icds/digital/HSI_SYS_015G.pdf"
# Make a working copy so we don't mutate the original
WORK_COPY = "output/.test_row_delete.pdf"

shutil.copy2(PDF_PATH, WORK_COPY)


def api_post(path, params=None, body=None):
    url = f"{API}{path}"
    if params:
        url += "?" + urlencode(params)
    if body:
        data = json.dumps(body).encode()
        req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    else:
        req = Request(url, method="POST")
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())


def api_get(path, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url)
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())


def get_spans_below(pdf_path, page_num, y_threshold):
    """Extract all text spans below y_threshold on a page."""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    page_height = page.rect.height
    spans = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span["bbox"]
                if bbox[1] > y_threshold and bbox[1] < page_height - 55:
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars)
                    if text.strip():
                        spans.append({
                            "text": text,
                            "x0": round(bbox[0], 1),
                            "y0": round(bbox[1], 1),
                            "x1": round(bbox[2], 1),
                            "y1": round(bbox[3], 1),
                            "font": span.get("font", ""),
                            "size": span.get("size", 0),
                        })
    doc.close()
    return spans


def get_drawings_below(pdf_path, page_num, y_threshold):
    """Extract drawings below y_threshold."""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    drawings = page.get_drawings()
    below = []
    for d in drawings:
        rect = d.get("rect")
        if rect and fitz.Rect(rect).y0 > y_threshold:
            below.append({
                "y0": round(fitz.Rect(rect).y0, 1),
                "y1": round(fitz.Rect(rect).y1, 1),
                "x0": round(fitz.Rect(rect).x0, 1),
                "x1": round(fitz.Rect(rect).x1, 1),
                "w": round(fitz.Rect(rect).width, 1),
                "h": round(fitz.Rect(rect).height, 1),
            })
    doc.close()
    return below


# ─── Step 1: Capture BEFORE state ─────────────────────────────

# Open document via API
result = api_post("/document/open", {"pdf_path": PDF_PATH})
print(f"Opened: {result['pages']} pages")

# Get table zone
zones = api_get("/document/page/7/table-zones")
zone = zones["zones"][0]
print(f"Table 1 zone: y_min={zone['y_min']}, y_max={zone['y_max']}")

# Get table data
table = api_get("/document/page/7/table-cells", {"y_min": zone["y_min"], "y_max": zone["y_max"]})
print(f"Table: {table['rows']} rows x {table['columns']} cols")

# Get spans below table BEFORE
spans_before = get_spans_below(PDF_PATH, 7, zone["y_max"])
drawings_before = get_drawings_below(PDF_PATH, 7, zone["y_max"])
print(f"\nBEFORE: {len(spans_before)} text spans below table, {len(drawings_before)} drawings")
print("First 5 spans:")
for s in spans_before[:5]:
    print(f"  x0={s['x0']:5.1f} y0={s['y0']:5.1f} | '{s['text'][:50]}'")

# ─── Step 2: Delete last row ──────────────────────────────────

# Build data from cells (grouped by row)
cells = table.get("cells", [])
num_rows = table["rows"]
num_cols = table["columns"]
data = [[""] * num_cols for _ in range(num_rows)]
for cell in cells:
    r, c = cell["row"], cell["col"]
    if r < num_rows and c < num_cols:
        data[r][c] = cell["text"]

print(f"\nTable data ({num_rows} rows):")
for i, row in enumerate(data):
    print(f"  Row {i}: {row}")

print(f"\nDeleting last row (row {num_rows-1})")
data = data[:-1]

rebuild_result = api_post("/document/page/7/table-rebuild", body={
    "y_min": zone["y_min"],
    "y_max": zone["y_max"],
    "data": data,
})
print(f"Rebuild: {rebuild_result}")
height_delta = rebuild_result["height_delta"]
print(f"Height delta: {height_delta} (negative = table shrunk)")

# ─── Step 3: Capture AFTER state ──────────────────────────────

# The working copy is what the API modified
# Find it — it should be at the source path used by the API
# Since we opened from PDF_PATH, the working copy is at output/.working_HSI_SYS_015G.pdf or similar
# Let's just re-read from the API's source
import glob
working_files = glob.glob("output/.working_*015G*")
if not working_files:
    working_files = glob.glob("icds/digital/HSI_SYS_015G.pdf")
work_path = working_files[0] if working_files else PDF_PATH
print(f"\nReading modified PDF from: {work_path}")

# New table bottom (original was zone['y_max'], now it's smaller by |height_delta|)
new_table_bottom = zone["y_max"] + height_delta  # height_delta is negative
spans_after = get_spans_below(work_path, 7, new_table_bottom)
drawings_after = get_drawings_below(work_path, 7, new_table_bottom)
print(f"AFTER: {len(spans_after)} text spans below table, {len(drawings_after)} drawings")
print("First 5 spans:")
for s in spans_after[:5]:
    print(f"  x0={s['x0']:5.1f} y0={s['y0']:5.1f} | '{s['text'][:50]}'")

# ─── Step 4: Compare ─────────────────────────────────────────

print(f"\n{'='*60}")
print("COMPARISON")
print(f"{'='*60}")
print(f"Expected shift: {height_delta:.1f}pt (every span should move by this amount)")
print()

# Match spans by text content and X position
matched = 0
mismatched = 0
missing = 0

for before_span in spans_before:
    # Find matching span in after (same text, same x0)
    match = None
    for after_span in spans_after:
        if (after_span["text"] == before_span["text"] and
                abs(after_span["x0"] - before_span["x0"]) < 2):
            match = after_span
            break

    if match is None:
        missing += 1
        if missing <= 5:
            print(f"  MISSING: x0={before_span['x0']:.1f} y0={before_span['y0']:.1f} | '{before_span['text'][:40]}'")
    else:
        actual_shift = match["y0"] - before_span["y0"]
        if abs(actual_shift - height_delta) < 2.0:
            matched += 1
        else:
            mismatched += 1
            if mismatched <= 5:
                print(f"  WRONG SHIFT: expected {height_delta:.1f}, got {actual_shift:.1f} "
                      f"| '{before_span['text'][:30]}' (y: {before_span['y0']:.1f} -> {match['y0']:.1f})")

print(f"\nResults: {matched} correct, {mismatched} wrong shift, {missing} missing")
print(f"Total spans before: {len(spans_before)}, after: {len(spans_after)}")

if missing == 0 and mismatched == 0:
    print("\nPASS: All text shifted correctly (1:1 match)")
elif missing > 0:
    print(f"\nFAIL: {missing} spans disappeared after shift")
elif mismatched > 0:
    print(f"\nFAIL: {mismatched} spans shifted by wrong amount")

# Clean up
Path(WORK_COPY).unlink(missing_ok=True)
