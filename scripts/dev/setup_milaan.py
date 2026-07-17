"""
setup_milaan.py — Week 1 scaffold for MilaanAI (UPI/Bank Reconciliation Agent)

Usage (Windows):
    1. Put this file inside your empty project folder (e.g. milaan-ai)
    2. python setup_milaan.py
    3. Follow the printed next steps.

Never overwrites existing files unless you pass --force.
"""

import os
import sys

FILES = {}

FILES["requirements.txt"] = """pandas>=2.0
pytest>=8.0
python-dotenv>=1.0
rapidfuzz>=3.0
openpyxl>=3.1
"""

FILES[".gitignore"] = """.env
__pycache__/
*.pyc
data/
outputs/
logs/
.venv/
venv/
"""

# ============================================================ models.py
FILES["milaan/__init__.py"] = ""

FILES["milaan/models.py"] = '''"""Normalized data schema used across MilaanAI.

Every bank adapter must produce this exact shape, so the matching engine
(Week 2) never sees bank-specific quirks.
"""

from dataclasses import dataclass, field, asdict


@dataclass
class BankTxn:
    txn_id: str            # e.g. "B0042"
    date: str              # ISO "YYYY-MM-DD"
    narration: str
    ref: str               # cheque / UTR / RRN reference ("" if none)
    amount: float          # always positive
    direction: str         # "credit" | "debit"
    balance_after: float

    def to_dict(self):
        return asdict(self)


@dataclass
class LedgerEntry:
    entry_id: str          # e.g. "L0017"
    date: str              # ISO
    party: str
    description: str
    invoice_no: str        # "" if none
    amount: float          # always positive
    entry_type: str        # "receipt" (money expected in) | "payment" (out)

    def to_dict(self):
        return asdict(self)


CATEGORIES = [
    "sales_receipt", "vendor_payment", "salary", "rent", "bank_charges",
    "gst_tds_payment", "loan_emi", "utility_bill", "upi_p2p", "refund",
    "interest_credit", "cash_deposit", "cash_withdrawal", "insurance", "other",
]
'''

# ============================================================ generator/narrations.py
FILES["milaan/generator/__init__.py"] = ""

