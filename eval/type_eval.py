"""Contract-type detection accuracy against CUAD's own grouping.

CUAD v1 stores its 510 PDFs in folders named by contract type (Part_I/II/III/<type>/).
The folder is the ground truth. We take up to N contracts per type (fixed seed),
run criteria.profile_contract and compare its contract_type with the folder.

Run:  python -m eval.type_eval --per-type 2      # the 50-contract test (API: title rule + model fallback)
      python -m eval.type_eval --offline         # title rule only, all 510 contracts, no API
Writes outputs/type_eval_rows.csv (or type_eval_offline.csv) and prints accuracy + the confusions.
type_source per row: "title" = the code rule decided from the title · "ai" = the model judged it.
"""
import argparse
import csv
import os
import random
import re
from collections import defaultdict
from pathlib import Path

from src import config
from src.criteria import TYPE_TH, find_title, profile_contract, type_from_title
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


def long_path(pdf: Path) -> Path:
    return Path("\\\\?\\" + str(pdf.resolve())) if os.name == "nt" else pdf  # CUAD paths pass 260 chars


def offline():
    """Title rule on every CUAD contract: first two pages only, no API, no cost."""
    import pdfplumber
    rows = []
    for ctype, files in sorted(cuad_by_type().items()):
        for pdf in files:
            with pdfplumber.open(long_path(pdf)) as d:
                text = "\n".join((pg.extract_text() or "") for pg in d.pages[:2])
            title = find_title(text)
            pred = type_from_title(title) if title else None
            rows.append({"file": pdf.name, "truth": ctype, "title": title, "predicted": pred or "-",
                         "correct": pred == ctype})
    out = config.OUTPUT_DIR / "type_eval_offline.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    dec = [r for r in rows if r["predicted"] != "-"]
    ok = sum(r["correct"] for r in dec)
    print(f"Title rule decided {len(dec)}/{len(rows)} · correct {ok}/{len(dec)} ({ok / len(dec):.1%}) · "
          f"{len(rows) - len(dec)} left to the model · {out}")
    for r in rows:
        if r["predicted"] != "-" and not r["correct"]:
            print(f"  {r['truth']:<26} -> {r['predicted']:<26} {r['title'][:70]}")


def main(per_type: int, seed: int = 42):
    rng = random.Random(seed)
    rows, trace = [], Trace("type_eval")
    for ctype, files in sorted(cuad_by_type().items()):
        for pdf in rng.sample(files, min(per_type, len(files))):
            try:
                doc = ContractDocument(pdf.stem, extract_pages(long_path(pdf), use_vision=False))
                prof = profile_contract(doc, trace, "en")
                pred, src, title = prof.contract_type, prof.type_source, prof.title
            except Exception as e:
                pred, src, title = f"ERROR {type(e).__name__}", "-", ""
            rows.append({"file": pdf.name, "truth": ctype, "predicted": pred, "correct": pred == ctype,
                         "type_source": src, "title": title})
            print(f"{'✓' if pred == ctype else '✕'} {ctype:<26} -> {pred:<26} [{src}] {pdf.name[:50]}", flush=True)
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
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    offline() if a.offline else main(a.per_type)
