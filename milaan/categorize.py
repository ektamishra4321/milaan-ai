"""Categorize bank transactions for the exception report.

Uses the LLM provider (batched); degrades gracefully offline — if the LLM
is unreachable, categories become "uncategorized" and the report still ships.
(The fine-tuned local model can replace this backend later via Ollama.)
"""

import json

from milaan.llm import complete_json, LLMError
from milaan.models import CATEGORIES

BATCH = 25

SYSTEM = ("You classify Indian bank statement transactions into exactly one "
          "category. Valid categories: " + ", ".join(CATEGORIES) +
          ". Respond with JSON only.")

PROMPT = """Classify each transaction into exactly one category from:
{cats}

Transactions (id: text):
{items}

Respond with ONLY a JSON object mapping id to category."""


def _text(t):
    return f"DIR={t.direction} | AMT={int(t.amount)} | NARR={t.narration}"


def categorize_txns(txns):
    """Returns {txn_id: category}. Never raises; falls back to 'uncategorized'."""
    out = {}
    for i in range(0, len(txns), BATCH):
        batch = txns[i:i + BATCH]
        items = "\n".join(f"{j}: {_text(t)}" for j, t in enumerate(batch))
        try:
            preds = complete_json(PROMPT.format(cats=", ".join(CATEGORIES),
                                                items=items),
                                  system=SYSTEM, max_tokens=1500,
                                  agent="categorizer")
        except Exception:
            preds = {}
        for j, t in enumerate(batch):
            p = str(preds.get(str(j), "uncategorized")).strip()
            out[t.txn_id] = p if p in CATEGORIES else "uncategorized"
    return out
