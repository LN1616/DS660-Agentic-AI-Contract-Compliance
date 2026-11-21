"""V6 tools WITHOUT an API key, on a real long CUAD contract (CERES, 154 pages).

1. follow_reference: 'Article 9.3' opens section 9.3; a made-up section gives one-format tool error.
2. lookup_definition: a defined term opens its definition passage; an unknown term gives a tool error.
3. search page 2: returns results ranked 6-10, none repeated from page 1.
4. Agent loop with a scripted fake model: search -> follow_reference -> lookup_definition -> search page 2 -> read ->
   submit. Every tool runs through the guard (repeat check, read record), the trajectory names each tool,
   and the verifier accepts the quote. The CUAD answer for termination for convenience sits at rank 7
   (page 2), so the fake model finds it only through page 2.
Usage:  python -m eval.test_v6_offline
"""
import sys
from pathlib import Path
from types import SimpleNamespace

from google.genai import types

from src import agent, config
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace
from eval.cuad import gold_spans, pdf_path
from eval.long_offline_check import LP, answer_passage

FNAME = "CERES,INC_01_25_2012-EX-10.20-Collaboration Agreement.PDF"


class Scripted:
    def __init__(self, plan):
        self.plan = plan

    def generate_content(self, model, contents, config):
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=0)
        step = sum(1 for c in contents if c.role == "model")
        name, args = self.plan[min(step, len(self.plan) - 1)]
        part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]))],
                               usage_metadata=usage)


def main():
    config.MIN_CALL_GAP, config.FALLBACK_MODEL = 0, ""
    p = pdf_path(FNAME)
    doc = ContractDocument(FNAME.rsplit(".", 1)[0], extract_pages(Path(LP + str(p.resolve())), use_vision=False))
    rule = next(r for r in config.load_playbook() if r["id"] == "P-02")

    r = doc.follow_reference("Article 9.3")
    assert "error" not in r and r["section"].endswith("9.3"), r
    assert "error" in doc.follow_reference("Section 99.9")
    print(f"1. follow_reference  : 'Article 9.3' -> {r['passage_id']} (section {r['section']}, p.{r['page']}) · unknown section -> tool error")

    term = next(iter(doc._defs))
    d = doc.lookup_definition(term.title())
    assert "error" not in d, d
    assert "error" in doc.lookup_definition("Zebra Crossing Fee")
    print(f"2. lookup_definition : '{term.title()}' -> {d['passage_id']} · {len(doc._defs)} defined terms indexed · unknown term -> tool error")

    p1 = [x["passage_id"] for x in doc.search(rule["title"])]
    p2 = [x["passage_id"] for x in doc.search(rule["title"], page=2)]
    assert len(p2) == 5 and not set(p1) & set(p2)
    print(f"3. search page 2     : page 1 {p1} · page 2 {p2}")

    gold = answer_passage(doc, gold_spans(FNAME, rule["cuad_category"])[0])
    query = f"{rule['title']} " + " ".join(rule["keywords"])
    page2 = [x["passage_id"] for x in doc.search(query, page=2)]
    assert gold.id in page2, (gold.id, page2)
    quote = " ".join(gold_spans(FNAME, rule["cuad_category"])[0].split()[:20])
    plan = [("search_contract", {"query": query}),
            ("follow_reference", {"reference": "Article 9.3"}),
            ("lookup_definition", {"term": term}),
            ("search_contract", {"query": query, "page": 2}),
            ("read_passage", {"passage_id": gold.id}),
            ("submit_finding", {"policy_id": "P-02", "clause_category": rule["title"], "clause_reference": gold.id,
                                "extracted_text": quote, "compliance_status": "COMPLIANT", "risk_level": "LOW",
                                "issue_description": "ทดสอบ", "action_required": "-", "suggested_redline": ""})]
    config._client = SimpleNamespace(models=Scripted(plan))
    doc.reset()
    out = agent.check_rule(rule, doc, Trace("v6_offline"))
    tools = [e["tool"] for e in out.trajectory]
    assert tools == ["search_contract", "follow_reference", "lookup_definition", "search_contract",
                     "read_passage", "submit_finding"], tools
    assert out.verified, out.trajectory[-1]
    print(f"4. agent loop        : {' > '.join(tools)} · CUAD answer {gold.id} reached via page 2 · verifier accepted the quote")
    print("\nPASS")


if __name__ == "__main__":
    main()
