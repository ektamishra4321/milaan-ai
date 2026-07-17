"""
fix_review_issues.py — addresses the three review findings:
  1. Honest README (caveats stated, exact teacher number, no TODO in results)
  2. CI: pytest + holdout eval gate (P>=0.98/R>=0.90) on every push
  3. Repo cleanup: scaffolding/fix scripts -> scripts/dev/, duplicates removed

Run from inside your milaan-ai folder:  python fix_review_issues.py
"""
import os
import shutil

FILES = {}

FILES['README.md'] = "# MilaanAI — UPI/Bank-Statement Reconciliation Agent for Indian CA Firms\n\n**Deterministic where money is counted. ML only where judgment is needed. Everything measured — with the caveats stated.**\n\nSmall CA firms reconcile client bank statements against ledgers by hand — 2-4 hours\nper client per month. MilaanAI parses the statement (HDFC/ICICI/SBI), matches every\ntransaction it can prove, categorizes the rest with a fine-tuned local model, and\noutputs an Excel exception report with only the items needing human review.\n\n## Results — and what they do and don't show\n\n| Component | Measured on | Result | Caveat |\n|---|---|---|---|\n| Matching engine (deterministic) | Held-out **synthetic** months (m08-m10) | P 1.000 / R 1.000 | In-distribution: the generator and matcher were written by the same author, so treat this as an upper bound, not field performance. CI enforces the PRD bar (P≥0.98, R≥0.90) on every push. **Real-data pilot pending.** |\n| Fine-tuned categorizer — Qwen2.5-3B + LoRA | 1,000-sample held-out test | **99.8%** (998/1000) | Test set is synthetic narrations; both errors are person-named UPI credits — the genuinely ambiguous class. |\n| Teacher baseline — gemini-flash-lite, prompted | 300-sample test, same distribution | **97.0%** (291/300) | Same exam, same answer key. The fine-tuned student beats the prompted teacher in-distribution, at ₹0 inference. |\n| Typical synthetic client month | ~69 bank lines | 94.2% auto-matched | ~4 lines left for human review. |\n\n**Known limitation, stated upfront:** all current numbers come from synthetic data with\nplanted, labeled discrepancies. That makes precision/recall *exact* rather than estimated —\nbut it does not prove real-world performance. Validating on one anonymized real client\nmonth with a CA is the next milestone; adapters for real statement exports are built for\nexactly the three formats the generator mimics.\n\n## Why the eval harness is the point\n\nThe first end-to-end run scored **1% precision** — the harness caught a real ID-mapping\nbug between generator and adapter. Iterating against measured numbers (1% → 99.8% → 100%\nin identified, explainable steps, including reordering exact-sum passes above tolerance\npasses after diagnosing a false match) is the working method this repo demonstrates.\nEvery push re-runs the gate in CI.\n\n## Architecture\n\n```\nbank.csv + ledger.csv ─▶ [Ingest + balance-integrity firewall]\n        ─▶ [Matching engine: 4 deterministic tiers, rule-ID + explanation per match]\nmatched ──────────────────────────────────────────────┐\nunmatched ─▶ [Fine-tuned categorizer] ─▶ [Report: Excel exceptions]\n                          everything ─▶ [Eval harness vs planted ground truth, gated in CI]\n```\n\n- **No ML in the money path.** Matches come only from rule-based passes; every match\n  carries a rule-ID, score, and plain-language explanation.\n- **Balance-integrity firewall:** opening + Σtxns must equal closing, per row, or the\n  run halts before matching.\n- **Distillation:** frontier LLM as teacher, LoRA-tuned Qwen2.5-3B as student, both\n  graded on the same held-out exam.\n\n## Quickstart\n\n```\npip install -r requirements.txt\npython -m pytest                                  # 30 deterministic tests, no API keys\npython cli.py generate --months 10 --out data/synth\npython cli.py reconcile --statement data/synth/m01/statement_hdfc.csv \\\n    --ledger data/synth/m01/ledger.csv --out outputs/report.xlsx\npython scripts/ci_eval_gate.py                    # the same gate CI runs\npython webapp.py                                  # live demo at 127.0.0.1:5000\n```\n\n## Repo map\n\n```\nmilaan/            engine: generator, adapters, matcher, finetune, report, eval\nscripts/           ci_eval_gate.py (CI gate) · dev/ (build-time scaffolding scripts)\nnotebooks/         Colab fine-tuning + prediction notebooks\ntests/             30 deterministic tests\nwebapp.py          Flask live demo (deterministic path, no keys needed)\n.github/workflows/ CI: pytest + holdout eval gate on every push\n```\n\nBuilt by Ekta Mishra, 2026. PRD and build notes in `docs/`.\n"

