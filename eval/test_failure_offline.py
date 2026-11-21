"""V5 harness WITHOUT an API key: a scripted fake model that can fail on purpose.

1. Random failures: 10% of calls raise 503 (overload) -> every run still finishes (retry + fallback model).
2. Main model down: every call to MODEL fails -> the fallback model answers every call, the run finishes,
   and the trace says which model answered.
3. Crash + resume: one rule hits a non-retryable error -> the run stops, the finished rules are already saved;
   the re-run checks only the missing rule (no paying twice) and the report equals a clean run.
4. Context budget: old search results become stubs that keep the passage ids; the conversation shrinks;
   a passage whose full text was removed can be read again.
Usage:  python -m eval.test_failure_offline
"""
import random
import shutil
from types import SimpleNamespace

from google.genai import types

from src import agent, config, trace as trace_mod
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace
from eval.cuad import pdf_path

FNAME = "FUSIONPHARMACEUTICALSINC_06_05_2020-EX-10.17-Supply Agreement - FUSION.PDF"
MAIN, FALLBACK = "fake-main", "fake-fallback"


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(f"fake API error {code}")
        self.code = code


class FakeModels:
    """Per rule: search, search with other words, read the top passage, read it again, submit a COMPLIANT quote."""

    def __init__(self, doc, rules):
        self.plan, self.calls = {}, []
        self.fail_rate, self.down, self.poison, self.rng = 0.0, set(), None, random.Random(42)
        for r in rules:
            ranked = doc.ranked_ids(f"{r['title']} " + " ".join(r["keywords"]), k=5)
            pid = next(p for p in ranked if len(doc._by_id[p].text.split()) >= 12)
            quote = " ".join(doc._by_id[pid].text.split()[:25])
            self.plan[r["id"]] = [("search_contract", {"query": r["title"]}),
                                  ("search_contract", {"query": " ".join(r["keywords"][:3])}),
                                  ("read_passage", {"passage_id": pid}),
                                  ("submit_finding", {"policy_id": r["id"], "clause_category": r["title"],
                                                      "clause_reference": pid, "extracted_text": quote,
                                                      "compliance_status": "COMPLIANT", "risk_level": "LOW",
                                                      "issue_description": "ทดสอบ", "action_required": "-",
                                                      "suggested_redline": ""})]

    def generate_content(self, model, contents, config):
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=0)
        rid = "summary" if isinstance(contents, str) else contents[0].parts[0].text.split("Policy rule ", 1)[1].split(" ", 1)[0]
        self.calls.append((model, rid))
        if model in self.down or (self.fail_rate and self.rng.random() < self.fail_rate):
            raise FakeAPIError(503)
        if rid == self.poison:
            raise FakeAPIError(400)  # not retryable: the run stops
        if rid == "summary":
            return SimpleNamespace(text="สรุปทดสอบ", usage_metadata=usage)
        step = sum(1 for c in contents if c.role == "model")
        name, args = self.plan[rid][min(step, len(self.plan[rid]) - 1)]
        part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]))],
                               usage_metadata=usage)


def key(report):
    return [(r.finding.policy_id, r.finding.compliance_status, r.finding.extracted_text, r.verified) for r in report.findings]