FILES["milaan/generator/narrations.py"] = '''"""Realistic Indian bank narration builders + name pools.

Narrations mimic real HDFC/ICICI/SBI strings: UPI/IMPS/NEFT prefixes, RRN
numbers, truncated party names ("SHARMA TRADERS" -> "SHRMA TRDRS").
"""

import random

CUSTOMERS = [
    "Sharma Traders", "Patel Enterprises", "Gupta Textiles", "Verma Electronics",
    "Iyer Distributors", "Khan Brothers", "Mehta Marketing", "Reddy Agencies",
    "Joshi Fabrics", "Bansal Steel", "Nair Foods", "Chawla Motors",
    "Desai Ceramics", "Kulkarni Papers", "Sinha Polymers", "Agarwal Sweets",
]

VENDORS = [
    "Balaji Packaging", "Om Logistics", "Shree Ram Transport", "Neha Stationers",
    "Galaxy Printers", "Sunrise Chemicals", "Metro Wholesale", "Anand Suppliers",
]

VPA_BANKS = ["okhdfcbank", "oksbi", "okicici", "ybl", "paytm", "ibl"]


def truncate_name(name: str, rng: random.Random) -> str:
    """Simulate bank truncation/vowel-dropping: 'Sharma Traders' -> 'SHRMA TRDRS'."""
    up = name.upper()
    style = rng.choice(["full", "vowel_drop", "cut"])
    if style == "full":
        return up
    if style == "cut":
        return up[: rng.randint(8, 14)].strip()
    words = []
    for w in up.split():
        if len(w) > 4:
            w = w[0] + "".join(c for c in w[1:] if c not in "AEIOU")
        words.append(w)
    return " ".join(words)


def vpa_for(name: str, rng: random.Random) -> str:
    handle = name.lower().split()[0][:8] + str(rng.randint(1, 99))
    return f"{handle}@{rng.choice(VPA_BANKS)}"


def rrn(rng: random.Random) -> str:
    return str(rng.randint(10**11, 10**12 - 1))


def utr(rng: random.Random) -> str:
    return f"N{rng.randint(10**8, 10**9 - 1)}"


def make_narration(mode: str, party: str, rng: random.Random) -> tuple:
    """Returns (narration, ref) for a payment mode."""
    disp = truncate_name(party, rng)
    if mode == "UPI":
        r = rrn(rng)
        return f"UPI-{disp}-{vpa_for(party, rng)}-{r}-PAYMENT", r
    if mode == "IMPS":
        r = rrn(rng)
        return f"IMPS-{r}-{disp}", r
    if mode == "NEFT":
        u = utr(rng)
        return f"NEFT CR-{u}-{disp}", u
    if mode == "RTGS":
        u = "R" + utr(rng)[1:]
        return f"RTGS-{u}-{disp}", u
    if mode == "CHQ":
        c = str(rng.randint(100000, 999999))
        return f"CHQ DEP-{c}-{disp}", c
    return disp, ""


FIXED_NARRATIONS = {
    "salary":          lambda rng: (f"NEFT DR-SALARY-{utr(rng)}-STAFF PAYROLL", utr(rng)),
    "rent":            lambda rng: (f"NEFT DR-{utr(rng)}-OFFICE RENT JUL", utr(rng)),
    "bank_charges":    lambda rng: ("SMS CHARGES JUN QTR" if rng.random() < 0.5
                                    else "NEFT RETURN CHARGES GST", ""),
    "gst_tds_payment": lambda rng: (f"GST PMT-{rng.randint(10**10, 10**11)}", ""),
    "loan_emi":        lambda rng: (f"ACH D-BAJAJ FINANCE-EMI-{rng.randint(10**7, 10**8)}", ""),
    "utility_bill":    lambda rng: (f"BILLPAY-MSEDCL-ELEC-{rng.randint(10**6, 10**7)}", ""),
    "interest_credit": lambda rng: ("INT.PD. SB ACCOUNT", ""),
    "insurance":       lambda rng: (f"ACH D-LIC OF INDIA-{rng.randint(10**7, 10**8)}", ""),
}
'''

# ============================================================ generator/generate.py
FILES["milaan/generator/generate.py"] = r'''"""Synthetic client-month generator with planted, labeled discrepancies.

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
'''

# ============================================================ generator/formats.py
FILES["milaan/generator/formats.py"] = r'''"""Bank-specific CSV writers. Each mimics the real export's columns,
date format and debit/credit convention — so our ingestion adapters
(milaan/ingest/adapters.py) have something honest to parse.

HDFC : Date DD/MM/YY | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
ICICI: S No.|Value Date DD-MM-YYYY|Transaction Date|Cheque Number|Transaction Remarks|Withdrawal Amount (INR )|Deposit Amount (INR )|Balance (INR )
SBI  : Txn Date DD Mon YYYY|Value Date|Description|Ref No./Cheque No.|Debit|Credit|Balance
"""

import csv
from datetime import date


def _d(iso: str) -> date:
    return date.fromisoformat(iso)


def _fmt_amount(x: float) -> str:
    return f"{x:,.2f}"


def write_ledger(path, ledger):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entry_id", "date", "party", "description",
                    "invoice_no", "amount", "entry_type"])
        for e in ledger:
            w.writerow([e.entry_id, e.date, e.party, e.description,
                        e.invoice_no, f"{e.amount:.2f}", e.entry_type])


def write_statement(path, fmt, txns, opening):
    fmt = fmt.lower()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if fmt == "hdfc":
            w.writerow(["Date", "Narration", "Chq./Ref.No.", "Value Dt",
                        "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"])
            w.writerow(["", "OPENING BALANCE", "", "", "", "", _fmt_amount(opening)])
            for t in txns:
                d = _d(t.date).strftime("%d/%m/%y")
                wd = _fmt_amount(t.amount) if t.direction == "debit" else ""
                dp = _fmt_amount(t.amount) if t.direction == "credit" else ""
                w.writerow([d, t.narration, t.ref, d, wd, dp,
                            _fmt_amount(t.balance_after)])
        elif fmt == "icici":
            w.writerow(["S No.", "Value Date", "Transaction Date", "Cheque Number",
                        "Transaction Remarks", "Withdrawal Amount (INR )",
                        "Deposit Amount (INR )", "Balance (INR )"])
            for i, t in enumerate(txns, 1):
                d = _d(t.date).strftime("%d-%m-%Y")
                wd = f"{t.amount:.2f}" if t.direction == "debit" else "0.00"
                dp = f"{t.amount:.2f}" if t.direction == "credit" else "0.00"
                w.writerow([i, d, d, t.ref if "CHQ" in t.narration else "",
                            t.narration, wd, dp, f"{t.balance_after:.2f}"])
        elif fmt == "sbi":
            w.writerow(["Txn Date", "Value Date", "Description",
                        "Ref No./Cheque No.", "Debit", "Credit", "Balance"])
            for t in txns:
                d = _d(t.date).strftime("%d %b %Y")
                db = _fmt_amount(t.amount) if t.direction == "debit" else " "
                cr = _fmt_amount(t.amount) if t.direction == "credit" else " "
                w.writerow([d, d, t.narration, t.ref or " ", db, cr,
                            _fmt_amount(t.balance_after)])
        else:
            raise ValueError(f"Unknown format: {fmt}")
'''

