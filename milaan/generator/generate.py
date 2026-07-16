"""Synthetic client-month generator with planted, labeled discrepancies.

Produces, per client-month:
  ledger.csv          — what the business recorded
  statement.<fmt>.csv — what the bank saw (HDFC/ICICI/SBI column format)
  ground_truth.json   — the perfect answer key (matches, discrepancies, categories)

Discrepancy types planted (each labeled in ground truth):
  CLEAN              — normal 1:1 match (majority)
  GATEWAY_FEE        — bank credit = invoice - 1..2.36% fee
  SHORT_PAYMENT      — customer paid less, no fee logic
  TIMING             — bank date lags ledger date by 2-5 days
  DUPLICATE_BANK     — same bank line appears twice
  MISSING_LEDGER     — bank line with no ledger entry (unrecorded income/expense)
  PAYMENT_NOT_RECEIVED — ledger receipt with no bank line
  COMBINED           — 2-3 invoices settled by ONE bank credit
  SPLIT              — 1 invoice settled by TWO bank credits
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

from milaan.models import BankTxn, LedgerEntry
from milaan.generator.narrations import (CUSTOMERS, VENDORS, FIXED_NARRATIONS,
                                         make_narration, truncate_name)

MODES = ["UPI", "UPI", "UPI", "IMPS", "NEFT", "RTGS", "CHQ"]  # UPI-weighted

# scenario mix for customer receipts
RECEIPT_SCENARIOS = (
    ["CLEAN"] * 62 + ["GATEWAY_FEE"] * 8 + ["SHORT_PAYMENT"] * 5 +
    ["TIMING"] * 8 + ["DUPLICATE_BANK"] * 3 + ["PAYMENT_NOT_RECEIVED"] * 4 +
    ["COMBINED"] * 6 + ["SPLIT"] * 4
)


def _amount(rng, lo=1500, hi=95000):
    base = rng.randint(lo, hi)
    return float(base - base % 10 + rng.choice([0, 0, 0, 118, 250, 500]))


def generate_month(seed: int, year: int, month: int, n_invoices: int = 45):
    rng = random.Random(seed)
    start = date(year, month, 1)
    days = 28

    ledger, bank_raw, gt_matches = [], [], []
    gt_unmatched_bank, gt_unmatched_ledger, categories = [], [], {}
    lid, bid = [0], [0]

    def next_l():
        lid[0] += 1
        return f"L{lid[0]:04d}"

    def next_b():
        bid[0] += 1
        return f"B{bid[0]:04d}"

    def dt(offset):
        return (start + timedelta(days=max(0, min(days - 1, offset)))).isoformat()

    def add_bank(day, narr, ref, amount, direction, category):
        t = BankTxn(next_b(), dt(day), narr, ref, round(amount, 2), direction, 0.0)
        bank_raw.append(t)
        categories[t.txn_id] = category
        return t

    # ---------------- customer invoice receipts (the interesting part)
    combined_pool = []
    for _ in range(n_invoices):
        cust = rng.choice(CUSTOMERS)
        amt = _amount(rng)
        day = rng.randint(0, days - 4)
        inv = f"INV-{rng.randint(1000, 9999)}"
        le = LedgerEntry(next_l(), dt(day), cust, f"Sales invoice {inv}", inv, amt, "receipt")
        ledger.append(le)
        scenario = rng.choice(RECEIPT_SCENARIOS)
        mode = rng.choice(MODES)
        narr, ref = make_narration(mode, cust, rng)

        if scenario == "COMBINED":
            combined_pool.append(le)
            if len(combined_pool) >= rng.choice([2, 2, 3]):
                group, combined_pool = combined_pool, []
                same_cust = group[0].party
                for g in group:
                    g.party = same_cust  # combined settlements come from one payer
                total = sum(g.amount for g in group)
                gday = max(int(g.date[-2:]) for g in group)  # after last invoice
                narr2, ref2 = make_narration(rng.choice(["NEFT", "RTGS"]), same_cust, rng)
                bt = add_bank(gday - 1 + rng.randint(1, 3), narr2, ref2, total,
                              "credit", "sales_receipt")
                gt_matches.append({"bank_ids": [bt.txn_id],
                                   "ledger_ids": [g.entry_id for g in group],
                                   "type": "COMBINED", "note": f"{len(group)} invoices, one settlement"})
            continue

        if scenario == "SPLIT":
            part1 = round(amt * rng.uniform(0.3, 0.7), 2)
            part2 = round(amt - part1, 2)
            b1 = add_bank(day + rng.randint(0, 2), narr, ref, part1, "credit", "sales_receipt")
            narr2, ref2 = make_narration(mode, cust, rng)
            b2 = add_bank(day + rng.randint(2, 5), narr2, ref2, part2, "credit", "sales_receipt")
            gt_matches.append({"bank_ids": [b1.txn_id, b2.txn_id],
                               "ledger_ids": [le.entry_id],
                               "type": "SPLIT", "note": "invoice paid in two parts"})
            continue

        if scenario == "PAYMENT_NOT_RECEIVED":
            gt_unmatched_ledger.append({"ledger_id": le.entry_id,
                                        "reason": "PAYMENT_NOT_RECEIVED"})
            continue

        if scenario == "GATEWAY_FEE":
            fee_pct = rng.choice([0.01, 0.0118, 0.02, 0.0236])
            credited = round(amt * (1 - fee_pct), 2)
            bt = add_bank(day + rng.randint(0, 2), narr, ref, credited, "credit", "sales_receipt")
            gt_matches.append({"bank_ids": [bt.txn_id], "ledger_ids": [le.entry_id],
                               "type": "GATEWAY_FEE",
                               "note": f"fee {fee_pct:.2%} deducted at source"})
            continue

        if scenario == "SHORT_PAYMENT":
            credited = round(amt - rng.choice([100, 118, 500, 1000, amt * 0.1]), 2)
            bt = add_bank(day + rng.randint(0, 2), narr, ref, credited, "credit", "sales_receipt")
            gt_matches.append({"bank_ids": [bt.txn_id], "ledger_ids": [le.entry_id],
                               "type": "SHORT_PAYMENT", "note": "customer short-paid"})
            continue

        lag = rng.randint(2, 5) if scenario == "TIMING" else rng.randint(0, 1)
        bt = add_bank(day + lag, narr, ref, amt, "credit", "sales_receipt")
        gt_matches.append({"bank_ids": [bt.txn_id], "ledger_ids": [le.entry_id],
                           "type": "TIMING" if scenario == "TIMING" else "CLEAN",
                           "note": f"bank lag {lag}d" if scenario == "TIMING" else ""})
        if scenario == "DUPLICATE_BANK":
            dup = add_bank(int(bt.date[-2:]) - 1, bt.narration, bt.ref, bt.amount,
                           "credit", "sales_receipt")
            gt_unmatched_bank.append({"bank_id": dup.txn_id, "reason": "DUPLICATE_BANK",
                                      "duplicate_of": bt.txn_id})

    # leftover combined pool -> clean matches
    for g in combined_pool:
        narr, ref = make_narration(rng.choice(MODES), g.party, rng)
        bt = add_bank(int(g.date[-2:]) - 1 + rng.randint(0, 2), narr, ref, g.amount,
                      "credit", "sales_receipt")
        gt_matches.append({"bank_ids": [bt.txn_id], "ledger_ids": [g.entry_id],
                           "type": "CLEAN", "note": ""})

    # ---------------- vendor payments (mostly clean, some unrecorded)
    for _ in range(rng.randint(8, 12)):
        vend = rng.choice(VENDORS)
        amt = _amount(rng, 800, 40000)
        day = rng.randint(0, days - 2)
        narr, ref = make_narration(rng.choice(MODES), vend, rng)
        bt = add_bank(day + rng.randint(0, 1), narr, ref, amt, "debit", "vendor_payment")
        if rng.random() < 0.12:
            gt_unmatched_bank.append({"bank_id": bt.txn_id, "reason": "MISSING_LEDGER"})
        else:
            le = LedgerEntry(next_l(), dt(day), vend, f"Purchase - {vend}",
                             "", amt, "payment")
            ledger.append(le)
            gt_matches.append({"bank_ids": [bt.txn_id], "ledger_ids": [le.entry_id],
                               "type": "CLEAN", "note": ""})

    # ---------------- fixed monthly items (ledger + bank, clean)
    fixed = [("salary", 5, _amount(rng, 40000, 90000), "debit", "Staff Payroll"),
             ("rent", 3, _amount(rng, 18000, 45000), "debit", "Landlord"),
             ("gst_tds_payment", 19, _amount(rng, 5000, 60000), "debit", "GSTN"),
             ("loan_emi", 7, _amount(rng, 8000, 25000), "debit", "Bajaj Finance"),
             ("utility_bill", 11, _amount(rng, 1500, 9000), "debit", "MSEDCL"),
             ("insurance", 14, _amount(rng, 2000, 12000), "debit", "LIC of India")]
    for cat, day, amt, direction, party in fixed:
        narr, ref = FIXED_NARRATIONS[cat](rng)
        bt = add_bank(day, narr, ref, amt, direction, cat)
        le = LedgerEntry(next_l(), dt(day), party, cat.replace("_", " ").title(),
                         "", amt, "payment")
        ledger.append(le)
        gt_matches.append({"bank_ids": [bt.txn_id], "ledger_ids": [le.entry_id],
                           "type": "CLEAN", "note": ""})

    # bank-only items: charges + interest (no ledger entry — MISSING_LEDGER)
    for cat, day, amt, direction in [("bank_charges", 24, rng.choice([59.0, 118.0, 236.0]), "debit"),
                                     ("interest_credit", 27, float(rng.randint(80, 900)), "credit")]:
        narr, ref = FIXED_NARRATIONS[cat](rng)
        bt = add_bank(day, narr, ref, amt, direction, cat)
        gt_unmatched_bank.append({"bank_id": bt.txn_id, "reason": "MISSING_LEDGER"})

    # ---------------- running balance
    bank_raw.sort(key=lambda t: (t.date, t.txn_id))
    # Re-assign IDs in file order so adapters (which number rows top-to-bottom)
    # produce IDs identical to ground truth.
    remap = {}
    for i, t in enumerate(bank_raw, 1):
        remap[t.txn_id] = f"B{i:04d}"
        t.txn_id = f"B{i:04d}"
    for m in gt_matches:
        m["bank_ids"] = [remap[b] for b in m["bank_ids"]]
    for u in gt_unmatched_bank:
        u["bank_id"] = remap[u["bank_id"]]
        if "duplicate_of" in u:
            u["duplicate_of"] = remap[u["duplicate_of"]]
    categories = {remap[k]: v for k, v in categories.items()}
    opening = float(rng.randint(150000, 800000))
    bal = opening
    for t in bank_raw:
        bal += t.amount if t.direction == "credit" else -t.amount
        t.balance_after = round(bal, 2)
    ledger.sort(key=lambda e: (e.date, e.entry_id))

    ground_truth = {
        "seed": seed, "opening_balance": opening,
        "closing_balance": round(bal, 2),
        "matches": gt_matches,
        "unmatched_bank": gt_unmatched_bank,
        "unmatched_ledger": gt_unmatched_ledger,
        "categories": categories,
    }
    return bank_raw, ledger, ground_truth


def write_month(out_dir: str, fmt: str, bank, ledger, gt):
    from milaan.generator.formats import write_statement, write_ledger
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_statement(out / f"statement_{fmt}.csv", fmt, bank,
                    gt["opening_balance"])
    write_ledger(out / "ledger.csv", ledger)
    (out / "ground_truth.json").write_text(
        json.dumps(gt, indent=2), encoding="utf-8")
