"""Realistic Indian bank narration builders + name pools.

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
