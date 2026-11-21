"""Long contracts WITHOUT an API key: where do CUAD's answers sit, and can our search reach them?

Evidence for V6 (decided before building, so tools are not built on a guess). For the longest CUAD contracts and
each policy rule whose clause CUAD marks as present:
  - answer passage  : the passage that holds the CUAD expert span (fuzzy match >= 80)
  - in attachment   : the passage comes after an EXHIBIT / SCHEDULE / APPENDIX / ANNEX heading
  - search top-5    : the agent's first search (rule title) or the verifier's ranking (title + keywords)
                      returns that passage in its top 5
  - points elsewhere: the answer passage cites another section / exhibit, or uses defined terms ("X" means ...)
Usage:  python -m eval.long_offline_check [n_contracts=6]
"""
import os
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

from src import config
from src.document import ContractDocument, normalize
from src.ingest import extract_pages
from eval.cuad import gold_spans, master, pdf_path

LP = "\\\\?\\" if sys.platform == "win32" else ""
ATTACH = re.compile(r"^\s*(EXHIBIT|SCHEDULE|APPENDIX|ANNEX|ATTACHMENT)\b", re.MULTILINE)
REF = re.compile(r"\b(?:Section|Article|Clause|paragraph)\s+\d+(?:\.\d+)*|\b(?:Exhibit|Schedule|Appendix|Annex|Attachment)\s+[A-Z0-9][\w.-]*")
DEFINES = re.compile(r'["“]([A-Z][\w\s-]{2,40})["”]\s*(?:\)\s*)?(?:means|shall mean|has the meaning)')


def longest(n: int) -> list[str]:
    d = LP + str((config.CUAD_DIR / "full_contract_txt").resolve())
    by_stem = {f.rsplit(".", 1)[0].lower(): f for f in master()["Filename"]}
    rows = sorted(((e.stat().st_size, e.name[:-4]) for e in os.scandir(d) if e.name.endswith(".txt")), reverse=True)
    out = []
    for _, stem in rows:
        f = by_stem.get(stem.lower())
        if f:
            try:
                pdf_path(f)
                out.append(f)
            except KeyError:
                continue
        if len(out) == n:
            break
    return out


def answer_passage(doc: ContractDocument, span: str):
    s = normalize(span)[:300]
    best = max(doc.passages, key=lambda p: fuzz.partial_ratio(s, normalize(p.text)))
    return best if fuzz.partial_ratio(s, normalize(best.text)) >= 80 else None


def main(n: int):
    rules = config.load_playbook()
    defined = {}
    rows, resolved, looked = [], [], []
    for f in longest(n):
        p = pdf_path(f)
        doc = ContractDocument(f.rsplit(".", 1)[0], extract_pages(Path(LP + str(p.resolve())), use_vision=False))
        attach_at = None  # index of the first attachment heading in the second half of the contract
        for i, ps in enumerate(doc.passages):
            if i > len(doc.passages) * 0.4 and ATTACH.search(ps.text):
                attach_at = i
                break
        defined[f] = set(m.group(1).strip() for ps in doc.passages for m in DEFINES.finditer(ps.text))
        print(f"\n{f[:60]} · {len(doc.pages)} pages · {len(doc.passages)} passages · "
              f"attachments from passage {doc.passages[attach_at].id if attach_at is not None else '-'} · "
              f"{len(defined[f])} defined terms")
        for r in rules:
            spans = gold_spans(f, r["cuad_category"])
            if not spans:
                continue
            ap = [answer_passage(doc, s) for s in spans]
            ap = [a for a in ap if a]
            if not ap:
                rows.append((f, r["id"], "not located", False, False, False, False, False))
                print(f"  {r['id']}: CUAD span not located in the extracted text")
                continue
            ids = {a.id for a in ap}
            first = doc.ranked_ids(r["title"], k=5)
            verifier = doc.ranked_ids(f"{r['title']} " + " ".join(r["keywords"]), k=5)
            in_att = any(attach_at is not None and doc.passages.index(a) >= attach_at for a in ap)
            refs = sorted({m.group(0) for a in ap for m in REF.finditer(a.text)})
            uses_def = sorted({t for t in defined[f] for a in ap if t in a.text})[:4]
            hit1, hitv = bool(ids & set(first)), bool(ids & set(verifier))
            hit10 = bool(ids & (set(doc.ranked_ids(r["title"], k=10)) | set(doc.ranked_ids(
                f"{r['title']} " + " ".join(r["keywords"]), k=10))))
            for ref in refs:  # V6 follow_reference: does each cited part resolve?
                res = doc.follow_reference(ref)
                resolved.append((ref, "error" not in res))
            for term in uses_def:  # V6 lookup_definition: is each defined term found?
                looked.append((term, "error" not in doc.lookup_definition(term)))
            rows.append((f, r["id"], "ok", in_att, hit1, hitv, bool(refs), hit10))
            print(f"  {r['id']}: answer {sorted(ids)} p.{ap[0].page} sec '{ap[0].section}' · attachment {in_att} · "
                  f"top-5 first search {hit1} / verifier {hitv} · cites {refs[:4]} · defined terms {uses_def}")
    ok = [r for r in rows if r[2] == "ok"]
    print(f"\nSUMMARY over {len(rows)} rule x contract pairs where CUAD marks the clause present:")
    print(f"  span located in our extracted text : {len(ok)}/{len(rows)}")
    print(f"  answer inside an attachment        : {sum(r[3] for r in ok)}/{len(ok)}")
    print(f"  first search (rule title) top-5    : {sum(r[4] for r in ok)}/{len(ok)}")
    print(f"  verifier ranking top-5             : {sum(r[5] for r in ok)}/{len(ok)}")
    print(f"  either reaches it                  : {sum(r[4] or r[5] for r in ok)}/{len(ok)}")
    print(f"  answer passage cites another part  : {sum(r[6] for r in ok)}/{len(ok)}")
    print("V6 tools (same contracts):")
    print(f"  either ranking top-10 (search page 2): {sum(r[7] for r in ok)}/{len(ok)}")
    print(f"  follow_reference resolves a citation : {sum(ok_ for _, ok_ in resolved)}/{len(resolved)} "
          f"· not resolved: {[r for r, ok_ in resolved if not ok_][:8]}")
    print(f"  lookup_definition finds the term     : {sum(ok_ for _, ok_ in looked)}/{len(looked)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
