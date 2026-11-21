"""Sectioning (rules checked in parallel) WITHOUT an API key, using a scripted fake model with a fixed delay.

Checks: same findings as one-after-another, in rule order · every callback runs on the calling thread ·
each rule's "read before MISSING" record is its own · wall time close to the slowest rule, not the sum.
Usage:  python -m eval.test_parallel_offline
"""
import threading
import time
from types import SimpleNamespace

from google.genai import types

from src import agent, config
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace
from eval.cuad import pdf_path

FNAME = "FUSIONPHARMACEUTICALSINC_06_05_2020-EX-10.17-Supply Agreement - FUSION.PDF"
DELAY = 0.4  # seconds per fake model call


class FakeModels:
    """Per rule: read the top passage, then submit it as a COMPLIANT quote. Rule found from the first prompt."""

    def __init__(self, doc, rules):
        self.plan = {}
        for r in rules:
            ranked = doc.ranked_ids(f"{r['title']} " + " ".join(r["keywords"]), k=5)
            pid = next(p for p in ranked if len(doc._by_id[p].text.split()) >= 12)  # skip heading-only passages
            quote = " ".join(doc._by_id[pid].text.split()[:25])
            self.plan[r["id"]] = [("read_passage", {"passage_id": pid}),
                                  ("submit_finding", {"policy_id": r["id"], "clause_category": r["title"],
                                                      "clause_reference": pid, "extracted_text": quote,
                                                      "compliance_status": "COMPLIANT", "risk_level": "LOW",
                                                      "issue_description": "ทดสอบ", "action_required": "-",
                                                      "suggested_redline": ""})]

    def generate_content(self, model, contents, config):
        time.sleep(DELAY)
        first = contents[0].parts[0].text
        rid = first.split("Policy rule ", 1)[1].split(" ", 1)[0]
        step = sum(1 for c in contents if c.role == "model")
        name, args = self.plan[rid][min(step, 1)]
        part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=0)
        return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]))],
                               usage_metadata=usage)


def run(doc, rules, workers):
    config.PARALLEL_RULES = workers
    doc.reset()
    threads, order = set(), []
    t0 = time.time()
    out = agent.check_rules(doc, rules, Trace(f"parallel_test_{workers}"),
                            on_step=lambda r: threads.add(threading.get_ident()),
                            on_tool=lambda r, c: threads.add(threading.get_ident()),
                            on_done=lambda r, f: (threads.add(threading.get_ident()), order.append(r["id"])))
    return out, time.time() - t0, threads, order


def main():
    config.MIN_CALL_GAP = 0
    doc = ContractDocument(FNAME, extract_pages(pdf_path(FNAME), use_vision=False))
    rules = config.load_playbook()
    config._client = SimpleNamespace(models=FakeModels(doc, rules))

    seq, t_seq, th_seq, _ = run(doc, rules, 1)
    par, t_par, th_par, done_order = run(doc, rules, 5)
    main_id = threading.get_ident()

    key = lambda rs: [(r.finding.policy_id, r.finding.compliance_status, r.verified, r.steps) for r in rs]
    assert key(seq) == key(par), (key(seq), key(par))
    assert [r.finding.policy_id for r in par] == [r["id"] for r in rules], "findings not in rule order"
    assert th_seq == th_par == {main_id}, "a callback ran on a worker thread"
    assert all(r.verified for r in par)
    print(f"rules      : {len(rules)} · {DELAY}s per call · 2 calls per rule")
    print(f"one by one : {t_seq:.1f}s   parallel (5): {t_par:.1f}s   ({t_seq / t_par:.1f}x faster)")
    print(f"findings   : identical, rule order kept · finish order {done_order}")
    print("callbacks  : all on the calling thread (safe for Streamlit)")
    assert t_par < t_seq / 2.5, "parallel run was not faster"

    # own read record: a MISSING answer for rule 2 must not count passages only rule 1 read
    r1, r2 = rules[0], rules[1]
    g1, g2 = agent.ProgressGuard(r1, doc), agent.ProgressGuard(r2, doc)
    top2 = doc.ranked_ids(f"{r2['title']} " + " ".join(r2["keywords"]), k=3)
    for pid in top2:
        g1.run("read_passage", pid, 1)
    miss = agent.ClauseFinding.model_validate({**FakeModels(doc, [r2]).plan[r2["id"]][1][1],
                                               "compliance_status": "MISSING", "extracted_text": ""})
    ok, why, *_ = agent.verify(miss, r2, doc, g2.read)
    assert not ok and "read_passage" in why, "rule 2 borrowed rule 1's reading"
    print("read record: per rule (rule 2 cannot claim MISSING on passages only rule 1 read)")
    print("\nPASS")


if __name__ == "__main__":
    main()
