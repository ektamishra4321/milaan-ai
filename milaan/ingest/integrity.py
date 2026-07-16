"""Balance-integrity check: the parse-error firewall.

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
