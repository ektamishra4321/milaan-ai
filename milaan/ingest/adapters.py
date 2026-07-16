"""Ingestion adapters: bank-format CSV -> list[BankTxn] (normalized schema).

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
