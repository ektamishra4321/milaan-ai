"""Fine-tuning dataset generator: (narration, amount, direction) -> category.

Richer than the reconciliation generator on purpose:
- hundreds of combinatorial business/person names (so the model learns
  patterns, not a fixed name list)
- multiple narration templates per category, real-bank style
- deterministic, split-hygienic (no narration string appears in two splits)

Output JSONL rows: {"text": "...", "category": "...", "narration": "...",
                    "amount": float, "direction": "credit|debit"}
`text` is the exact model input: "DIR=credit | AMT=45210 | NARR=UPI-..."
"""

import json
import random
from pathlib import Path

SURNAMES = ["Sharma", "Patel", "Gupta", "Verma", "Iyer", "Khan", "Mehta",
            "Reddy", "Joshi", "Bansal", "Nair", "Chawla", "Desai", "Kulkarni",
            "Sinha", "Agarwal", "Mishra", "Yadav", "Rathi", "Bhatt", "Pillai",
            "Ghosh", "Das", "Chopra", "Malhotra", "Saxena", "Trivedi", "Shah"]
BIZ_TYPES = ["Traders", "Enterprises", "Textiles", "Electronics", "Distributors",
             "Brothers", "Marketing", "Agencies", "Fabrics", "Steel", "Foods",
             "Motors", "Ceramics", "Papers", "Polymers", "Sweets", "Packaging",
             "Logistics", "Transport", "Stationers", "Printers", "Chemicals",
             "Wholesale", "Suppliers", "Industries", "Exports", "Hardware"]
FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikas", "Pooja", "Rohan",
               "Neha", "Arjun", "Kavita", "Sanjay", "Divya", "Manish", "Anita",
               "Deepak", "Ritu", "Suresh", "Meena", "Ajay", "Swati"]
VPA_BANKS = ["okhdfcbank", "oksbi", "okicici", "ybl", "paytm", "ibl", "axl"]
UTILITIES = ["MSEDCL", "TATA POWER", "ADANI ELEC", "BEST UNDERT", "AIRTEL",
             "JIO FIBER", "MAHANAGAR GAS", "BWSSB WATER"]
LENDERS = ["BAJAJ FINANCE", "HDFC BANK LOAN", "ICICI PL", "TATA CAPITAL",
           "FULLERTON", "AXIS LOAN"]
INSURERS = ["LIC OF INDIA", "HDFC ERGO", "ICICI LOMBARD", "STAR HEALTH",
            "SBI LIFE", "MAX LIFE"]


def _vowel_drop(s):
    return " ".join(w[0] + "".join(c for c in w[1:] if c not in "AEIOU")
                    if len(w) > 4 else w for w in s.split())


def _mangle(name, rng):
    up = name.upper()
    return rng.choice([up, up, _vowel_drop(up), up[:rng.randint(8, 14)].strip()])


def _rrn(rng):
    return str(rng.randint(10**11, 10**12 - 1))


def _utr(rng):
    return f"N{rng.randint(10**8, 10**9 - 1)}"


def _biz(rng):
    return f"{rng.choice(SURNAMES)} {rng.choice(BIZ_TYPES)}"


