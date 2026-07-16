"""Tiered deterministic matching engine — the money path. No ML here.

Passes (in order, each consumes matched items):
  P1 EXACT     : same amount, direction-consistent, unique best name+date score
  P2 TOLERANCE : bank amount slightly below ledger (gateway fee / short payment)
  P3 COMBINED  : one bank credit settles 2-3 ledger invoices (same party)
  P4 SPLIT     : two bank credits settle one ledger invoice (same party)

Every match records: rule id, score, and a human-readable explanation.
Duplicate bank lines (same narration+ref+amount) are pre-flagged.
Determinism: stable sorts everywhere; same input -> identical output.
"""

from datetime import date
from itertools import combinations

from rapidfuzz import fuzz

# ---------------------------------------------------------------- tunables
DATE_BEFORE = 1        # bank may precede ledger by at most 1 day
DATE_AFTER = 7         # bank may lag ledger by up to 7 days
NAME_THRESHOLD = 70    # min fuzzy score to accept a name link
TOL_PCT = 0.12         # max fee/short-payment delta as fraction of ledger amt
TOL_ABS = 50.0         # plus small absolute buffer
GROUP_MAX = 3          # max invoices in a combined settlement
GROUP_AFTER = 31       # settlement may lag oldest invoice this many days

STOPWORDS = {"UPI", "IMPS", "NEFT", "RTGS", "CHQ", "DEP", "CR", "DR",
             "PAYMENT", "ACH", "D", "BILLPAY", "PMT", "REF", "TRF"}


def _vowel_drop(s: str) -> str:
    return " ".join(w[0] + "".join(c for c in w[1:] if c not in "AEIOU")
                    if len(w) > 4 else w for w in s.split())


def narration_hint(narration: str) -> str:
    """Strip mode prefixes, numbers, VPAs -> probable party text."""
    toks = []
    for raw in narration.upper().replace("/", "-").split("-"):
        for t in raw.split():
            if not t or t in STOPWORDS or "@" in t:
                continue
            if sum(c.isdigit() for c in t) > len(t) // 2:
                continue
            toks.append(t)
    return " ".join(toks)


def name_score(narration: str, party: str) -> float:
    hint = narration_hint(narration)
    if not hint:
        return 0.0
    p = party.upper()
    return max(fuzz.token_set_ratio(hint, p),
               fuzz.token_set_ratio(hint, _vowel_drop(p)),
               fuzz.partial_ratio(hint, p))


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def _date_ok(bank_date: str, ledger_date: str) -> bool:
    d = _days(bank_date, ledger_date)
    return -DATE_BEFORE <= d <= DATE_AFTER


def _date_ok_group(bank_date: str, ledger_date: str) -> bool:
    d = _days(bank_date, ledger_date)
    return -DATE_BEFORE <= d <= GROUP_AFTER


def _dir_ok(txn, entry) -> bool:
    return (txn.direction == "credit") == (entry.entry_type == "receipt")


def flag_duplicates(txns):
    """Same narration+ref+amount seen before -> later copies flagged."""
    seen, dupes = {}, {}
    for t in sorted(txns, key=lambda x: (x.date, x.txn_id)):
        key = (t.narration, t.ref, round(t.amount, 2))
        if key in seen:
            dupes[t.txn_id] = seen[key]
        else:
            seen[key] = t.txn_id
    return dupes  # dup_txn_id -> original_txn_id


def _greedy_assign(edges, bank_used, ledger_used):
    """edges: list of (score_tuple, txn, entry, rule, explanation).
    Higher score wins; each side used once. Deterministic tie-breaks."""
    matches = []
    for score, txn, entry, rule, expl in sorted(
            edges, key=lambda e: (-e[0][0], e[0][1], e[1].txn_id, e[2].entry_id)):
        if txn.txn_id in bank_used or entry.entry_id in ledger_used:
            continue
        bank_used.add(txn.txn_id)
        ledger_used.add(entry.entry_id)
        matches.append({"bank_ids": [txn.txn_id], "ledger_ids": [entry.entry_id],
                        "rule": rule, "score": round(score[0], 1),
                        "explanation": expl})
    return matches