# ============================================================ ingest
FILES["milaan/ingest/__init__.py"] = ""

FILES["milaan/ingest/adapters.py"] = r'''"""Ingestion adapters: bank-format CSV -> list[BankTxn] (normalized schema).

Auto-detects the format from the header row. Each adapter handles that
bank's date format, amount commas, and debit/credit column convention.
"""

import csv
from datetime import datetime

from milaan.models import BankTxn, LedgerEntry


def _amt(s: str) -> float:
    s = (s or "").replace(",", "").strip()
    return float(s) if s else 0.0


def _detect(header: list) -> str:
    joined = "|".join(h.strip().lower() for h in header)
    if "narration" in joined and "closing balance" in joined:
        return "hdfc"
    if "transaction remarks" in joined:
        return "icici"
    if "txn date" in joined and "description" in joined:
        return "sbi"
    raise ValueError(f"Unrecognized statement format. Header: {header}")


def parse_statement(path: str):
    """Returns (txns, opening_balance_or_None, fmt)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    fmt = _detect(header)
    txns, opening, n = [], None, 0

    for row in body:
        if not any(cell.strip() for cell in row):
            continue
        if fmt == "hdfc":
            if "OPENING BALANCE" in row[1].upper():
                opening = _amt(row[6])
                continue
            d = datetime.strptime(row[0].strip(), "%d/%m/%y").date().isoformat()
            wd, dp = _amt(row[4]), _amt(row[5])
            n += 1
            txns.append(BankTxn(f"B{n:04d}", d, row[1].strip(), row[2].strip(),
                                wd or dp, "debit" if wd else "credit", _amt(row[6])))
        elif fmt == "icici":
            d = datetime.strptime(row[1].strip(), "%d-%m-%Y").date().isoformat()
            wd, dp = _amt(row[5]), _amt(row[6])
            n += 1
            txns.append(BankTxn(f"B{n:04d}", d, row[4].strip(), row[3].strip(),
                                wd or dp, "debit" if wd else "credit", _amt(row[7])))
        elif fmt == "sbi":
            d = datetime.strptime(row[0].strip(), "%d %b %Y").date().isoformat()
            db, cr = _amt(row[4]), _amt(row[5])
            n += 1
            txns.append(BankTxn(f"B{n:04d}", d, row[2].strip(), row[3].strip(),
                                db or cr, "debit" if db else "credit", _amt(row[6])))
    return txns, opening, fmt


def parse_ledger(path: str):
    entries = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            entries.append(LedgerEntry(
                row["entry_id"].strip(), row["date"].strip(), row["party"].strip(),
                row["description"].strip(), row["invoice_no"].strip(),
                float(row["amount"]), row["entry_type"].strip()))
    return entries
'''