def _person(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"


def _vpa(name, rng):
    return f"{name.lower().split()[0][:8]}{rng.randint(1, 99)}@{rng.choice(VPA_BANKS)}"


# --------------------------------------------------------------- per-category
def _sales_receipt(rng):
    p = _biz(rng)
    d = _mangle(p, rng)
    mode = rng.choice(["UPI", "UPI", "IMPS", "NEFT", "RTGS", "CHQ"])
    if mode == "UPI":
        n = f"UPI-{d}-{_vpa(p, rng)}-{_rrn(rng)}-{rng.choice(['PAYMENT', 'INV PAYMENT', 'COLLECT'])}"
    elif mode == "IMPS":
        n = f"IMPS-{_rrn(rng)}-{d}"
    elif mode == "NEFT":
        n = f"NEFT CR-{_utr(rng)}-{d}"
    elif mode == "RTGS":
        n = f"RTGS-R{_utr(rng)[1:]}-{d}"
    else:
        n = f"CHQ DEP-{rng.randint(100000, 999999)}-{d}"
    return n, float(rng.randint(1500, 250000)), "credit"


def _vendor_payment(rng):
    p = _biz(rng)
    d = _mangle(p, rng)
    mode = rng.choice(["UPI", "NEFT", "IMPS", "RTGS"])
    if mode == "UPI":
        n = f"UPI-{d}-{_vpa(p, rng)}-{_rrn(rng)}-{rng.choice(['PAYMENT', 'PURCHASE', 'BILL PMT'])}"
    elif mode == "NEFT":
        n = f"NEFT DR-{_utr(rng)}-{d}"
    elif mode == "IMPS":
        n = f"IMPS-{_rrn(rng)}-{d}"
    else:
        n = f"RTGS-R{_utr(rng)[1:]}-{d}"
    return n, float(rng.randint(800, 180000)), "debit"


def _salary(rng):
    who = rng.choice(["STAFF PAYROLL", "SALARY " + rng.choice(
        ["JUL", "AUG", "SEP", "OCT", "JAN", "FEB", "MAR"]),
        _person(rng).upper() + " SAL"])
    return (f"NEFT DR-{_utr(rng)}-{who}" if rng.random() < 0.7
            else f"SAL-{who}-{_rrn(rng)[:8]}"), float(rng.randint(12000, 95000)), "debit"


def _rent(rng):
    m = rng.choice(["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])
    forms = [f"NEFT DR-{_utr(rng)}-OFFICE RENT {m}",
             f"RENT {m}-{_mangle(_person(rng), rng)}",
             f"UPI-{_mangle(_person(rng), rng)}-{_rrn(rng)}-SHOP RENT"]
    return rng.choice(forms), float(rng.randint(8000, 90000)), "debit"


def _bank_charges(rng):
    forms = ["SMS CHARGES " + rng.choice(["MAR", "JUN", "SEP", "DEC"]) + " QTR",
             "AMB CHRG INCL GST", "NEFT RETURN CHARGES GST",
             "CHQ BOOK ISSUE CHG", "DEBIT CARD AMC", "MIN BAL CHARGES",
             f"PROCESSING FEE-{_rrn(rng)[:6]}"]
    return rng.choice(forms), float(rng.choice([29, 59, 118, 177, 236, 354, 590])), "debit"


def _gst_tds(rng):
    forms = [f"GST PMT-{rng.randint(10**10, 10**11)}",
             f"GSTN PAYMENT {_rrn(rng)[:8]}",
             f"TDS PAYMENT CBDT-{rng.randint(10**7, 10**8)}",
             "EPAYMENT-CBIC-GST", f"ADVANCE TAX-{rng.randint(10**6, 10**7)}"]
    return rng.choice(forms), float(rng.randint(2000, 400000)), "debit"


def _loan_emi(rng):
    l = rng.choice(LENDERS)
    forms = [f"ACH D-{l}-EMI-{rng.randint(10**7, 10**8)}",
             f"NACH-{l}-{_rrn(rng)[:8]}",
             f"ECS-{l}-LOAN {rng.randint(10**5, 10**6)}"]
    return rng.choice(forms), float(rng.randint(3500, 60000)), "debit"


def _utility(rng):
    u = rng.choice(UTILITIES)
    forms = [f"BILLPAY-{u}-{rng.choice(['ELEC', 'BILL', 'RECHARGE'])}-{rng.randint(10**6, 10**7)}",
             f"BBPS-{u}-{_rrn(rng)[:8]}",
             f"UPI-{u}-{u.lower().split()[0]}@{rng.choice(VPA_BANKS)}-{_rrn(rng)}-BILL"]
    return rng.choice(forms), float(rng.randint(400, 18000)), "debit"


def _upi_p2p(rng):
    p = _person(rng)
    d = _mangle(p, rng)
    direction = rng.choice(["credit", "debit"])
    n = f"UPI-{d}-{_vpa(p, rng)}-{_rrn(rng)}-{rng.choice(['', 'SENT', 'PAYMENT', 'GPAY', 'PHONEPE'])}".rstrip("-")
    return n, float(rng.randint(100, 25000)), direction


def _refund(rng):
    src = rng.choice(["AMAZON", "FLIPKART", "MYNTRA", "SWIGGY", "ZOMATO",
                      "IRCTC", _biz(rng).upper()])
    forms = [f"REV-UPI-{_rrn(rng)}-{src}",
             f"REFUND-{src}-{_rrn(rng)[:8]}",
             f"UPI RET-{_rrn(rng)}-{src}",
             f"IMPS REV-{_rrn(rng)}-{_mangle(src, rng) if ' ' in src else src}"]
    return rng.choice(forms), float(rng.randint(99, 45000)), "credit"


def _interest(rng):
    return rng.choice(["INT.PD. SB ACCOUNT", "SB INT CREDIT",
                       f"FD INT-{rng.randint(10**6, 10**7)}",
                       "INTEREST CAPITALISED"]), float(rng.randint(50, 9000)), "credit"


def _cash_dep(rng):
    return rng.choice([f"CDM DEPOSIT-{rng.randint(10**5, 10**6)}",
                       "CASH DEP BY SELF", f"CSH DEP-BRANCH-{rng.randint(100, 999)}"]), \
        float(rng.randint(1000, 200000) // 100 * 100), "credit"


def _cash_wdl(rng):
    return rng.choice([f"ATM WDL-{rng.randint(10**5, 10**6)}-{rng.choice(['MUMBAI', 'PUNE', 'THANE', 'DELHI'])}",
                       "SELF CHQ WDL", f"NWD-{_rrn(rng)[:10]}"]), \
        float(rng.choice([500, 1000, 2000, 5000, 10000, 20000, 40000])), "debit"


def _insurance(rng):
    i = rng.choice(INSURERS)
    return rng.choice([f"ACH D-{i}-{rng.randint(10**7, 10**8)}",
                       f"NACH-{i}-PREMIUM",
                       f"BILLPAY-{i}-{_rrn(rng)[:8]}"]), \
        float(rng.randint(1500, 60000)), "debit"


def _other(rng):
    forms = [f"BY TRANSFER-{_rrn(rng)[:8]}", "SWEEP TRF TO FD",
             f"CLG-{rng.randint(10**5, 10**6)}", "DD ISSUE",
             f"POS {rng.randint(10**5, 10**6)} {rng.choice(['DMART', 'RELIANCE RETAIL', 'CROMA'])}"]
    return rng.choice(forms), float(rng.randint(200, 60000)), rng.choice(["credit", "debit"])


MAKERS = {
    "sales_receipt": _sales_receipt, "vendor_payment": _vendor_payment,
    "salary": _salary, "rent": _rent, "bank_charges": _bank_charges,
    "gst_tds_payment": _gst_tds, "loan_emi": _loan_emi,
    "utility_bill": _utility, "upi_p2p": _upi_p2p, "refund": _refund,
    "interest_credit": _interest, "cash_deposit": _cash_dep,
    "cash_withdrawal": _cash_wdl, "insurance": _insurance, "other": _other,
}

# sampling weights: frequent categories appear more, like real statements
WEIGHTS = {"sales_receipt": 22, "vendor_payment": 16, "upi_p2p": 10,
           "salary": 6, "rent": 5, "bank_charges": 6, "gst_tds_payment": 6,
           "loan_emi": 6, "utility_bill": 6, "refund": 5,
           "interest_credit": 3, "cash_deposit": 3, "cash_withdrawal": 3,
           "insurance": 4, "other": 3}


def to_text(narration, amount, direction):
    return f"DIR={direction} | AMT={int(amount)} | NARR={narration}"


def generate_dataset(out_dir, n_train=8000, n_val=1000, n_test=1000, seed=42):
    rng = random.Random(seed)
    cats = [c for c, w in WEIGHTS.items() for _ in range(w)]
    seen, rows = set(), []
    target = n_train + n_val + n_test
    while len(rows) < target:
        cat = rng.choice(cats)
        narration, amount, direction = MAKERS[cat](rng)
        text = to_text(narration, amount, direction)
        if text in seen:            # split hygiene: globally unique inputs
            continue
        seen.add(text)
        rows.append({"text": text, "category": cat, "narration": narration,
                     "amount": amount, "direction": direction})
    rng.shuffle(rows)
    splits = {"train": rows[:n_train],
              "val": rows[n_train:n_train + n_val],
              "test": rows[n_train + n_val:]}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, split in splits.items():
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in split:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {k: len(v) for k, v in splits.items()}
