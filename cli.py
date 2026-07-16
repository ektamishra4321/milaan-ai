"""MilaanAI CLI (Week 1).

  python cli.py generate --months 10 --out data/synth --seed 42
  python cli.py ingest --statement data/synth/m01/statement_hdfc.csv --ledger data/synth/m01/ledger.csv
"""

import argparse
import json
from pathlib import Path

from milaan.generator.generate import generate_month, write_month
from milaan.ingest.adapters import parse_statement, parse_ledger
from milaan.ingest.integrity import check_balance

FORMATS = ["hdfc", "icici", "sbi"]


def cmd_generate(args):
    out_root = Path(args.out)
    for i in range(args.months):
        seed = args.seed + i
        month = (i % 12) + 1
        bank, ledger, gt = generate_month(seed, 2026, month)
        fmt = FORMATS[i % 3]
        mdir = out_root / f"m{i+1:02d}"
        write_month(str(mdir), fmt, bank, ledger, gt)
        n_disc = len(gt["unmatched_bank"]) + len(gt["unmatched_ledger"]) + sum(
            1 for m in gt["matches"] if m["type"] != "CLEAN")
        print(f"m{i+1:02d} [{fmt.upper():5}] bank={len(bank):3} "
              f"ledger={len(ledger):3} planted_discrepancies={n_disc}")
    print(f"\nDone -> {out_root}  (last {args.holdout} months are HOLDOUT — "
          "do not tune against them)")


def cmd_ingest(args):
    txns, opening, fmt = parse_statement(args.statement)
    report = check_balance(txns, opening)
    print(f"Format detected : {fmt.upper()}")
    print(f"Transactions    : {report['n_txns']}")
    print(f"Opening balance : {report['opening']:,.2f}")
    print(f"Closing balance : {report['closing']:,.2f}")
    print("Balance check   : PASSED")
    if args.ledger:
        entries = parse_ledger(args.ledger)
        print(f"Ledger entries  : {len(entries)}")
    print("\nFirst 5 normalized txns:")
    for t in txns[:5]:
        print(f"  {t.txn_id} {t.date} {t.direction:6} {t.amount:>12,.2f}  "
              f"{t.narration[:48]}")




def cmd_reconcile(args):
    import json as _json
    from milaan.match.engine import reconcile as _rec
    from milaan.report.excel import write_report
    txns, opening, fmt = parse_statement(args.statement)
    check_balance(txns, opening)
    entries = parse_ledger(args.ledger)
    result = _rec(txns, entries)
    categories = None
    if args.categorize:
        from milaan.categorize import categorize_txns
        unmatched_ids = {u["bank_id"] for u in result["unmatched_bank"]}
        categories = categorize_txns([t for t in txns if t.txn_id in unmatched_ids])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_bank = len(txns)
    n_matched = sum(len(m["bank_ids"]) for m in result["matches"])
    write_report(str(out), result, txns, entries,
                 meta={"Statement": args.statement, "Format": fmt.upper()},
                 categories=categories)
    (out.with_suffix(".json")).write_text(
        _json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Matched {n_matched}/{n_bank} bank txns "
          f"({n_matched/n_bank:.1%}) via {len(result['matches'])} match groups")
    print(f"Needs review: {len(result['unmatched_bank'])} bank, "
          f"{len(result['unmatched_ledger'])} ledger")
    print(f"Report -> {out}")


def cmd_eval(args):
    from milaan.match.engine import reconcile as _rec
    from milaan.evalx.harness import evaluate_dir
    months = set(args.months.split(",")) if args.months else None
    rows, overall = evaluate_dir(args.dir, _rec, parse_statement, parse_ledger,
                                 months=months)
    for r in rows:
        print(f"{r['month']}: P={r['precision']:.3f} R={r['recall']:.3f} "
              f"F1={r['f1']:.3f} dupes {r['dupes_caught']}/{r['dupes_truth']}")
        for w in r["wrong_pairs"]:
            print(f"   WRONG {w}")
        for w in r["missed_pairs"]:
            print(f"   MISSED {w}")
    print(f"OVERALL: P={overall['precision']:.4f} R={overall['recall']:.4f} "
          f"F1={overall['f1']:.4f}")



def cmd_ftdata(args):
    from milaan.finetune.datagen import generate_dataset
    counts = generate_dataset(args.out, n_train=args.train, n_val=args.val,
                              n_test=args.test, seed=args.seed)
    print(f"dataset -> {args.out}  {counts}")


def cmd_teacher(args):
    from milaan.finetune.teacher import label_file
    label_file(args.test, args.out, limit=args.limit)


def cmd_evalcat(args):
    import json as _json
    from milaan.finetune.teacher import evaluate_predictions
    rep = evaluate_predictions(args.test, args.preds)
    print(_json.dumps(rep, indent=2))

def main():
    p = argparse.ArgumentParser(prog="milaan")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--months", type=int, default=10)
    g.add_argument("--out", default="data/synth")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--holdout", type=int, default=3)
    g.set_defaults(func=cmd_generate)

    i = sub.add_parser("ingest")
    i.add_argument("--statement", required=True)
    i.add_argument("--ledger")
    i.set_defaults(func=cmd_ingest)

    r = sub.add_parser("reconcile")
    r.add_argument("--statement", required=True)
    r.add_argument("--ledger", required=True)
    r.add_argument("--out", default="outputs/reconciliation_report.xlsx")
    r.add_argument("--categorize", action="store_true",
                   help="LLM-categorize unmatched bank lines in the report")
    r.set_defaults(func=cmd_reconcile)

    e = sub.add_parser("eval")
    e.add_argument("--dir", default="data/synth")
    e.add_argument("--months", help="comma-separated, e.g. m08,m09,m10")
    e.set_defaults(func=cmd_eval)

    fd = sub.add_parser("finetune-data")
    fd.add_argument("--out", default="data/finetune")
    fd.add_argument("--train", type=int, default=8000)
    fd.add_argument("--val", type=int, default=1000)
    fd.add_argument("--test", type=int, default=1000)
    fd.add_argument("--seed", type=int, default=42)
    fd.set_defaults(func=cmd_ftdata)

    tl = sub.add_parser("teacher-label")
    tl.add_argument("--test", default="data/finetune/test.jsonl")
    tl.add_argument("--out", default="data/finetune/teacher_preds.jsonl")
    tl.add_argument("--limit", type=int, default=500)
    tl.set_defaults(func=cmd_teacher)

    ec = sub.add_parser("eval-cat")
    ec.add_argument("--test", default="data/finetune/test.jsonl")
    ec.add_argument("--preds", required=True)
    ec.set_defaults(func=cmd_evalcat)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
