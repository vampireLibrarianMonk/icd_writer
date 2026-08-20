"""Check the spans around 'power levels' and 'programmable' on page 7."""
import fitz

doc = fitz.open("icds/digital/HSI_SYS_015G.pdf")
page = doc[6]  # page 7
raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

# Find the paragraph about coldplate heater
print("All spans in the 'Coldplate heater' paragraph area (y=350-420):")
print()
for block in raw.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            bbox = span["bbox"]
            if 340 < bbox[1] < 420:
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars).strip()
                if text:
                    h = bbox[3] - bbox[1]
                    print(f"  y0={bbox[1]:6.1f} y1={bbox[3]:6.1f} h={h:4.1f} size={span['size']:4.1f} | {text[:70]}")

# Also check what's around y=360-400 (where the overlap might happen)
print("\n\nAll spans y=360-400:")
for block in raw.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            bbox = span["bbox"]
            if 360 < bbox[1] < 400:
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars).strip()
                if text:
                    print(f"  y0={bbox[1]:6.1f} y1={bbox[3]:6.1f} size={span['size']:4.1f} | {text[:70]}")

doc.close()
