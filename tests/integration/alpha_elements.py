"""Alpha loop: inspect all elements on every page of 20130010957.pdf.

For each page, shows every element with its id, type, text, and bbox.
This is exactly what the frontend receives and uses for the dropdown/editor.
"""
import json
import fitz
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"

# Open
params = urlencode({"pdf_path": "icds/digital/20130010957.pdf"})
req = Request(f"{API}/document/open?{params}", method="POST")
resp = urlopen(req)
info = json.loads(resp.read())
print(f"Opened: {info['pages']} pages, {info['text_blocks']} blocks")
print()

# Also check what PyMuPDF sees directly on page 1 for comparison
doc = fitz.open("icds/digital/20130010957.pdf")
page = doc[0]
print("RAW PyMuPDF page 1 blocks:")
blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
for i, block in enumerate(blocks):
    if block.get("type") != 0:
        continue
    lines_text = []
    for line in block.get("lines", []):
        line_text = ""
        max_size = 0
        for span in line.get("spans", []):
            line_text += span.get("text", "")
            max_size = max(max_size, span.get("size", 0))
        lines_text.append((line_text.strip(), max_size))
    if lines_text:
        bbox = block["bbox"]
        full_text = " ".join(t for t, _ in lines_text if t)[:80]
        sizes = set(s for _, s in lines_text if s > 0)
        print(f"  Block {i}: bbox=({bbox[0]:.0f},{bbox[1]:.0f},{bbox[2]:.0f},{bbox[3]:.0f}) sizes={sizes}")
        print(f"    text: {full_text}")
doc.close()
print()

# Now check the API elements for all pages
for page_num in range(1, info["pages"] + 1):
    try:
        req = Request(f"{API}/document/page/{page_num}/elements")
        resp = urlopen(req)
        data = json.loads(resp.read())
        elements = data.get("elements", [])
    except Exception as e:
        print(f"Page {page_num}: ERROR {e}")
        continue

    print(f"{'='*70}")
    print(f"PAGE {page_num}: {len(elements)} elements")
    print(f"{'='*70}")
    for i, e in enumerate(elements):
        eid = e.get("id", "???")
        etype = e.get("type", "???")
        text = e.get("text", "")[:60].replace("\n", "\\n")
        bbox = e.get("bbox", {})
        x0 = bbox.get("x0", 0)
        y0 = bbox.get("y0", 0)
        x1 = bbox.get("x1", 0)
        y1 = bbox.get("y1", 0)
        h = y1 - y0
        print(f"  [{i}] {etype:12s} id={eid[:20]:20s} h={h:5.0f}px | {text}")
    print()
