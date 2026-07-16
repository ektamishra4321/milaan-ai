"""Week 3a tests — fine-tune dataset + teacher eval logic. No keys."""

import json

from milaan.finetune.datagen import generate_dataset, MAKERS, to_text
from milaan.finetune.teacher import evaluate_predictions
from milaan.models import CATEGORIES

import random


def test_all_categories_have_makers():
    assert set(MAKERS.keys()) == set(CATEGORIES)


def test_dataset_splits_and_hygiene(tmp_path):
    counts = generate_dataset(str(tmp_path), n_train=800, n_val=100,
                              n_test=100, seed=7)
    assert counts == {"train": 800, "val": 100, "test": 100}
    seen = set()
    for split in ("train", "val", "test"):
        for l in open(tmp_path / f"{split}.jsonl", encoding="utf-8"):
            r = json.loads(l)
            assert r["text"] not in seen, "leakage between splits"
            seen.add(r["text"])
            assert r["category"] in CATEGORIES
            assert r["direction"] in ("credit", "debit")


def test_dataset_deterministic(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    generate_dataset(str(a), 200, 50, 50, seed=3)
    generate_dataset(str(b), 200, 50, 50, seed=3)
    assert (a / "train.jsonl").read_text() == (b / "train.jsonl").read_text()


def test_makers_direction_sanity():
    rng = random.Random(1)
    for _ in range(50):
        assert MAKERS["sales_receipt"](rng)[2] == "credit"
        assert MAKERS["vendor_payment"](rng)[2] == "debit"
        assert MAKERS["refund"](rng)[2] == "credit"
        assert MAKERS["cash_withdrawal"](rng)[2] == "debit"


def test_evaluate_predictions(tmp_path):
    test_f = tmp_path / "test.jsonl"; pred_f = tmp_path / "preds.jsonl"
    rows = [{"text": to_text(f"N{i}", 100, "debit"), "category": "rent",
             "narration": f"N{i}", "amount": 100, "direction": "debit"}
            for i in range(10)]
    test_f.write_text("\n".join(json.dumps(r) for r in rows))
    preds = [{"text": r["text"], "pred": "rent" if i < 8 else "salary"}
             for i, r in enumerate(rows)]
    pred_f.write_text("\n".join(json.dumps(p) for p in preds))
    rep = evaluate_predictions(str(test_f), str(pred_f))
    assert rep["n"] == 10 and rep["accuracy"] == 0.8
    assert rep["top_confusions"][0][0] == ("rent", "salary")
