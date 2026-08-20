"""Audit element types using local extraction (not API).

Runs extract_text_blocks directly and checks for classification issues.
"""
from pathlib import Path
from src.extraction.text_extractor import extract_text_blocks

DOCUMENTS = [
    "icds/digital/20130010957.pdf",
    "icds/digital/20150010976.pdf",
    "icds/digital/HSI_SYS_001H.pdf",
    "icds/digital/HSI_SYS_001I.pdf",
    "icds/digital/HSI_SYS_015G.pdf",
    "icds/digital/IDSS_IDD_RevE.pdf",
    "icds/digital/IDSS_IDD_RevF.pdf",
]

results = []
for doc_path in DOCUMENTS:
    p = Path(doc_path)
    if not p.exists():
        print(f"SKIP: {p.name}")
        continue

    blocks = extract_text_blocks(p)
    issues = []

    for b in blocks:
        h = b.bbox.y1 - b.bbox.y0
        # Giant heading (>100px)
        if b.block_type == "heading" and h > 100:
            issues.append(f"p.{b.page}: Giant heading ({h:.0f}px): {b.text_verbatim[:40]}")
        # Giant paragraph (>500px) — entire page in one block
        if b.block_type == "paragraph" and h > 500:
            issues.append(f"p.{b.page}: Giant paragraph ({h:.0f}px)")
        # TOC entry as heading
        if b.block_type == "heading" and ("..." in b.text_verbatim or b.text_verbatim.count(".") > 5):
            issues.append(f"p.{b.page}: TOC as heading: {b.text_verbatim[:40]}")

    types = {}
    for b in blocks:
        types[b.block_type] = types.get(b.block_type, 0) + 1

    print(f"{p.name:25s} | {len(blocks):4d} blocks | types: {dict(types)} | issues: {len(issues)}")
    if issues:
        for iss in issues[:5]:
            print(f"  ! {iss}")
        if len(issues) > 5:
            print(f"  ... and {len(issues)-5} more")

    results.append({"name": p.name, "blocks": len(blocks), "issues": len(issues)})

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
total_issues = sum(r["issues"] for r in results)
for r in results:
    print(f"  {r['name']:25s} issues: {r['issues']}")
print(f"\nTotal issues: {total_issues}")
