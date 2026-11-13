"""Review one contract from the command line.

Examples:
  python run_review.py --cuad FUSION                 # agent on a CUAD contract (name contains FUSION)
  python run_review.py --cuad FUSION --baseline      # single-call baseline on the same contract
  python run_review.py path\\to\\contract.pdf
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from src import config
from src.agent import review
from src.baseline import review_single_call
from src.document import ContractDocument
from src.ingest import extract_pages
from src.report import save, to_frame
from src.trace import Trace


def find_cuad(fragment: str) -> Path:
    hits = [p for p in (config.CUAD_DIR / "full_contract_pdf").rglob("*")
            if p.suffix.lower() == ".pdf" and fragment.lower() in p.name.lower()]
    if not hits:
        sys.exit(f"No CUAD PDF name contains '{fragment}'")
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--cuad", help="part of a CUAD file name")
    ap.add_argument("--baseline", action="store_true", help="run the single-call baseline instead")
    ap.add_argument("--no-vision", action="store_true")
    a = ap.parse_args()
    pdf = find_cuad(a.cuad) if a.cuad else Path(a.pdf)
    mode = "baseline" if a.baseline else "agent"
    name = re.sub(r"[^A-Za-z0-9]+", "_", pdf.stem)[:40] + f"_{mode}"

    trace = Trace(name)
    doc = ContractDocument(pdf.stem, extract_pages(pdf, use_vision=not a.no_vision, trace=trace))
    rules = config.load_playbook()
    print(f"{pdf.name}\n{len(doc.pages)} pages, {len(doc.passages)} passages, {len(rules)} rules, mode={mode}\n")

    if a.baseline:
        report = review_single_call(pdf, doc, rules, trace)
    else:
        report = review(doc, rules, trace, on_step=lambda r: print(f"  checking {r['id']} {r['title']} ..."))

    pd.set_option("display.width", 160, "display.max_colwidth", 40)
    print("\n" + to_frame(report)[["policy", "category", "status", "risk", "reference", "verified", "steps", "sent_back"]].to_string(index=False))
    print(f"\nSummary: {report.executive_summary}\n\nCounts: {report.counts}\nCost/time: {trace.totals}")
    js, xlsx = save(report, config.OUTPUT_DIR, name)
    print(f"Saved {xlsx.name}, {js.name}, trace {trace.save().name}")


if __name__ == "__main__":
    main()
