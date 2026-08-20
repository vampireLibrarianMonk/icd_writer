"""Inspect page 8 of HSI_SYS_015G.pdf for non-text artifacts."""
import fitz
from pathlib import Path

doc = fitz.open("icds/digital/HSI_SYS_015G.pdf")
page = doc[7]  # page 8, 0-indexed

print(f"Page 8: {page.rect.width:.0f} x {page.rect.height:.0f}")
print()

# Text blocks
text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
text_blocks = [b for b in text_dict.get("blocks", []) if b.get("type") == 0]
image_blocks = [b for b in text_dict.get("blocks", []) if b.get("type") == 1]
print(f"Text blocks: {len(text_blocks)}")
print(f"Image blocks: {len(image_blocks)}")
for ib in image_blocks:
    print(f"  Image: bbox={ib['bbox']}, size={ib.get('width','?')}x{ib.get('height','?')}")

# Drawings (vector art — lines, rectangles, paths)
drawings = page.get_drawings()
print(f"\nDrawings (vector elements): {len(drawings)}")
if drawings:
    # Categorize
    lines = [d for d in drawings if d.get("type") == "l" or len(d.get("items", [])) == 1]
    rects = [d for d in drawings if d.get("type") == "re" or d.get("rect")]
    others = [d for d in drawings if d not in lines and d not in rects]
    print(f"  Lines: {len(lines)}, Rects: {len(rects)}, Other paths: {len(others)}")
    # Show first few
    for d in drawings[:5]:
        items = d.get("items", [])
        rect = d.get("rect")
        color = d.get("color")
        fill = d.get("fill")
        print(f"  rect={rect}, color={color}, fill={fill}, items={len(items)}")

# Images on page
images = page.get_images(full=True)
print(f"\nEmbedded images: {len(images)}")
for img in images:
    xref = img[0]
    w, h = img[2], img[3]
    print(f"  xref={xref}, {w}x{h}")

# What elements does our extractor produce?
from src.extraction.text_extractor import extract_text_blocks
blocks = extract_text_blocks(Path("icds/digital/HSI_SYS_015G.pdf"), pages=[8])
print(f"\nOur extracted elements: {len(blocks)}")
for b in blocks:
    h = b.bbox.y1 - b.bbox.y0
    print(f"  {b.block_type:12s} h={h:.0f} | {b.text_verbatim[:50]}")

doc.close()
