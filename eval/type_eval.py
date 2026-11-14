"""Contract-type detection accuracy against CUAD's own grouping.

CUAD v1 stores its 510 PDFs in folders named by contract type (Part_I/II/III/<type>/).
The folder is the ground truth. We take up to N contracts per type (fixed seed),
run criteria.profile_contract and compare its contract_type with the folder.

Run:  python -m eval.type_eval --per-type 2
Writes outputs/type_eval_rows.csv and prints accuracy + the confusions.
"""
import argparse
import csv
import os
import random
import re
from collections import defaultdict
from pathlib import Path

import yaml

from src import config
from src.criteria import TYPE_TH, profile_contract
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace


def canonical(folder: str) -> str:
    """Merge CUAD folder spellings across parts, e.g. 'Affiliate_Agreements' / 'Affiliate Agreement' -> Affiliate."""
    name = re.sub(r"\s+", " ", folder.replace("_", " ")).strip()
    name = re.sub(r"(?i)\s*(agreements?|filing)$", "", name).strip()
    special = {"Co Branding": "Co-Branding", "Non Compete Non Solicit": "Non-Compete / Non-Solicit"}
    name = special.get(name, name)
    if name not in TYPE_TH:
        raise ValueError(f"Unknown CUAD folder: {folder}")
    return name


def cuad_by_type() -> dict[str, list]:
    root = config.CUAD_DIR / "full_contract_pdf"
    out = defaultdict(list)
    for part in sorted(root.glob("Part_*")):
        for d in sorted(p for p in part.iterdir() if p.is_dir()):
            out[canonical(d.name)] += sorted(f for f in d.rglob("*") if f.suffix.lower() == ".pdf")
    return out


def main(per_type: int, seed: int = 42):
    rules = config.load_playbook()
    rng = random.Random(seed)
    rows, trace = [], Trace("type_eval")
    for ctype, files in sorted(cuad_by_type().items()):
        for pdf in rng.sample(files, min(per_type, len(files))):
            try:
                long_path = Path("\\\\?\\" + str(pdf.resolve())) if os.name == "nt" else pdf  # CUAD paths pass 260 chars
                doc = ContractDocument(pdf.stem, extract_pages(long_path, use_vision=False))
                pred = profile_contract(doc, rules, trace, "en").contract_type
            except Exception as e:
                pred = f"ERROR {type(e).__name__}"
            rows.append({"file": pdf.name, "truth": ctype, "predicted": pred, "correct": pred == ctype})
            print(f"{'✓' if pred == ctype else '✕'} {ctype:<26} -> {pred:<26} {pdf.name[:60]}", flush=True)
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    out = config.OUTPUT_DIR / "type_eval_rows.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    scored = [r for r in rows if not r["predicted"].startswith("ERROR")]
    n = len(scored)
    acc = sum(r["correct"] for r in scored) / n
    print(f"\nAccuracy {acc:.0%} ({sum(r['correct'] for r in scored)}/{n}, {len(rows) - n} unreadable) · {trace.totals}")
    conf = defaultdict(int)
    for r in rows:
        if not r["correct"]:
            conf[(r["truth"], r["predicted"])] += 1
    for (a, b), k in sorted(conf.items(), key=lambda x: -x[1]):
        print(f"  {a} -> {b}: {k}")
    trace.save()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=2)
    main(ap.parse_args().per_type)
