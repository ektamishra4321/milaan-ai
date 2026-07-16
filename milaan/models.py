"""Normalized data schema used across MilaanAI.

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
