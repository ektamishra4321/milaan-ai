"""Teacher labeling: frontier LLM predicts categories on test.jsonl.

Batched (25 per call), resumable (skips already-predicted ids), telemetry
logged. Output: teacher_preds.jsonl rows {"text":..., "pred":...}.
Uses the dual-provider layer (LLM_PROVIDER=anthropic|gemini).
"""

import json
import time
from pathlib import Path

from milaan.llm import complete_json
from milaan.models import CATEGORIES

BATCH = 25

SYSTEM = (
    "You classify Indian bank statement transactions into exactly one category. "
    "Valid categories: " + ", ".join(CATEGORIES) + ". "
    "Respond with JSON only — no prose, no markdown fences."
)

PROMPT = """Classify each transaction into exactly one category from:
{cats}

Transactions (id: text):
{items}

Respond with ONLY a JSON object mapping id to category, e.g.
{{"0": "sales_receipt", "1": "rent"}}
"""


def label_file(test_path: str, out_path: str, sleep_s: float = 2.0,
               limit: int = 0):
    rows = [json.loads(l) for l in open(test_path, encoding="utf-8")]
    if limit:
        rows = rows[:limit]
    out = Path(out_path)
    done = {}
    if out.exists():
        for l in out.open(encoding="utf-8"):
            r = json.loads(l)
            done[r["text"]] = r["pred"]
    todo = [r for r in rows if r["text"] not in done]
    print(f"{len(done)} already labeled, {len(todo)} to go")

    with out.open("a", encoding="utf-8") as f:
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            items = "\n".join(f"{j}: {r['text']}" for j, r in enumerate(batch))
            try:
                preds = complete_json(
                    PROMPT.format(cats=", ".join(CATEGORIES), items=items),
                    system=SYSTEM, max_tokens=1500, agent="teacher")
            except Exception as e:
                print(f"batch {i // BATCH}: FAILED ({e}) — rerun to resume")
                time.sleep(sleep_s * 3)
                continue
            for j, r in enumerate(batch):
                pred = str(preds.get(str(j), "other")).strip()
                if pred not in CATEGORIES:
                    pred = "other"
                f.write(json.dumps({"text": r["text"], "pred": pred},
                                   ensure_ascii=False) + "\n")
            f.flush()
            print(f"labeled {min(i + BATCH, len(todo))}/{len(todo)}")
            time.sleep(sleep_s)
    print(f"done -> {out}")


def evaluate_predictions(test_path: str, preds_path: str):
    """Accuracy + per-category breakdown + confusion pairs, vs generator truth."""
    truth = {r["text"]: r["category"]
             for r in map(json.loads, open(test_path, encoding="utf-8"))}
    preds = {r["text"]: r["pred"]
             for r in map(json.loads, open(preds_path, encoding="utf-8"))}
    common = [t for t in truth if t in preds]
    if not common:
        return {"n": 0}
    correct = sum(1 for t in common if truth[t] == preds[t])
    per_cat, confusion = {}, {}
    for t in common:
        c = truth[t]
        per_cat.setdefault(c, [0, 0])
        per_cat[c][1] += 1
        if preds[t] == c:
            per_cat[c][0] += 1
        else:
            key = (c, preds[t])
            confusion[key] = confusion.get(key, 0) + 1
    return {
        "n": len(common),
        "accuracy": round(correct / len(common), 4),
        "per_category": {c: {"acc": round(a / b, 3), "n": b}
                         for c, (a, b) in sorted(per_cat.items())},
        "top_confusions": sorted(confusion.items(), key=lambda kv: -kv[1])[:8],
    }
