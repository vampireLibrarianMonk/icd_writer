"""Check why page 2 of 20130010957.pdf is classified as TOC."""
import fitz
import re

doc = fitz.open("icds/digital/20130010957.pdf")
page = doc[1]  # page 2 (0-indexed)
raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
page_height = page.rect.height

body_spans = []
for block in raw.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            chars = span.get("chars", [])
            text = "".join(c["c"] for c in chars).strip()
            if not text:
                continue
            y = span["bbox"][1]
            if 60 <= y <= page_height - 72:
                body_spans.append(text)

print(f"Body spans on page 2: {len(body_spans)}")
print()

toc_matches = []
section_matches = []
for s in body_spans:
    is_toc = ("..." in s or s.count(".") > 5) and bool(re.search(r"\d+\s*$", s))
    is_section = bool(re.match(r"^\d+[\.\d]*\.?\s+\w", s))
    if is_toc:
        toc_matches.append(s)
    if is_section:
        section_matches.append(s)
    flag = ""
    if is_toc:
        flag += "TOC "
    if is_section:
        flag += "SEC "
    print(f"  {flag:8s}| {s[:80]}")

print(f"\nTOC line matches: {len(toc_matches)}")
print(f"Section numbered matches: {len(section_matches)}")
triggered = len(toc_matches) >= 3 or (len(toc_matches) >= 2 and len(section_matches) >= 2)
print(f"has_toc triggered: {triggered}")

if toc_matches:
    print("\nTOC-matched lines:")
    for t in toc_matches:
        print(f"  '{t[:80]}'")

doc.close()
