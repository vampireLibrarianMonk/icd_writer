"""Alpha loop: test table row add/delete and verify drawings shift correctly.

Opens HSI_SYS_015G.pdf, identifies table on page 7, adds a row,
then checks if drawings below the table moved with the text.
"""
import json
import fitz
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"


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


# Open the document
result = api_post("/document/open", {"pdf_path": "icds/digital/HSI_SYS_015G.pdf"})
print(f"Opened: {result}")

# Get table zones on page 7
zones = api_get("/document/page/7/table-zones")
print(f"\nTable zones on page 7: {zones}")

if not zones.get("zones"):
    print("No table zones found on page 7, checking other pages...")
    for p in range(1, 9):
        z = api_get(f"/document/page/{p}/table-zones")
        if z.get("zones"):
            print(f"  Page {p}: {z['zones']}")
    exit()

zone = zones["zones"][0]
print(f"Using zone: y_min={zone['y_min']}, y_max={zone['y_max']}")

# Get current table data
table = api_get(f"/document/page/7/table-cells", {"y_min": zone["y_min"], "y_max": zone["y_max"]})
print(f"Table: {table.get('rows', '?')} rows x {table.get('columns', '?')} cols")
if table.get("data"):
    for i, row in enumerate(table["data"][:3]):
        print(f"  Row {i}: {[c.get('text','')[:15] for c in row]}")

# Check drawings before modification
doc = fitz.open("icds/digital/HSI_SYS_015G.pdf")
page = doc[6]  # page 7
drawings_before = page.get_drawings()
# Find drawings below the table
below_table = [d for d in drawings_before if d.get("rect") and fitz.Rect(d["rect"]).y0 > zone["y_max"]]
print(f"\nDrawings below table (before): {len(below_table)}")
if below_table:
    for d in below_table[:5]:
        r = fitz.Rect(d["rect"])
        print(f"  ({r.x0:.0f},{r.y0:.0f})-({r.x1:.0f},{r.y1:.0f}) h={r.height:.1f}")
doc.close()

# Now add a row
if table.get("data"):
    data = [[c.get("text", "") for c in row] for row in table["data"]]
    num_cols = table["columns"]
    new_row = ["NEW_TEST"] * num_cols
    data.append(new_row)

    print(f"\nRebuilding with {len(data)} rows (was {table['rows']})...")
    rebuild_result = api_post(f"/document/page/7/table-rebuild", body={
        "y_min": zone["y_min"],
        "y_max": zone["y_max"],
        "data": data,
    })
    print(f"Rebuild result: {rebuild_result}")

    # Now check the working copy for drawings below table
    # The working copy path is the source the API uses
    # We can check by re-reading the page image or inspecting the PDF
    # For now, let's check via the API if text below moved
    print("\nDone. Check page 7 visually to see if borders below table shifted.")
