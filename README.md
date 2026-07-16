# MilaanAI — UPI/Bank-Statement Reconciliation Agent for Indian CA Firms

**Deterministic where money is counted. ML only where judgment is needed. Everything measured.**

Small CA firms reconcile client bank statements against ledgers by hand — 2-4
hours per client per month, with mismatches slipping through. MilaanAI reads
the bank statement (HDFC/ICICI/SBI) and the ledger, matches everything it can
prove, categorizes what's left, explains each exception with evidence, and
hands the accountant an Excel report with only the items needing human eyes.

## Results

| Component | Metric | Result |
|---|---|---|
| Matching engine (deterministic) | Pair precision / recall on held-out ground truth | **1.000 / 1.000** |
| Fine-tuned categorizer (Qwen2.5-3B + LoRA) | Accuracy, 1,000-sample held-out test | **99.8%** (998/1000) |
| Teacher baseline (gemini-flash-lite, prompted) | Accuracy, 300-sample test | **~97%** <!-- TODO: exact from eval-cat --> |
| Typical client month | Auto-matched bank lines | **94%+**, ~4 lines for human review |

The fine-tuned 3B **student beats the prompted frontier teacher** — at zero
inference cost, runnable locally. Its only errors (2/1000) are UPI credits
from person-named payers, the one case that's ambiguous to humans too.

## Architecture

```
bank.pdf/csv + ledger.csv ─▶ [Ingest + balance-integrity firewall]
        ─▶ [Matching engine: 4 deterministic tiers, full audit trail]
matched ────────────────────────────────────────────┐
unmatched ─▶ [Fine-tuned categorizer] ─▶ [Exception agent] ─▶ Excel report
                                    all measured by ─▶ [Eval harness vs planted ground truth]
```

- **No ML in the money path.** Matches come only from rule-based passes
  (exact → combined-settlement → split-payment → fee/short tolerance); every
  match records a rule-ID, score, and human-readable explanation.
- **Balance-integrity firewall:** if opening + Σtransactions ≠ closing, the
  run halts — parse errors never reach matching.
- **Ground truth by construction:** the synthetic data generator plants
  labeled discrepancies (gateway fees, short payments, duplicates,
  combined/split settlements), so precision/recall are exact, not estimated.
- **Distillation:** a frontier LLM teaches, a LoRA-tuned Qwen2.5-3B learns,
  and the eval harness grades both on the same held-out exam.

## Quickstart

```
pip install -r requirements.txt
python -m pytest                                   # 30 tests, no API keys needed
python cli.py generate --months 10 --out data/synth
python cli.py reconcile --statement data/synth/m01/statement_hdfc.csv \
    --ledger data/synth/m01/ledger.csv --out outputs/report.xlsx
python cli.py eval --months m08,m09,m10            # holdout metrics
```

Fine-tuning pipeline: `python cli.py finetune-data`, then the Colab notebook
in `notebooks/`, then `python cli.py eval-cat --preds student_preds.jsonl`.

## Repo map

```
milaan/generator/   synthetic statements + ledgers with planted ground truth
milaan/ingest/      HDFC/ICICI/SBI adapters + balance-integrity check
milaan/match/       deterministic 4-tier matching engine
milaan/finetune/    dataset generator, teacher labeling, category eval
milaan/report/      Excel exception report
milaan/evalx/       matching eval harness
notebooks/          Colab fine-tuning + prediction notebooks
```

Built by Ekta Mishra. Week-by-week build log and PRD in `docs/`.