def main():
    config.MIN_CALL_GAP, config.MODEL, config.FALLBACK_MODEL = 0, MAIN, FALLBACK
    config.CHECKPOINT_DIR = config.OUTPUT_DIR / "test_checkpoints"
    shutil.rmtree(config.CHECKPOINT_DIR, ignore_errors=True)
    trace_mod.random = SimpleNamespace(uniform=lambda a, b: 0.0)  # no real waiting between retries
    doc = ContractDocument(FNAME, extract_pages(pdf_path(FNAME), use_vision=False))
    rules = config.load_playbook()
    fake = FakeModels(doc, rules)
    config._client = SimpleNamespace(models=fake)

    clean = agent.review(doc, rules, Trace("v5_clean"))
    n_clean = len(fake.calls)

    # 1. random failures
    fake.fail_rate, done, fb = 0.10, 0, 0
    for i in range(20):
        doc.reset()
        tr = Trace(f"v5_random_{i}")
        rep = agent.review(doc, rules, tr)
        done += key(rep) == key(clean)
        fb += tr.totals["fallback_calls"]
    fake.fail_rate = 0.0
    print(f"1. 10% of calls fail : {done}/20 runs finished with the same findings · fallback answered {fb} calls")
    assert done == 20

    # 2. main model down
    fake.down, fake.calls = {MAIN}, []
    doc.reset()
    tr = Trace("v5_main_down")
    rep = agent.review(doc, rules, tr)
    t = tr.totals
    print(f"2. main model down   : finished, {t['fallback_calls']}/{t['llm_calls']} calls answered by {FALLBACK} "
          f"· {sum(r['type'] == 'fallback' for r in tr.records)} switches logged")
    assert key(rep) == key(clean) and t["fallback_calls"] == t["llm_calls"] > 0
    fake.down = set()

    # 3. crash + resume
    fake.poison, fake.calls = rules[2]["id"], []
    doc.reset()
    try:
        agent.review(doc, rules, Trace("v5_crash"), resume=True)
        raise AssertionError("the poisoned rule should stop the run")
    except FakeAPIError:
        pass
    folder = agent.checkpoint_dir(doc, "th")
    saved = sorted(p.name.split("_")[0] for p in folder.glob("*.json"))
    fake.poison, fake.calls = None, []
    doc.reset()
    tr = Trace("v5_resume")
    rep = agent.review(doc, rules, tr, resume=True)
    rechecked = sorted({rid for _, rid in fake.calls} - {"summary"})
    print(f"3. crash + resume    : saved before the crash {saved} · re-run checked only {rechecked} "
          f"({len(fake.calls)} calls instead of {n_clean}) · report equals a clean run · checkpoint removed after success")
    assert len(saved) == len(rules) - 1 and rechecked == [rules[2]["id"]]
    assert key(rep) == key(clean) and not folder.exists()

    # 4. context budget
    old = config.CONTEXT_BUDGET_CHARS
    sizes = []
    orig = agent.ContextBudget.apply
    agent.ContextBudget.apply = lambda self, c: sizes.append(orig(self, c)) or sizes[-1]
    config.CONTEXT_BUDGET_CHARS = 600  # tiny, to force reads into stubs as well
    doc.reset()
    tr = Trace("v5_budget")
    agent.check_rule(rules[0], doc, tr)
    agent.ContextBudget.apply = orig
    config.CONTEXT_BUDGET_CHARS = old
    cut = [(a, b) for a, b in sizes if b < a]
    ev = [r for r in tr.records if r["type"] == "context"]
    print(f"4. context budget    : shrunk before {len(cut)} of {len(sizes)} calls · e.g. {cut[0][0]:,} -> {cut[0][1]:,} chars · "
          f"{len(ev)} trace events")
    assert cut and len(ev) == len(cut)
    budget = agent.ContextBudget(agent.ProgressGuard(rules[0], doc), 10)
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="x")])]
    for i, (tool, arg) in enumerate([("search_contract", "liability"), ("read_passage", "P3"), ("read_passage", "P4")]):
        fp = budget.guard.fingerprint(tool, arg)
        budget.guard.done[fp] = i
        contents.append(types.Content(role="user", parts=[types.Part.from_function_response(
            name=tool, response={"result": "long text " * 50})]))
        budget.add(len(contents) - 1, 0, tool, arg, ["P3", "P7"] if tool == "search_contract" else [arg], fp)
    budget.apply(contents)
    stub = contents[1].parts[0].function_response.response["result"]
    assert "P3" in stub and "P7" in stub, stub
    assert budget.guard.fingerprint("read_passage", "P3") not in budget.guard.done, "stubbed read is still blocked"
    assert "long text" in contents[3].parts[0].function_response.response["result"], "latest result was cut"
    print("   stubs keep the passage ids · a stubbed read can be read again · the latest result is never cut")
    shutil.rmtree(config.CHECKPOINT_DIR, ignore_errors=True)
    print("\nPASS")


if __name__ == "__main__":
    main()
