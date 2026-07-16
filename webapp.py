"""MilaanAI web app — the live demo behind the landing page.

Endpoints:
  GET  /                      landing page with live-demo panel
  POST /api/reconcile         multipart upload: statement + ledger CSV -> JSON summary + report id
  GET  /api/sample            run the bundled sample month -> same JSON
  GET  /download/<rid>        the generated Excel report
  GET  /sample/<name>         download the sample input CSVs to inspect

Design notes:
- Engine is fully deterministic: no API keys needed for the demo path.
- Uploads capped at 2 MB, CSV only. Reports live in a temp dir, pruned after an hour.
- The balance-integrity firewall's error is surfaced verbatim: it's a feature.
"""

import json
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from milaan.generator.generate import generate_month, write_month
from milaan.ingest.adapters import parse_statement, parse_ledger
from milaan.ingest.integrity import check_balance, IntegrityError
from milaan.match.engine import reconcile
from milaan.report.excel import write_report

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB

TMP = Path("outputs/webapp")
SAMPLE_DIR = Path("data/webapp_sample")


def _ensure_sample():
    if not (SAMPLE_DIR / "ledger.csv").exists():
        bank, ledger, gt = generate_month(seed=4242, year=2026, month=7)
        write_month(str(SAMPLE_DIR), "hdfc", bank, ledger, gt)
_ensure_sample()


def _prune():
    TMP.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 3600
    for f in TMP.glob("*.xlsx"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def _run(statement_path: str, ledger_path: str, label: str):
    txns, opening, fmt = parse_statement(statement_path)
    integrity = check_balance(txns, opening)
    entries = parse_ledger(ledger_path)
    result = reconcile(txns, entries)

    _prune()
    rid = uuid.uuid4().hex[:12]
    out = TMP / f"{rid}.xlsx"
    write_report(str(out), result, txns, entries,
                 meta={"Statement": label, "Format": fmt.upper()})

    n_bank = len(txns)
    n_matched = sum(len(m["bank_ids"]) for m in result["matches"])
    dupes = sum(1 for u in result["unmatched_bank"]
                if u.get("suspect") == "DUPLICATE")
    interesting = [
        {"rule": m["rule"], "explanation": m["explanation"]}
        for m in result["matches"] if m["rule"] != "P1_EXACT"
    ][:6]
    return {
        "ok": True,
        "format": fmt.upper(),
        "bank_txns": n_bank,
        "ledger_entries": len(entries),
        "matched": n_matched,
        "match_pct": round(100 * n_matched / max(n_bank, 1), 1),
        "match_groups": len(result["matches"]),
        "review_bank": len(result["unmatched_bank"]) - dupes,
        "review_ledger": len(result["unmatched_ledger"]),
        "duplicates": dupes,
        "opening": integrity["opening"],
        "closing": integrity["closing"],
        "interesting": interesting,
        "report_id": rid,
    }


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/reconcile")
def api_reconcile():
    stmt = request.files.get("statement")
    ledg = request.files.get("ledger")
    if not stmt or not ledg:
        return jsonify(ok=False, error="Upload both files: a bank statement CSV "
                                        "and a ledger CSV."), 400
    for f in (stmt, ledg):
        if not (f.filename or "").lower().endswith(".csv"):
            return jsonify(ok=False, error=f"'{f.filename}' is not a .csv file. "
                           "Export your statement as CSV first."), 400
    TMP.mkdir(parents=True, exist_ok=True)
    sp = TMP / f"in_{uuid.uuid4().hex[:8]}_s.csv"
    lp = TMP / f"in_{uuid.uuid4().hex[:8]}_l.csv"
    stmt.save(sp)
    ledg.save(lp)
    try:
        return jsonify(_run(str(sp), str(lp), stmt.filename))
    except IntegrityError as e:
        return jsonify(ok=False, error=f"Balance-integrity firewall halted the "
                       f"run: {e}"), 422
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 422
    except Exception:
        return jsonify(ok=False, error="Could not parse these files. Supported: "
                       "HDFC/ICICI/SBI statement CSV + MilaanAI ledger CSV "
                       "(see the sample files)."), 422
    finally:
        sp.unlink(missing_ok=True)
        lp.unlink(missing_ok=True)


@app.get("/api/sample")
def api_sample():
    stmt = next(SAMPLE_DIR.glob("statement_*.csv"))
    return jsonify(_run(str(stmt), str(SAMPLE_DIR / "ledger.csv"),
                        "sample client month (synthetic)"))


@app.get("/download/<rid>")
def download(rid):
    safe = "".join(c for c in rid if c.isalnum())
    path = TMP / f"{safe}.xlsx"
    if not path.exists():
        return "Report expired — run the demo again.", 404
    return send_file(path, as_attachment=True,
                     download_name="milaan_reconciliation_report.xlsx")


@app.get("/sample/<name>")
def sample_file(name):
    if name not in ("statement", "ledger"):
        return "Not found", 404
    path = (next(SAMPLE_DIR.glob("statement_*.csv")) if name == "statement"
            else SAMPLE_DIR / "ledger.csv")
    return send_file(path, as_attachment=True, download_name=f"sample_{name}.csv")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