FILES["milaan/ingest/integrity.py"] = '''"""Balance-integrity check: the parse-error firewall.

If opening balance + sum(signed txns) != closing balance, something was
misparsed — halt before bad data reaches the matching engine.
Also verifies each row's running balance when the format provides it.
"""


class IntegrityError(Exception):
    pass


def check_balance(txns, opening, tolerance=0.01):
    if opening is None:
        if not txns:
            raise IntegrityError("Empty statement")
        first = txns[0]
        delta = first.amount if first.direction == "credit" else -first.amount
        opening = round(first.balance_after - delta, 2)

    bal = opening
    for t in txns:
        bal += t.amount if t.direction == "credit" else -t.amount
        if abs(bal - t.balance_after) > tolerance:
            raise IntegrityError(
                f"Running balance mismatch at {t.txn_id} ({t.date}): "
                f"computed {bal:.2f} vs statement {t.balance_after:.2f}. "
                "Likely a misparsed amount or missing row."
            )
    return {"opening": round(opening, 2), "closing": round(bal, 2),
            "n_txns": len(txns), "ok": True}
'''

# ============================================================ cli.py
FILES["cli.py"] = r'''"""MilaanAI CLI (Week 1).

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

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
'''

# ============================================================ tests
FILES["tests/test_week1.py"] = r'''"""Week 1 tests — generator, adapters, integrity. No network, no keys."""

import json

import pytest

from milaan.generator.generate import generate_month, write_month
from milaan.generator.narrations import truncate_name
from milaan.ingest.adapters import parse_statement, parse_ledger
from milaan.ingest.integrity import check_balance, IntegrityError

import random


# ------------------------------------------------------------ generator
def test_generator_deterministic():
    a = generate_month(seed=7, year=2026, month=3)
    b = generate_month(seed=7, year=2026, month=3)
    assert json.dumps(a[2], sort_keys=True) == json.dumps(b[2], sort_keys=True)


def test_running_balance_consistent():
    bank, _, gt = generate_month(seed=11, year=2026, month=1)
    bal = gt["opening_balance"]
    for t in bank:
        bal += t.amount if t.direction == "credit" else -t.amount
        assert abs(bal - t.balance_after) < 0.01
    assert abs(bal - gt["closing_balance"]) < 0.01


def test_ground_truth_ids_exist():
    bank, ledger, gt = generate_month(seed=5, year=2026, month=2)
    bank_ids = {t.txn_id for t in bank}
    ledger_ids = {e.entry_id for e in ledger}
    for m in gt["matches"]:
        assert set(m["bank_ids"]) <= bank_ids
        assert set(m["ledger_ids"]) <= ledger_ids
    for u in gt["unmatched_bank"]:
        assert u["bank_id"] in bank_ids
    for u in gt["unmatched_ledger"]:
        assert u["ledger_id"] in ledger_ids


def test_every_bank_txn_accounted_exactly_once():
    bank, _, gt = generate_month(seed=13, year=2026, month=4)
    seen = []
    for m in gt["matches"]:
        seen += m["bank_ids"]
    seen += [u["bank_id"] for u in gt["unmatched_bank"]]
    assert sorted(seen) == sorted(t.txn_id for t in bank)


def test_every_ledger_entry_accounted_exactly_once():
    _, ledger, gt = generate_month(seed=13, year=2026, month=4)
    seen = []
    for m in gt["matches"]:
        seen += m["ledger_ids"]
    seen += [u["ledger_id"] for u in gt["unmatched_ledger"]]
    assert sorted(seen) == sorted(e.entry_id for e in ledger)


def test_discrepancy_variety_planted():
    types = set()
    for seed in range(20, 26):
        _, _, gt = generate_month(seed=seed, year=2026, month=5)
        types |= {m["type"] for m in gt["matches"]}
        types |= {u["reason"] for u in gt["unmatched_bank"]}
        types |= {u["reason"] for u in gt["unmatched_ledger"]}
    for expected in ["CLEAN", "GATEWAY_FEE", "SHORT_PAYMENT", "COMBINED",
                     "SPLIT", "DUPLICATE_BANK", "MISSING_LEDGER",
                     "PAYMENT_NOT_RECEIVED", "TIMING"]:
        assert expected in types, f"{expected} never planted across seeds"


def test_categories_cover_all_bank_txns():
    bank, _, gt = generate_month(seed=9, year=2026, month=6)
    assert set(gt["categories"].keys()) == {t.txn_id for t in bank}


def test_truncate_name_variants():
    rng = random.Random(1)
    outs = {truncate_name("Sharma Traders", rng) for _ in range(30)}
    assert "SHARMA TRADERS" in outs          # full form appears
    assert any(o != "SHARMA TRADERS" for o in outs)  # and mangled forms too


# ------------------------------------------------------------ round-trip
@pytest.mark.parametrize("fmt", ["hdfc", "icici", "sbi"])
def test_roundtrip_all_formats(tmp_path, fmt):
    bank, ledger, gt = generate_month(seed=31, year=2026, month=7)
    write_month(str(tmp_path), fmt, bank, ledger, gt)
    txns, opening, detected = parse_statement(str(tmp_path / f"statement_{fmt}.csv"))
    assert detected == fmt
    assert len(txns) == len(bank)
    for orig, parsed in zip(bank, txns):
        assert parsed.date == orig.date
        assert abs(parsed.amount - orig.amount) < 0.01
        assert parsed.direction == orig.direction
    report = check_balance(txns, opening if opening is not None else gt["opening_balance"])
    assert report["ok"]
    entries = parse_ledger(str(tmp_path / "ledger.csv"))
    assert len(entries) == len(ledger)


# ------------------------------------------------------------ integrity
def test_integrity_catches_corruption(tmp_path):
    bank, ledger, gt = generate_month(seed=17, year=2026, month=8)
    write_month(str(tmp_path), "hdfc", bank, ledger, gt)
    txns, opening, _ = parse_statement(str(tmp_path / "statement_hdfc.csv"))
    txns[10].amount += 5000.0  # simulate a misparse
    with pytest.raises(IntegrityError):
        check_balance(txns, opening)


def test_integrity_infers_missing_opening():
    bank, _, gt = generate_month(seed=19, year=2026, month=9)
    report = check_balance(bank, None)
    assert abs(report["opening"] - gt["opening_balance"]) < 0.01
'''

