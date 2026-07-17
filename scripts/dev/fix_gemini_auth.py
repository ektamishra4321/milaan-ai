"""fix_gemini_auth.py — make milaan/llm.py compatible with new AQ. Gemini keys.

Google's new Auth keys (AQ.Ab...) are most reliable when sent via the
x-goog-api-key header instead of the ?key= query parameter.
Run from inside your milaan-ai folder:  python fix_gemini_auth.py
"""

PATH = "milaan/llm.py"

REPLACEMENTS = [
    (
        '''    resp = requests.get(f"{_GEMINI_BASE}/models?key={api_key}", timeout=60)''',
        '''    resp = requests.get(f"{_GEMINI_BASE}/models",
                        headers={"x-goog-api-key": api_key}, timeout=60)'''
    ),
    (
        '''    return requests.post(
        f"{_GEMINI_BASE}/models/{model}:generateContent?key={api_key}",
        json=body,
        timeout=120,
    )''',
        '''    return requests.post(
        f"{_GEMINI_BASE}/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key},
        json=body,
        timeout=120,
    )'''
    ),
]


def main():
    src = open(PATH, encoding="utf-8").read()
    changed = 0
    for old, new in REPLACEMENTS:
        if old in src:
            src = src.replace(old, new)
            changed += 1
        elif new in src:
            print("  already patched:", new.splitlines()[0].strip())
    open(PATH, "w", encoding="utf-8", newline="\n").write(src)
    print(f"Patched {changed} call site(s) in {PATH}")
    print("Gemini key now sent via x-goog-api-key header (AQ. compatible).")


if __name__ == "__main__":
    main()
