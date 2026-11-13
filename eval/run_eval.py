"""Step 8 - Compare baseline (single call) vs agent on CUAD contracts.

What CUAD can grade automatically:
  presence  - did the system say MISSING (or the rule's if_absent status) exactly when CUAD has no clause?
  faithful  - for findings that quote the contract, is the quote really in the PDF?
Plus time and cost from the trace.

Usage:  python -m eval.run_eval  [number_of_contracts]
"""
import sys
import time

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
                     "quote_real": (r.quote_score or 0) >= 88 if quoted else None})
    for row in rows:
        row.update(sec=sec / len(rows), cost_usd=totals["cost_usd"] / len(rows))
    return rows


def main(n: int):
    rules = config.load_playbook()
    rows = []
    for fname in DEV_SET[:n]:
        pdf = pdf_path(fname)
        doc = ContractDocument(pdf.stem, extract_pages(pdf, use_vision=False))
        for system in ("B2 single call", "A1 agent"):
            doc.reset()
            trace = Trace(f"eval_{system[:2]}_{pdf.stem[:20]}")
            t0 = time.time()
            rep = review_single_call(pdf, doc, rules, trace) if system.startswith("B2") else review(doc, rules, trace)
            rows += grade(rep, fname, rules, system, time.time() - t0, trace.totals)
            trace.save()
            print(f"done {system:<15} {fname[:50]}")
    df = pd.DataFrame(rows)
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(config.OUTPUT_DIR / "eval_rows.csv", index=False)
    summary = df.groupby("system").agg(
        presence_accuracy=("presence_correct", lambda s: s.dropna().astype(float).mean()),
        quote_faithfulness=("quote_real", lambda s: s.dropna().mean()),
        sec_per_contract=("sec", lambda s: s.sum() / n),
        usd_per_contract=("cost_usd", lambda s: s.sum() / n),
    ).round(3)
    summary.to_csv(config.OUTPUT_DIR / "eval_summary.csv")
    print("\n", summary.to_string())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else len(DEV_SET))
