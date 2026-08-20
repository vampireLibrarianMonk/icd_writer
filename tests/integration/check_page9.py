import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"

# Open doc first
params = urlencode({"pdf_path": "icds/digital/20130010957.pdf"})
req = Request(f"{API}/document/open?{params}", method="POST")
resp = urlopen(req)
print("Opened:", json.loads(resp.read()))
print()

# Try basic page endpoint first
try:
    req = Request(f"{API}/document/page/9")
    resp = urlopen(req)
    data = json.loads(resp.read())
    print(f"Page 9 basic: {data.get('page_number')} - {len(data.get('blocks',[]))} blocks")
except Exception as e:
    print(f"Page 9 basic failed: {e}")

# Try elements
try:
    req = Request(f"{API}/document/page/9/elements")
    resp = urlopen(req)
    data = json.loads(resp.read())
    print(f"Page 9 elements: {len(data.get('elements',[]))} elements")
except Exception as e:
    print(f"Page 9 elements failed: {e}")

# Try page 1
try:
    req = Request(f"{API}/document/page/1/elements")
    resp = urlopen(req)
    data = json.loads(resp.read())
    print(f"Page 1 elements: {len(data.get('elements',[]))} elements")
except Exception as e:
    print(f"Page 1 elements failed: {e}")

