"""Alpha loop: inspect comparison output for HSI_SYS_001 H→I."""
from pathlib import Path
from collections import Counter
from src.briefing.section_diff import compare_revisions

result = compare_revisions(
    Path("icds/digital/HSI_SYS_001H.pdf"),
    Path("icds/digital/HSI_SYS_001I.pdf"),
)

print("GLOBAL CHANGES (extracted boilerplate):")
print("=" * 80)
for gc in result.global_changes:
    print(f"  {gc}")

print(f"\nStats: {result.total_sections_changed} changed, {result.total_sections_unchanged} unchanged")
print()

# Show all modified sections with their details
print("MODIFIED SECTIONS:")
print("=" * 80)
for s in result.sections:
    if s.change_type == "unchanged":
        continue
    print(f"\n[{s.change_type.upper()}] {s.section_heading} (p.{s.page_new})")
    print(f"  Classification: {s.classification}" + (" | REQ CHANGE" if s.has_requirement_change else ""))
    if s.value_changes:
        print(f"  Value changes:")
        for vc in s.value_changes:
            print(f"    {vc.parameter}: {vc.old_value}{vc.unit} → {vc.new_value}{vc.unit}")
    if s.tbd_delta and (s.tbd_delta.resolved or s.tbd_delta.introduced):
        print(f"  TBD resolved: {len(s.tbd_delta.resolved)}, introduced: {len(s.tbd_delta.introduced)}")
    if s.text_snippets:
        print(f"  Text snippets:")
        for sn in s.text_snippets:
            print(f"    {sn}")
    print(f"  Summary: {s.summary_line}")

