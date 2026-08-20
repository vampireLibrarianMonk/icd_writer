"""Inspect pages with '28V' text in HSI_SYS_015G.pdf for artifacts."""
import fitz

doc = fitz.open("icds/digital/HSI_SYS_015G.pdf")

for page_idx in [2, 6]:  # pages 3 and 7 (0-indexed)
    page = doc[page_idx]
    print(f"\n{'='*60}")
    print(f"PAGE {page_idx + 1}")
    print(f"{'='*60}")

    # Drawings
    drawings = page.get_drawings()
    print(f"Vector drawings: {len(drawings)}")

    # Find text with 28V and check what's around it
    text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if "28V" in text or "Heater" in text or "IDPU" in text or "Switched" in text:
                    bbox = span["bbox"]
                    print(f"  Text: '{text.strip()[:40]}' at ({bbox[0]:.0f},{bbox[1]:.0f},{bbox[2]:.0f},{bbox[3]:.0f}) size={span['size']}")

    # Categorize drawings near the 28V text region
    print(f"\n  Drawing details ({len(drawings)} total):")
    for i, d in enumerate(drawings):
        rect = d.get("rect")
        if rect:
            # Check if drawing is in the body area
            r = fitz.Rect(rect)
            color = d.get("color")
            fill = d.get("fill")
            width = d.get("width", 0)
            items = d.get("items", [])
            item_types = [item[0] for item in items]
            if r.y0 > 50 and r.y1 < 700:  # body area only
                print(f"    [{i}] rect=({r.x0:.0f},{r.y0:.0f},{r.x1:.0f},{r.y1:.0f}) "
                      f"w={r.width:.1f} h={r.height:.1f} "
                      f"color={color} fill={fill} linewidth={width} "
                      f"items={item_types[:3]}")

doc.close()
