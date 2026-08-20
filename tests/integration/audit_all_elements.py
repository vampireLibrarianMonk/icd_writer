"""Audit element types across all test corpus documents.

For each document, opens it via the API, inspects every page's elements,
and reports:
1. Element type distribution per page
2. Misclassification indicators (headings in footer zone, huge paragraphs, etc.)
3. Pages with no body elements (potential issues)
4. Summary statistics

Documents tested (from TEST_DOCUMENT_CORPUS.md):
- 20130010957.pdf (TSAFE ICD)
- 20150010976.pdf
- HSI_SYS_001H.pdf
- HSI_SYS_001I.pdf
- HSI_SYS_015G.pdf
- IDSS_IDD_RevE.pdf
- IDSS_IDD_RevF.pdf
"""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "http://localhost:8000"


def api_post(path, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url, method="POST")
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())


def api_get(path):
    req = Request(f"{API}{path}")
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())


def audit_document(pdf_path):
    """Audit all pages of a document and return summary."""
    filename = Path(pdf_path).name
    print(f"\n{'#'*70}")
    print(f"# {filename}")
    print(f"{'#'*70}")

    # Open
    try:
        info = api_post("/document/open", {"pdf_path": pdf_path})
    except Exception as e:
        print(f"  FAILED TO OPEN: {e}")
        return None

    pages = info.get("pages", 0)
    print(f"  Pages: {pages}, Text blocks: {info.get('text_blocks', 0)}")
    print()

    issues = []
    page_summaries = []

    for page_num in range(1, pages + 1):
        try:
            data = api_get(f"/document/page/{page_num}/elements")
            elements = data.get("elements", [])
        except Exception as e:
            issues.append(f"Page {page_num}: Failed to get elements: {e}")
            continue

        # Categorize
        type_counts = {}
        body_elements = []
        header_footer_elements = []

        for e in elements:
            etype = e.get("type", "unknown")
            type_counts[etype] = type_counts.get(etype, 0) + 1

            bbox = e.get("bbox", {})
            y0 = bbox.get("y0", 0)
            y1 = bbox.get("y1", 0)
            h = y1 - y0

            # Classify zone
            if y0 < 60 or y1 > 700:
                header_footer_elements.append(e)
            else:
                body_elements.append(e)

            # Check for issues
            # 1. Heading with huge height (probably not a heading)
            if etype == "heading" and h > 100:
                issues.append(
                    f"Page {page_num}: Heading with height {h:.0f}px — likely misclassified: "
                    f"'{e.get('text', '')[:40]}'"
                )

            # 2. Single paragraph spanning entire page (>500px)
            if etype == "paragraph" and h > 500:
                issues.append(
                    f"Page {page_num}: Giant paragraph ({h:.0f}px) — entire page in one block"
                )

        # 3. No body elements
        if not body_elements and pages > 1:
            issues.append(f"Page {page_num}: No body elements (only header/footer)")

        page_summaries.append({
            "page": page_num,
            "total": len(elements),
            "body": len(body_elements),
            "types": type_counts,
        })

    # Print page summary table
    print(f"  {'Page':>4} | {'Total':>5} | {'Body':>4} | Types")
    print(f"  {'-'*4}-+-{'-'*5}-+-{'-'*4}-+{'-'*40}")
    for ps in page_summaries:
        types_str = ", ".join(f"{k}:{v}" for k, v in sorted(ps["types"].items()))
        print(f"  {ps['page']:4d} | {ps['total']:5d} | {ps['body']:4d} | {types_str}")

    # Print issues
    if issues:
        print(f"\n  ISSUES ({len(issues)}):")
        for issue in issues:
            print(f"    ! {issue}")
    else:
        print(f"\n  No issues found.")

    # Summary stats
    total_elements = sum(ps["total"] for ps in page_summaries)
    total_body = sum(ps["body"] for ps in page_summaries)
    all_types = {}
    for ps in page_summaries:
        for k, v in ps["types"].items():
            all_types[k] = all_types.get(k, 0) + v

    print(f"\n  TOTALS: {total_elements} elements ({total_body} body), types: {dict(all_types)}")
    return {"filename": filename, "pages": pages, "elements": total_elements, "issues": len(issues)}


# ─── Run audit ─────────────────────────────────────────────────

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
    if not Path(doc_path).exists():
        print(f"\n  SKIPPED (not found): {doc_path}")
        continue
    r = audit_document(doc_path)
    if r:
        results.append(r)

# Final summary
print(f"\n\n{'='*70}")
print("AUDIT SUMMARY")
print(f"{'='*70}")
print(f"{'Document':<25} {'Pages':>5} {'Elements':>8} {'Issues':>6}")
print(f"{'-'*25} {'-'*5} {'-'*8} {'-'*6}")
total_issues = 0
for r in results:
    print(f"{r['filename']:<25} {r['pages']:>5} {r['elements']:>8} {r['issues']:>6}")
    total_issues += r["issues"]
print(f"\nTotal issues: {total_issues}")
if total_issues == 0:
    print("PASS — all elements properly typed")
else:
    print(f"NEEDS ATTENTION — {total_issues} issues found")
