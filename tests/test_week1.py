"""Week 1 tests — generator, adapters, integrity. No network, no keys."""

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
