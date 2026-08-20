import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"

# Open
r = urlopen(Request(f"{API}/document/open?" + urlencode({"pdf_path": "icds/digital/HSI_SYS_001I.pdf"}), method="POST"))
info = json.loads(r.read())
print("Open:", info)

# Elements page 6
r = urlopen(Request(f"{API}/document/page/6/elements"))
data = json.loads(r.read())
elems = data.get("elements", [])
print(f"Page 6 elements: {len(elems)}")
for e in elems[:5]:
    h = e["bbox"]["y1"] - e["bbox"]["y0"]
    print(f"  {e['type']:12s} h={h:.0f} | {e['text'][:50]}")
