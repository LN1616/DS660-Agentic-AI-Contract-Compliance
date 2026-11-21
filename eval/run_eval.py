"""Step 8 - Compare baseline (single call) vs agent on CUAD contracts.

What CUAD can grade automatically:
  presence  - did the system say MISSING (or the rule's if_absent status) exactly when CUAD has no clause?
  faithful  - for findings that quote the contract, is the quote really in the PDF?
Plus time and cost from the trace.

Usage:  python -m eval.run_eval  [number_of_contracts] [--systems B2,A1] [--out DIR]
        --out keeps rows, reports and traces of one run together (used by eval.run_versions for repeated runs).
"""
import argparse
import time
from pathlib import Path

import pandas as pd

from src import config
from src.agent import review
from src.baseline import review_single_call
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace
from eval.cuad import expected_status, pdf_path
from eval.offline_check import DEV_SET


def grade(report, fname, rules, system, sec, totals):
    by_id = {r.finding.policy_id: r for r in report.findings}
    rows = []
    for rule in rules:
        exp = expected_status(fname, rule)
        r = by_id.get(rule["id"])
        pred = r.finding.compliance_status if r else "NONE"
        # Presence is only gradable when "absent" has its own status (MISSING).
        if rule["if_absent"] == "MISSING":
            correct = ((exp == "PRESENT") != (pred == "MISSING")) if r else False
        else:
            correct = None
        quoted = bool(r and r.finding.extracted_text.strip())
        rows.append({"system": system, "contract": fname[:40], "rule": rule["id"], "expected": exp, "predicted": pred,
                     "presence_correct": correct, "quoted": quoted,
                     "quote_real": (r.quote_score or 0) >= 88 if quoted else None,
                     "steps": r.steps if r else None, "rejections": r.rejections if r else None,
                     # trajectory exists from V3 on; older versions only have tool_calls
                     "repeats": sum(e.get("event") == "repeat" for e in getattr(r, "trajectory", [])) if r else None,
                     "no_new": sum(e.get("event") == "no_new" for e in getattr(r, "trajectory", [])) if r else None,
                     "tool_calls": "|".join(r.tool_calls) if r else ""})
    for row in rows:
        row.update(sec=sec / len(rows), cost_usd=totals["cost_usd"] / len(rows))
    return rows


def main(n: int, systems=("B2 single call", "A1 agent"), out=None, long: bool = False):
    if out:  # one folder per run: rows, full reports and traces
        config.OUTPUT_DIR = Path(out)
        config.TRACE_DIR = Path(out) / "traces"
        config.TRACE_DIR.mkdir(parents=True, exist_ok=True)
    rules = config.load_playbook()
    rows = []
    if long:  # test 22: the n longest CUAD contracts (75-154 pages), long Windows paths
        from eval.long_offline_check import LP, longest
        files = longest(n)
    else:
        LP, files = "", DEV_SET[:n]
    for fname in files:
        pdf = pdf_path(fname)
        pdf = Path(LP + str(pdf.resolve())) if LP else pdf
        doc = ContractDocument(pdf.stem, extract_pages(pdf, use_vision=False))
        for system in systems:
            doc.reset()
            trace = Trace(f"eval_{system[:2]}_{pdf.stem[:20]}")
            t0 = time.time()
            rep = review_single_call(pdf, doc, rules, trace) if system.startswith("B2") else review(doc, rules, trace)
            rows += grade(rep, fname, rules, system, time.time() - t0, trace.totals)
            trace.save()
            rep_dir = config.OUTPUT_DIR / "eval_reports"  # full reports (quotes included) for checking failures
            rep_dir.mkdir(parents=True, exist_ok=True)
            (rep_dir / f"{system[:2]}_{pdf.stem[:30]}.json").write_text(rep.model_dump_json(indent=2), encoding="utf-8")
            print(f"done {system:<15} {fname[:50]}")
    df = pd.DataFrame(rows)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.OUTPUT_DIR / "eval_rows.csv", index=False)
    summary = df.groupby("system").agg(
        presence_accuracy=("presence_correct", lambda s: s.dropna().astype(float).mean()),
        quote_faithfulness=("quote_real", lambda s: s.dropna().mean()),
        sec_per_contract=("sec", lambda s: s.sum() / n),
        usd_per_contract=("cost_usd", lambda s: s.sum() / n),
    ).round(3)
    summary.to_csv(config.OUTPUT_DIR / "eval_summary.csv")
    print("\n", summary.to_string())


SYSTEMS = {"B2": "B2 single call", "A1": "A1 agent"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=len(DEV_SET))
    ap.add_argument("--systems", default="B2,A1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--long", action="store_true", help="the n longest CUAD contracts instead of the short dev set")
    a = ap.parse_args()
    main(a.n, tuple(SYSTEMS[x] for x in a.systems.split(",")), a.out, a.long)
