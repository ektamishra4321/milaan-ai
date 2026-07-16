"""fix_byline.py — change the byline to Ekta across the site and README.

Run from inside your milaan-ai folder:  python fix_byline.py
"""

import os

TARGETS = [
    "templates/index.html",   # the live web app page
    "index_dark.html",        # dark landing page (if present)
    "index.html",             # ledger landing page (if present)
    "docs/index.html",        # GitHub Pages copy (if present)
    "README.md",
]

REPLACEMENTS = [
    ("built by Prabhakar", "built by Ekta Mishra"),
    ("Built by Prabhakar", "Built by Ekta Mishra"),
]


def main():
    changed_any = False
    for rel in TARGETS:
        path = rel.replace("/", os.sep)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        out = src
        for old, new in REPLACEMENTS:
            out = out.replace(old, new)
        if out != src:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
            print(f"  updated: {rel}")
            changed_any = True
        else:
            print(f"  no byline found (already fine): {rel}")
    if not changed_any:
        print("Nothing needed changing.")
    else:
        print("\nDone. Refresh the page in Chrome (Ctrl+Shift+R) to see it.")


if __name__ == "__main__":
    main()
