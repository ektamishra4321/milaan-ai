"""fix_milaan.py — run from the milaan-ai repo root.
1. Adds CI + Python badges to README
2. Fixes the dangling `docs/` reference (no docs/ dir exists in the repo)
After running: review in GitHub Desktop, commit, push. Then move this to scripts/dev/.
"""
import sys
from pathlib import Path

rd = Path("README.md")
if not rd.exists() or not Path("milaan").is_dir():
    sys.exit("ERROR: run this from the milaan-ai repo root.")
text = rd.read_text(encoding="utf-8")

title = "# MilaanAI — UPI/Bank-Statement Reconciliation Agent for Indian CA Firms\n"
badges = ("![CI](https://github.com/ektamishra4321/milaan-ai/actions/workflows/ci.yml/badge.svg)\n"
          "![Python](https://img.shields.io/badge/python-3.10%2B-blue)\n")
if "actions/workflows/ci.yml/badge.svg" not in text:
    if title not in text:
        sys.exit("ERROR: README title line not found — aborting, nothing changed.")
    text = text.replace(title, title + badges, 1)
    print("[1/2] Added CI badge to README.")
else:
    print("[1/2] CI badge already present — skipped.")

old_line = "Built by Ekta Mishra, 2026. PRD and build notes in `docs/`.\n"
new_line = "Built by Ekta Mishra, 2026. Fine-tuning notebooks in `notebooks/`.\n"
if old_line in text:
    text = text.replace(old_line, new_line, 1)
    print("[2/2] Fixed dangling docs/ reference (now points to notebooks/).")
elif new_line in text:
    print("[2/2] docs/ reference already fixed — skipped.")
else:
    print("[2/2] WARNING: byline not found verbatim — check the last line of README manually.")
rd.write_text(text, encoding="utf-8", newline="\n")
print("\nDone. Review in GitHub Desktop -> commit -> push.")