def reconcile(txns, entries):
    bank_used, ledger_used = set(), set()
    matches = []

    dupes = flag_duplicates(txns)
    live_txns = [t for t in txns if t.txn_id not in dupes]

    # -------------------------------------------------- P1 exact amount
    edges = []
    for t in live_txns:
        for e in entries:
            if not _dir_ok(t, e) or abs(t.amount - e.amount) > 0.01:
                continue
            if not _date_ok(t.date, e.date):
                continue
            ns = name_score(t.narration, e.party)
            gap = abs(_days(t.date, e.date))
            edges.append(((ns + (7 - gap), gap), t, e, "P1_EXACT",
                          f"exact amount {t.amount:,.2f}; name score {ns:.0f}; "
                          f"date gap {gap}d"))
    matches += _greedy_assign(edges, bank_used, ledger_used)

    # -------------------------------------------------- P3 combined (N ledger -> 1 bank)
    open_receipts = [e for e in entries
                     if e.entry_id not in ledger_used and e.entry_type == "receipt"]
    by_party = {}
    for e in open_receipts:
        by_party.setdefault(e.party, []).append(e)
    for t in sorted(live_txns, key=lambda x: (x.date, x.txn_id)):
        if t.txn_id in bank_used or t.direction != "credit":
            continue
        best = None
        for party, group in sorted(by_party.items()):
            cands = [e for e in group if e.entry_id not in ledger_used
                     and _date_ok_group(t.date, e.date)
                     and name_score(t.narration, party) >= NAME_THRESHOLD]
            for r in (2, GROUP_MAX):
                for combo in combinations(sorted(cands, key=lambda e: e.entry_id), r):
                    if abs(sum(e.amount for e in combo) - t.amount) <= 0.01:
                        best = combo
                        break
                if best:
                    break
            if best:
                break
        if best:
            bank_used.add(t.txn_id)
            for e in best:
                ledger_used.add(e.entry_id)
            invs = ", ".join(e.invoice_no or e.entry_id for e in best)
            matches.append({"bank_ids": [t.txn_id],
                            "ledger_ids": [e.entry_id for e in best],
                            "rule": "P3_COMBINED", "score": 100.0,
                            "explanation": f"one credit {t.amount:,.2f} settles "
                                           f"{len(best)} invoices ({invs})"})

    # -------------------------------------------------- P4 split (2 bank -> 1 ledger)
    open_credits = [t for t in live_txns
                    if t.txn_id not in bank_used and t.direction == "credit"]
    for e in sorted(entries, key=lambda x: (x.date, x.entry_id)):
        if e.entry_id in ledger_used or e.entry_type != "receipt":
            continue
        cands = [t for t in open_credits if t.txn_id not in bank_used
                 and _date_ok_group(t.date, e.date)
                 and name_score(t.narration, e.party) >= NAME_THRESHOLD]
        found = None
        for combo in combinations(sorted(cands, key=lambda t: t.txn_id), 2):
            if abs(sum(t.amount for t in combo) - e.amount) <= 0.01:
                found = combo
                break
        if found:
            ledger_used.add(e.entry_id)
            for t in found:
                bank_used.add(t.txn_id)
            matches.append({"bank_ids": [t.txn_id for t in found],
                            "ledger_ids": [e.entry_id], "rule": "P4_SPLIT",
                            "score": 100.0,
                            "explanation": f"invoice {e.invoice_no or e.entry_id} "
                                           f"({e.amount:,.2f}) paid in 2 parts"})

    # -------------------------------------------------- P2 fee/short tolerance
    edges = []
    for t in live_txns:
        if t.txn_id in bank_used:
            continue
        for e in entries:
            if e.entry_id in ledger_used or not _dir_ok(t, e):
                continue
            delta = e.amount - t.amount
            if delta <= 0.01 or delta > e.amount * TOL_PCT + TOL_ABS:
                continue
            if not _date_ok(t.date, e.date):
                continue
            ns = name_score(t.narration, e.party)
            if ns < NAME_THRESHOLD:
                continue
            pct = delta / e.amount
            kind = "gateway fee" if pct <= 0.025 else "short payment"
            edges.append(((ns - pct * 100, abs(_days(t.date, e.date))), t, e,
                          "P2_TOLERANCE",
                          f"amount short by {delta:,.2f} ({pct:.2%}) — likely "
                          f"{kind}; name score {ns:.0f}"))
    matches += _greedy_assign(edges, bank_used, ledger_used)

    # -------------------------------------------------- leftovers + near misses
    unmatched_bank = []
    for t in txns:
        if t.txn_id in bank_used:
            continue
        if t.txn_id in dupes:
            unmatched_bank.append({"bank_id": t.txn_id,
                                   "suspect": "DUPLICATE",
                                   "duplicate_of": dupes[t.txn_id]})
            continue
        near = sorted(
            ({"entry_id": e.entry_id, "party": e.party,
              "amount": e.amount, "delta": round(e.amount - t.amount, 2),
              "name_score": round(name_score(t.narration, e.party), 0)}
             for e in entries if e.entry_id not in ledger_used
             and _dir_ok(t, e) and _date_ok(t.date, e.date)),
            key=lambda c: (abs(c["delta"]), -c["name_score"]))[:3]
        unmatched_bank.append({"bank_id": t.txn_id, "suspect": None,
                               "near_misses": near})

    unmatched_ledger = [{"ledger_id": e.entry_id}
                        for e in entries if e.entry_id not in ledger_used]

    return {"matches": matches, "unmatched_bank": unmatched_bank,
            "unmatched_ledger": unmatched_ledger}
