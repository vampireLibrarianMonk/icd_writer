"""Alpha loop: inspect what the editor panel sees for 20130010957.pdf.

For each page, check:
1. What /document/page/{n}/header-footer returns
2. What /document/page/{n}/table-zones returns
3. What /document/page/{n}/toc returns
4. What /document/page/{n}/elements returns (clickable overlays)
5. What /document/page/{n}/analysis returns

This mirrors what the UnifiedEditor's PageElementSelector fetches.
"""
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"


def api_get(path):
    try:
        req = Request(f"{API}{path}")
        resp = urlopen(req)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def api_post(path, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url, method="POST")
    resp = urlopen(req)
    return json.loads(resp.read())


# Open the document
result = api_post("/document/open", {"pdf_path": "icds/digital/20130010957.pdf"})
print(f"Opened: {result.get('status')} — {result.get('pages')} pages")
print()

for page in range(1, result.get("pages", 0) + 1):
    print(f"{'='*60}")
    print(f"PAGE {page}")
    print(f"{'='*60}")

    # Header/Footer
    hf = api_get(f"/document/page/{page}/header-footer")
    if "error" not in hf:
        headers = hf.get("header", [])
        footers = hf.get("footer", [])
        print(f"  Header entries: {len(headers)}")
        print(f"  Footer entries: {len(footers)}")
    else:
        print(f"  Header/Footer: {hf['error'][:60]}")

    # Table zones
    tz = api_get(f"/document/page/{page}/table-zones")
    if "error" not in tz:
        zones = tz.get("zones", [])
        print(f"  Table zones: {len(zones)}")
    else:
        print(f"  Table zones: {tz['error'][:60]}")

    # TOC
    toc = api_get(f"/document/page/{page}/toc")
    if "error" not in toc:
        print(f"  TOC: is_toc={toc.get('is_toc')}, entries={len(toc.get('entries', []))}")
    else:
        print(f"  TOC: {toc['error'][:60]}")

    # Elements (overlays)
    elems = api_get(f"/document/page/{page}/elements")
    if "error" not in elems:
        elements = elems.get("elements", [])
        types = {}
        for e in elements:
            t = e.get("type", "?")
            types[t] = types.get(t, 0) + 1
        print(f"  Elements: {len(elements)} — {dict(types)}")
    else:
        print(f"  Elements: {elems['error'][:60]}")

    # What PageElementSelector would show in the dropdown
    dropdown_items = []
    if "error" not in toc and toc.get("is_toc"):
        dropdown_items.append("Table of Contents")
    if "error" not in hf and len(hf.get("header", [])) > 0:
        dropdown_items.append("Header")
    if "error" not in hf and len(hf.get("footer", [])) > 0:
        dropdown_items.append("Footer")
    if "error" not in tz:
        for i in range(len(tz.get("zones", []))):
            dropdown_items.append(f"Table {i+1}")

    if dropdown_items:
        print(f"  >>> Dropdown shows: {dropdown_items}")
    else:
        print(f"  >>> Dropdown: HIDDEN (no special sections detected)")

    print()
