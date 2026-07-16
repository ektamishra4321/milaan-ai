"""Week 4 tests — categorizer wiring (offline-safe)."""

from milaan.models import BankTxn
import milaan.categorize as cz


def test_categorize_offline_fallback(monkeypatch):
    def boom(*a, **k):
        raise cz.LLMError("no network")
    monkeypatch.setattr(cz, "complete_json", boom)
    txns = [BankTxn(f"B{i:04d}", "2026-07-01", "SMS CHARGES", "", 59.0,
                    "debit", 0.0) for i in range(3)]
    out = cz.categorize_txns(txns)
    assert all(v == "uncategorized" for v in out.values())
    assert set(out.keys()) == {"B0000", "B0001", "B0002"}


def test_categorize_parses_and_validates(monkeypatch):
    monkeypatch.setattr(cz, "complete_json",
                        lambda *a, **k: {"0": "bank_charges", "1": "not_a_cat"})
    txns = [BankTxn("B0001", "2026-07-01", "SMS CHARGES", "", 59.0, "debit", 0.0),
            BankTxn("B0002", "2026-07-01", "XYZ", "", 10.0, "debit", 0.0)]
    out = cz.categorize_txns(txns)
    assert out["B0001"] == "bank_charges"
    assert out["B0002"] == "uncategorized"
