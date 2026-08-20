"""Check what the API returns for pages of 20130010957.pdf — specifically TOC detection."""
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"

# Open doc
params = urlencode({"pdf_path": "icds/digital/20130010957.pdf"})
req = Request(f"{API}/document/open?{params}", method="POST")
resp = urlopen(req)
print("Open:", json.loads(resp.read()))

# Check TOC endpoint for multiple pages
for page in range(1, 8):
    try:
        req = Request(f"{API}/document/page/{page}/toc")
        resp = urlopen(req)
        data = json.loads(resp.read())
        is_toc = data.get("is_toc", False)
        entries = data.get("entries", [])
        print(f"  Page {page}: is_toc={is_toc}, entries={len(entries)}")
        if entries:
            for e in entries[:3]:
                print(f"    {e.get('title','')[:40]} | page_ref={e.get('page_ref','')}")
    except Exception as e:
        print(f"  Page {page}: ERROR {e}")
