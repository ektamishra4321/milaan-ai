"""Eval harness: matching output vs planted ground truth.

Pair-level metrics: each match group expands to (bank_id, ledger_id) pairs.
  precision = correct predicted pairs / all predicted pairs
  recall    = correct predicted pairs / all truth pairs
Plus: duplicate-detection accuracy and unmatched-set overlap.
"""

import json
from pathlib import Path


def _pairs(match_list):
    pairs = set()
    for m in match_list:
        for b in m["bank_ids"]:
            for l in m["ledger_ids"]:
                pairs.add((b, l))
    return pairs


def evaluate_month(result: dict, gt: dict) -> dict:
    pred = _pairs(result["matches"])
    truth = _pairs(gt["matches"])
    tp = len(pred & truth)
    precision = tp / len(pred) if pred else 1.0
    recall = tp / len(truth) if truth else 1.0
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)

    truth_dupes = {u["bank_id"] for u in gt["unmatched_bank"]
                   if u["reason"] == "DUPLICATE_BANK"}
    pred_dupes = {u["bank_id"] for u in result["unmatched_bank"]
                  if u.get("suspect") == "DUPLICATE"}

    truth_ub = {u["bank_id"] for u in gt["unmatched_bank"]}
    pred_ub = {u["bank_id"] for u in result["unmatched_bank"]}
    truth_ul = {u["ledger_id"] for u in gt["unmatched_ledger"]}
    pred_ul = {u["ledger_id"] for u in result["unmatched_ledger"]}

    return {
        "pairs_pred": len(pred), "pairs_truth": len(truth), "pairs_correct": tp,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(f1, 4),
        "dupes_caught": len(pred_dupes & truth_dupes),
        "dupes_truth": len(truth_dupes),
        "false_unmatched_bank": len(pred_ub - truth_ub),
        "missed_unmatched_bank": len(truth_ub - pred_ub),
        "false_unmatched_ledger": len(pred_ul - truth_ul),
        "missed_unmatched_ledger": len(truth_ul - pred_ul),
        "wrong_pairs": sorted(pred - truth)[:10],
        "missed_pairs": sorted(truth - pred)[:10],
    }


def evaluate_dir(synth_root: str, reconcile_fn, parse_statement, parse_ledger,
                 months=None):
    root = Path(synth_root)
    rows, agg = [], {"pred": 0, "truth": 0, "tp": 0}
    for mdir in sorted(root.iterdir()):
        if not mdir.is_dir():
            continue
        if months and mdir.name not in months:
            continue
        stmt = next(mdir.glob("statement_*.csv"))
        txns, _, _ = parse_statement(str(stmt))
        entries = parse_ledger(str(mdir / "ledger.csv"))
        gt = json.loads((mdir / "ground_truth.json").read_text(encoding="utf-8"))
        res = reconcile_fn(txns, entries)
        m = evaluate_month(res, gt)
        m["month"] = mdir.name
        rows.append(m)
        agg["pred"] += m["pairs_pred"]
        agg["truth"] += m["pairs_truth"]
        agg["tp"] += m["pairs_correct"]
    p = agg["tp"] / agg["pred"] if agg["pred"] else 1.0
    r = agg["tp"] / agg["truth"] if agg["truth"] else 1.0
    overall = {"precision": round(p, 4), "recall": round(r, 4),
               "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}
    return rows, overall
