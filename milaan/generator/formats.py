"""Bank-specific CSV writers. Each mimics the real export's columns,
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
