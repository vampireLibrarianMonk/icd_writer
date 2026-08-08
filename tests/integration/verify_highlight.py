"""Verify that the compare highlight matching logic finds the correct
overlay block for each section heading on the right page.

This runs the same matching algorithm that DocumentView uses in the browser,
against the real API endpoint that serves overlay elements.

Usage: python tests/integration/verify_highlight.py
Requires: Docker backend running on localhost:8000
"""

import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.version_diff import _extract_sections

API_BASE = "http://localhost:8000"


def open_document(pdf_path: str) -> dict:
    params = urlencode({"pdf_path": pdf_path})
    req = Request(f"{API_BASE}/document/open?{params}", method="POST")
    resp = urlopen(req)
    return json.loads(resp.read())


def get_page_elements(page: int) -> list[dict]:
    req = Request(f"{API_BASE}/document/page/{page}/elements")
    resp = urlopen(req)
    data = json.loads(resp.read())
    return data.get("elements", [])


def match_heading_to_overlay(heading: str, elements: list[dict]) -> tuple[int, float, str]:
    """Same matching logic as DocumentView's useEffect."""
    heading_lower = heading.lower()
    best_idx = -1
    best_score = 0.0
    best_text = ""

    for i, el in enumerate(elements):
        ov_text = el.get("text", "").lower()
        # Exact substring match
        if heading_lower in ov_text or ov_text.strip() in heading_lower:
            return i, 1.0, el.get("text", "")[:60]
        # Word overlap
        heading_words = [w for w in heading_lower.split() if len(w) > 2]
        if heading_words:
            matches = sum(1 for w in heading_words if w in ov_text)
            score = matches / len(heading_words)
            if score > best_score:
                best_score = score
                best_idx = i
                best_text = el.get("text", "")[:60]

    return best_idx, best_score, best_text


def verify_document(pdf_path: str):
    print(f"\n{'='*80}")
    print(f"Verifying: {pdf_path}")
    print(f"{'='*80}")

    # Open in backend
    result = open_document(pdf_path)
    print(f"Opened: {result.get('status', 'unknown')} ({result.get('pages', '?')} pages)")

    # Extract sections
    sections = _extract_sections(Path(pdf_path))
    print(f"Sections extracted: {len(sections)}")
    print()

    header = f"{'Status':<6} {'Page':<5} {'Section Heading':<50} {'Score':<6} {'Matched Overlay'}"
    print(header)
    print("-" * len(header))

    hits = 0
    misses = []
    for s in sections:
        heading = s["heading"]
        page = s["page"]

        elements = get_page_elements(page)
        idx, score, matched_text = match_heading_to_overlay(heading, elements)

        status = "OK" if score >= 0.3 else "MISS"
        if status == "OK":
            hits += 1
        else:
            misses.append((page, heading))

        heading_display = heading[:48]
        matched_display = matched_text[:40]
        print(f"{status:<6} p.{page:<3} {heading_display:<50} {score:.2f}   {matched_display}")

    print(f"\nResult: {hits}/{len(sections)} sections matched ({hits/len(sections)*100:.0f}%)")
    if misses:
        print(f"\nMisses ({len(misses)}):")
        for page, heading in misses[:10]:
            print(f"  p.{page}: {heading[:60]}")

    return hits, len(sections)


if __name__ == "__main__":
    docs = [
        "icds/digital/HSI_SYS_001I.pdf",
        "icds/digital/IDSS_IDD_RevF.pdf",
    ]

    total_hits = 0
    total_sections = 0

    for doc in docs:
        try:
            h, t = verify_document(doc)
            total_hits += h
            total_sections += t
        except HTTPError as e:
            print(f"FAILED to verify {doc}: {e.code} {e.reason}")
        except Exception as e:
            print(f"ERROR verifying {doc}: {e}")

    print(f"\n{'='*80}")
    print(f"TOTAL: {total_hits}/{total_sections} ({total_hits/max(total_sections,1)*100:.0f}%)")
    if total_hits / max(total_sections, 1) >= 0.7:
        print("PASS — majority of sections can be highlighted correctly")
    else:
        print("FAIL — too many sections cannot be matched to overlays")