FILES['.github/workflows/ci.yml'] = 'name: ci\n\non:\n  push:\n    branches: [main]\n  pull_request:\n\njobs:\n  test-and-eval:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: "3.11"\n      - name: Install dependencies\n        run: pip install -r requirements.txt\n      - name: Unit tests (30, deterministic, no API keys)\n        run: python -m pytest -q\n      - name: Generate synthetic ground truth\n        run: python cli.py generate --months 10 --out data/synth\n      - name: Matching eval gate (holdout m08-m10, P>=0.98 R>=0.90)\n        run: python scripts/ci_eval_gate.py\n'

FILES['scripts/ci_eval_gate.py'] = '"""CI eval gate: matching engine must clear the PRD bar on holdout months.\n\nBar (from PRD §6): precision >= 0.98, recall >= 0.90 on m08-m10.\nExits non-zero (fails the build) if the bar is missed.\n"""\n\nimport sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n\nfrom milaan.ingest.adapters import parse_statement, parse_ledger\nfrom milaan.match.engine import reconcile\nfrom milaan.evalx.harness import evaluate_dir\n\nP_BAR, R_BAR = 0.98, 0.90\n\n\ndef main():\n    rows, overall = evaluate_dir("data/synth", reconcile, parse_statement,\n                                 parse_ledger, months={"m08", "m09", "m10"})\n    for r in rows:\n        print(f"{r[\'month\']}: P={r[\'precision\']:.4f} R={r[\'recall\']:.4f} "\n              f"F1={r[\'f1\']:.4f} dupes {r[\'dupes_caught\']}/{r[\'dupes_truth\']}")\n    print(f"HOLDOUT OVERALL: P={overall[\'precision\']:.4f} "\n          f"R={overall[\'recall\']:.4f} (bar: P>={P_BAR}, R>={R_BAR})")\n    if overall["precision"] < P_BAR or overall["recall"] < R_BAR:\n        print("EVAL GATE: FAIL")\n        sys.exit(1)\n    print("EVAL GATE: PASS")\n\n\nif __name__ == "__main__":\n    main()\n'


SCAFFOLD = ["setup_milaan.py", "add_week2.py", "add_week3a.py", "add_week4.py",
            "add_webapp.py", "fix_gemini_auth.py", "fix_gemini_rotation.py",
            "fix_byline.py", "fix_review_issues.py"]


def main():
    for rel, content in FILES.items():
        path = rel.replace("/", os.sep)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        print(f"  wrote: {rel}")

    dev = os.path.join("scripts", "dev")
    os.makedirs(dev, exist_ok=True)
    moved, removed = 0, 0
    # move root copies of scaffolding into scripts/dev, delete stray duplicates
    for name in SCAFFOLD:
        root_copy = name
        dev_copy = os.path.join(dev, name)
        if os.path.exists(root_copy):
            if os.path.exists(dev_copy):
                os.remove(root_copy)
                removed += 1
                print(f"  removed duplicate: {root_copy}")
            else:
                shutil.move(root_copy, dev_copy)
                moved += 1
                print(f"  moved: {root_copy} -> scripts/dev/")
        # duplicates hiding inside the package dir
        pkg_copy = os.path.join("milaan", name)
        if os.path.exists(pkg_copy):
            os.remove(pkg_copy)
            removed += 1
            print(f"  removed duplicate: {pkg_copy}")
    # stray outputs at root
    if os.path.exists("student_preds.jsonl"):
        os.makedirs("eval_artifacts", exist_ok=True)
        shutil.move("student_preds.jsonl", os.path.join("eval_artifacts", "student_preds.jsonl"))
        print("  moved: student_preds.jsonl -> eval_artifacts/")

    print(f"\nDone. {moved} scripts moved, {removed} duplicates removed.")
    print("""
NEXT STEPS
  1. python -m pytest                     (30 passed)
  2. python scripts/ci_eval_gate.py       (EVAL GATE: PASS)
  3. Commit as THREE separate commits (reviewer point about history):
       a) "docs: honest results framing + exact teacher baseline"
       b) "ci: pytest + holdout eval gate on every push"
       c) "chore: move scaffolding to scripts/dev, remove duplicates"
  4. Push. Then check github.com -> Actions tab: the workflow should run and go green.
""")


if __name__ == "__main__":
    main()
