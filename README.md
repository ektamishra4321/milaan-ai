# MilaanAI — UPI/Bank-Statement Reconciliation Agent for Indian CA Firms

🔴 **Live demo:** https://milaan-ai.onrender.com

**Deterministic where money is counted. ML only where judgment is needed. Everything measured — with the caveats stated.**

Small CA firms reconcile client bank statements against ledgers by hand — 2-4 hours
per client per month. MilaanAI parses the statement (HDFC/ICICI/SBI), matches every
transaction it can prove, categorizes the rest with a fine-tuned local model, and
outputs an Excel exception report with only the items needing human review.

## Results — and what they do and don't show

| Component | Measured on | Result | Caveat |
|---|---|---|---|
| Matching engine (deterministic) | Held-out **synthetic** months (m08-m10) | P 1.000 / R 1.000 | In-distribution: the generator and matcher were written by the same author, so treat this as an upper bound, not field performance. CI enforces the PRD bar (P≥0.98, R≥0.90) on every push. **Real-data pilot pending.** |
| Fine-tuned categorizer — Qwen2.5-3B + LoRA | 1,000-sample held-out test | **99.8%** (998/1000) | Test set is synthetic narrations; both errors are person-named UPI credits — the genuinely ambiguous class. |
| Teacher baseline — gemini-flash-lite, prompted | 300-sample test, same distribution | **97.0%** (291/300) | Same exam, same answer key. The fine-tuned student beats the prompted teacher in-distribution, at ₹0 inference. |
| Typical synthetic client month | ~69 bank lines | 94.2% auto-matched | ~4 lines left for human review. |

**Known limitation, stated upfront:** all current numbers come from synthetic data with
planted, labeled discrepancies. That makes precision/recall *exact* rather than estimated —
but it does not prove real-world performance. Validating on one anonymized real client
month with a CA is the next milestone; adapters for real statement exports are built for
exactly the three formats the generator mimics.

## Why the eval harness is the point

The first end-to-end run scored **1% precision** — the harness caught a real ID-mapping
bug between generator and adapter. Iterating against measured numbers (1% → 99.8% → 100%
in identified, explainable steps, including reordering exact-sum passes above tolerance
passes after diagnosing a false match) is the working method this repo demonstrates.
Every push re-runs the gate in CI.

## Architecture

```
bank.csv + ledger.csv ─▶ [Ingest + balance-integrity firewall]
        ─▶ [Matching engine: 4 deterministic tiers, rule-ID + explanation per match]
matched ──────────────────────────────────────────────┐
unmatched ─▶ [Fine-tuned categorizer] ─▶ [Report: Excel exceptions]
                          everything ─▶ [Eval harness vs planted ground truth, gated in CI]
```

- **No ML in the money path.** Matches come only from rule-based passes; every match
  carries a rule-ID, score, and plain-language explanation.
- **Balance-integrity firewall:** opening + Σtxns must equal closing, per row, or the
  run halts before matching.
- **Distillation:** frontier LLM as teacher, LoRA-tuned Qwen2.5-3B as student, both
  graded on the same held-out exam.

## Quickstart

```
pip install -r requirements.txt
python -m pytest                                  # 30 deterministic tests, no API keys
python cli.py generate --months 10 --out data/synth
python cli.py reconcile --statement data/synth/m01/statement_hdfc.csv \
    --ledger data/synth/m01/ledger.csv --out outputs/report.xlsx
python scripts/ci_eval_gate.py                    # the same gate CI runs
python webapp.py                                  # live demo at 127.0.0.1:5000
```

## Repo map

```
milaan/            engine: generator, adapters, matcher, finetune, report, eval
scripts/           ci_eval_gate.py (CI gate) · dev/ (build-time scaffolding scripts)
notebooks/         Colab fine-tuning + prediction notebooks
tests/             30 deterministic tests
webapp.py          Flask live demo (deterministic path, no keys needed)
.github/workflows/ CI: pytest + holdout eval gate on every push
```

Built by Ekta Mishra, 2026. PRD and build notes in `docs/`.
