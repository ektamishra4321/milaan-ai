"""fix_links.py — adds the live-demo line to README and sets your LinkedIn URL
on the website. No text editor needed.

Run from inside your milaan-ai folder:  python fix_links.py
"""

import os

LIVE = "https://milaan-ai.onrender.com"
DEMO_LINE = f"\n\U0001F534 **Live demo:** {LIVE}\n"


def patch_readme():
    path = "README.md"
    src = open(path, encoding="utf-8").read()
    if LIVE in src:
        print("  README: live-demo link already present")
        return
    lines = src.splitlines(keepends=True)
    # insert right after the first heading line
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(i + 1, DEMO_LINE)
            break
    open(path, "w", encoding="utf-8", newline="\n").write("".join(lines))
    print("  README: added live-demo link")


def patch_linkedin():
    path = os.path.join("templates", "index.html")
    src = open(path, encoding="utf-8").read()
    placeholder = "https://www.linkedin.com/"
    if placeholder not in src:
        print("  index.html: no placeholder found (maybe already set)")
        return
    url = input("Paste your LinkedIn profile URL and press Enter: ").strip()
    if not url.startswith("http"):
        print("  That doesn't look like a URL — skipped. Run again to retry.")
        return
    open(path, "w", encoding="utf-8", newline="\n").write(
        src.replace(placeholder, url))
    print(f"  index.html: LinkedIn button now points to {url}")


if __name__ == "__main__":
    patch_readme()
    patch_linkedin()
    print("\nDone. Now in GitHub Desktop: commit 'add live demo link + linkedin url' and Push origin.")
