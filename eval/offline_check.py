"""Checks that need no API key.

1. Retrieval: for each rule, is a CUAD gold clause inside the top-5 search results?
2. Verifier sanity: are CUAD gold quotes found in the PDF text (score >= 90)?

Usage:  python -m eval.offline_check  [number_of_contracts]
"""
import sys

from rapidfuzz import fuzz

from src.config import load_playbook
from src.document import ContractDocument, normalize
from src.ingest import extract_pages
from eval.cuad import gold_spans, pdf_path

DEV_SET = [
    "FUSIONPHARMACEUTICALSINC_06_05_2020-EX-10.17-Supply Agreement - FUSION.PDF",
    "UAGHINC_04_14_2004-EX-10.18-MAINTENANCE AGREEMENT.PDF",
    "PAXMEDICA,INC_07_02_2020-EX-10.12-Master Service Agreement.PDF",
    "BNLFINANCIALCORP_03_30_2007-EX-10.8-OUTSOURCING AGREEMENT.PDF",
    "CCAINDUSTRIESINC_04_14_2014-EX-10.1-OUTSOURCING AGREEMENT.PDF",
    "MERITLIFEINSURANCECO_06_19_2020-EX-10.(XIV)-MASTER SERVICES AGREEMENT.PDF",
]


def main(n: int):
    rules = load_playbook()
    hit = tot = qfound = qtot = 0
    for fname in DEV_SET[:n]:
        pages = extract_pages(pdf_path(fname), use_vision=False)
        doc = ContractDocument(fname, pages)
        kinds = {k: sum(p.kind == k for p in pages) for k in ("text", "table", "scan")}
        print(f"\n{fname[:70]}\n  pages={len(pages)} {kinds} passages={len(doc.passages)}")
        for r in rules:
            gold = gold_spans(fname, r["cuad_category"])
            if not gold:
                print(f"  {r['id']} {r['title']:<28} no clause in CUAD")
                continue
            results = doc.search(f"{r['title']} " + " ".join(r["keywords"]))
            full = [normalize(doc.read(x["passage_id"])["text"]) for x in results]
            found = any(fuzz.partial_ratio(normalize(g)[:200], t) >= 85 for g in gold for t in full)
            hit += found
            tot += 1
            scores = [doc.find_quote(g)[1] for g in gold]
            qfound += sum(s >= 90 for s in scores)
            qtot += len(scores)
            print(f"  {r['id']} {r['title']:<28} retrieved={'yes' if found else 'NO '}  "
                  f"gold quotes found={sum(s >= 90 for s in scores)}/{len(scores)} (min score {min(scores):.0f})")
    print(f"\nRetrieval recall@5: {hit}/{tot} = {hit / max(tot, 1):.0%}")
    print(f"Verifier finds gold quotes: {qfound}/{qtot} = {qfound / max(qtot, 1):.0%}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else len(DEV_SET))
