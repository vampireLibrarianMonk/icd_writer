"""Check what elements/analysis each page returns for 20130010957.pdf"""
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"

# Open
params = urlencode({"pdf_path": "icds/digital/20130010957.pdf"})
req = Request(f"{API}/document/open?{params}", method="POST")
resp = urlopen(req)
print("Opened:", json.loads(resp.read())["status"])
print()

for page in range(1, 16):
    # Elements
    req = Request(f"{API}/document/page/{page}/elements")
    resp = urlopen(req)
    data = json.loads(resp.read())
    elems = data.get("elements", [])

    # Analysis
    req2 = Request(f"{API}/document/page/{page}/analysis")
    resp2 = urlopen(req2)
    analysis = json.loads(resp2.read())
    page_type = analysis.get("page_type", "unknown")

    types = {}
    for e in elems:
        t = e.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    print(f"Page {page:2d}: page_type={page_type!r:20s} | {len(elems):3d} elements | types: {dict(types)}")
    # Show first few element texts for TOC-classified pages
    if page_type == "table_of_contents":
        for e in elems[:5]:
            print(f"         {e.get('type','')}: {e.get('text','')[:50]}")
