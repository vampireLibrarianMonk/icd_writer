"""Detailed check of the overlapping spans on page 7."""
import fitz

doc = fitz.open("icds/digital/HSI_SYS_015G.pdf")
page = doc[6]  # page 7
raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

print("ALL spans at y0≈371 (the problematic line):")
print()
for block in raw.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            bbox = span["bbox"]
            if 370 < bbox[1] < 372:
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars)
                print(f"  x0={bbox[0]:6.1f} x1={bbox[2]:6.1f} y0={bbox[1]:6.1f} y1={bbox[3]:6.1f}")
                print(f"  font={span['font']} size={span['size']} flags={span['flags']}")
                print(f"  text='{text}'")
                # Show individual char positions
                if chars:
                    print(f"  chars: first_x={chars[0]['bbox'][0]:.1f}, last_x={chars[-1]['bbox'][2]:.1f}")
                print()

print("\nSpan that contains 'Power' or 'ower':")
for block in raw.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            chars = span.get("chars", [])
            text = "".join(c["c"] for c in chars)
            if "ower" in text or "Power" in text or "levels" in text:
                bbox = span["bbox"]
                if 340 < bbox[1] < 400:
                    print(f"  x0={bbox[0]:6.1f} y0={bbox[1]:6.1f} | '{text[:60]}'")

doc.close()