# ============================================================ README
FILES["README.md"] = """# MilaanAI — UPI/Bank-Statement Reconciliation Agent

Deterministic where money is counted, ML only where judgment is needed — and
everything measured against planted ground truth.

## Week 1 (this scaffold)
- Synthetic client-month generator: paired bank statement + ledger with
  **planted, labeled discrepancies** (gateway fees, short payments, duplicates,
  combined/split settlements, timing lags, unrecorded items)
- Bank format adapters: HDFC / ICICI / SBI CSV → one normalized schema
- Balance-integrity firewall: opening + Σtxns must equal closing, per-row

## Quickstart
```
pip install -r requirements.txt
pytest
python cli.py generate --months 10 --out data/synth
python cli.py ingest --statement data/synth/m01/statement_hdfc.csv --ledger data/synth/m01/ledger.csv
```
Months m08–m10 are HOLDOUT — never tune against them.

## Coming next
Week 2: tiered matching engine + exception report + eval harness.
Week 3: LoRA fine-tuned Qwen2.5-3B categorizer (distilled from frontier labels).
Week 4: real CA pilot on anonymized data.
"""


def main():
    force = "--force" in sys.argv
    created, skipped = 0, 0
    for rel_path, content in FILES.items():
        path = os.path.join(os.getcwd(), rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.exists(path) and not force:
            skipped += 1
            print(f"  skip (exists): {rel_path}")
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        created += 1
        print(f"  created: {rel_path}")

    for d in ("data", "outputs", "logs"):
        os.makedirs(os.path.join(os.getcwd(), d), exist_ok=True)

    print(f"\nDone. {created} files created, {skipped} skipped.")
    print("""
NEXT STEPS
  1. pip install -r requirements.txt
  2. pytest                      (expect 15+ passed, no keys needed)
  3. python cli.py generate --months 10 --out data/synth
  4. python cli.py ingest --statement data/synth/m01/statement_hdfc.csv --ledger data/synth/m01/ledger.csv
  5. Open data/synth/m01/ in Excel — check the statement looks like a real bank export
""")


if __name__ == "__main__":
    main()
