"""Tests the agent loop WITHOUT an API key, using a scripted fake model.

Script: search -> submit a made-up quote (verifier must reject) -> read -> submit the real quote (accepted).
Usage:  python -m eval.test_harness_offline
"""
from types import SimpleNamespace

from google.genai import types

from src import agent, config
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace
from eval.cuad import gold_spans, pdf_path

FNAME = "FUSIONPHARMACEUTICALSINC_06_05_2020-EX-10.17-Supply Agreement - FUSION.PDF"


class FakeModels:
    def __init__(self, script):
        self.script, self.seen_results = list(script), []

    def generate_content(self, model, contents, config):
        last = contents[-1]
        for p in last.parts or []:
            if p.function_response:
                self.seen_results.append(p.function_response.response["result"])
        name, args = self.script.pop(0)
        part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=0)
        return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]))],
                               usage_metadata=usage)


def finding(quote):
    return {"policy_id": "P-01", "clause_category": "Limitation of liability", "clause_reference": "Section 9, page 8",
            "extracted_text": quote, "compliance_status": "DEVIATED", "risk_level": "MEDIUM",
            "issue_description": "ทดสอบ", "action_required": "ทดสอบ", "suggested_redline": "test"}


def main():
    doc = ContractDocument(FNAME, extract_pages(pdf_path(FNAME), use_vision=False))
    rule = config.load_playbook()[0]
    real_quote = gold_spans(FNAME, rule["cuad_category"])[0]
    hit = doc.search("limitation of liability")[0]["passage_id"]
    doc.seen.clear()

    fake = FakeModels([
        ("search_contract", {"query": "limitation of liability"}),
        ("submit_finding", finding("Supplier liability shall never exceed one dollar under any circumstances.")),
        ("read_passage", {"passage_id": hit}),
        ("submit_finding", finding(real_quote)),
    ])
    config._client = SimpleNamespace(models=fake)
    trace = Trace("offline_harness_test")
    result = agent.check_rule(rule, doc, trace)

    rejected = [r for r in fake.seen_results if isinstance(r, dict) and "rejected" in r]
    print("tool calls :", result.tool_calls)
    print("rejections :", result.rejections, "->", rejected[0]["rejected"][:90] if rejected else None)
    print("verified   :", result.verified, "page", result.verified_page, "score", result.quote_score)
    print("trace      :", trace.totals)
    assert result.rejections == 1 and result.verified and result.steps == 4, "harness behaved unexpectedly"
    print("\nPASS: fake quote rejected, real quote accepted, loop stopped after 4 steps")


if __name__ == "__main__":
    main()
