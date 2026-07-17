"""CI eval gate: matching engine must clear the PRD bar on holdout months.

Bar (from PRD §6): precision >= 0.98, recall >= 0.90 on m08-m10.
Exits non-zero (fails the build) if the bar is missed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from milaan.ingest.adapters import parse_statement, parse_ledger
from milaan.match.engine import reconcile
from milaan.evalx.harness import evaluate_dir

P_BAR, R_BAR = 0.98, 0.90


def main():
    rows, overall = evaluate_dir("data/synth", reconcile, parse_statement,
                                 parse_ledger, months={"m08", "m09", "m10"})
    for r in rows:
        print(f"{r['month']}: P={r['precision']:.4f} R={r['recall']:.4f} "
              f"F1={r['f1']:.4f} dupes {r['dupes_caught']}/{r['dupes_truth']}")
    print(f"HOLDOUT OVERALL: P={overall['precision']:.4f} "
          f"R={overall['recall']:.4f} (bar: P>={P_BAR}, R>={R_BAR})")
    if overall["precision"] < P_BAR or overall["recall"] < R_BAR:
        print("EVAL GATE: FAIL")
        sys.exit(1)
    print("EVAL GATE: PASS")


if __name__ == "__main__":
    main()
