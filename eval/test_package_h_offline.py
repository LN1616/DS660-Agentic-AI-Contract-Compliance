"""Package H (model-call settings + validate-and-re-ask) WITHOUT an API key.

1. finish_reason + model_version: every LLM record keeps both; a cut answer (MAX_TOKENS) adds a finish_reason event.
2. Lock the provider while measuring: with EVAL_NO_FALLBACK the fallback model is never tried.
3. Pre-flight: the size is recorded before sending; a request above 90% of the model's window is refused with a
   clear message, before any call is made.
4. Modality: an unknown (text-only) model gets the extracted text, never the PDF; a scanned page is not sent to it.
5. Single call re-ask: a finding that fails validation is asked for again once, instead of being dropped.
6. Cross-check: an unparseable (cut) answer gives no notes instead of a crash.
Usage:  python -m eval.test_package_h_offline
"""
import json
from types import SimpleNamespace

from src import agent, baseline, config, ingest
from src.document import ContractDocument
from src.ingest import extract_pages
from src.trace import Trace
from eval.cuad import pdf_path

FNAME = "FUSIONPHARMACEUTICALSINC_06_05_2020-EX-10.17-Supply Agreement - FUSION.PDF"


def resp(text="", reason="STOP", version="fake-001", parsed=None):
    cand = SimpleNamespace(finish_reason=SimpleNamespace(name=reason), content=None)
    return SimpleNamespace(text=text, parsed=parsed, candidates=[cand], model_version=version,
                           usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=10,
                                                          thoughts_token_count=0))


def finding(pid, status="COMPLIANT", text=""):
    return {"policy_id": pid, "clause_category": "x", "clause_reference": "1", "extracted_text": text,
            "compliance_status": status, "risk_level": "LOW", "issue_description": "ทดสอบ",
            "action_required": "-", "suggested_redline": ""}


class FakeClient:
    def __init__(self, answers):
        self.answers, self.sent, self.uploads = list(answers), [], 0
        self.models = SimpleNamespace(generate_content=self.generate, count_tokens=self.count)
        self.files = SimpleNamespace(upload=self.upload, delete=lambda name: None)

    def upload(self, file, config):
        self.uploads += 1
        return SimpleNamespace(name="files/fake")

    def count(self, model, contents):
        return SimpleNamespace(total_tokens=sum(len(str(c)) for c in contents) // 4)

    def generate(self, model, contents, config):
        self.sent.append((model, contents))
        return self.answers.pop(0)


def main():
    old = (config.MODEL, config.FALLBACK_MODEL, config.EVAL_NO_FALLBACK, config.VISION_MODEL, config.client)
    rules = config.load_playbook()
    doc = ContractDocument("fusion", extract_pages(pdf_path(FNAME), use_vision=False))
    quote = " ".join(doc.pages[0].text.split()[:12])
    try:
        # 1. finish_reason + model_version
        t = Trace("h1")
        t.call(lambda: resp(reason="STOP"), "ok")
        t.call(lambda: resp(reason="MAX_TOKENS"), "cut")
        llm = [r for r in t.records if r["type"] == "llm"]
        assert all(r["model_version"] == "fake-001" for r in llm) and [r["finish_reason"] for r in llm] == ["STOP", "MAX_TOKENS"]
        assert [r["label"] for r in t.records if r["type"] == "finish_reason"] == ["cut"]
        print("1. finish_reason     : recorded on every call · cut answer -> finish_reason event · model_version kept")

        # 2. no fallback while measuring
        config.MODEL, config.FALLBACK_MODEL, config.EVAL_NO_FALLBACK = "gemini-main", "gemini-backup", True
        tried = []

        class Down(Exception):
            code = 503

        def make(m):
            tried.append(m)
            raise Down()
        t = Trace("h2")
        try:
            t.call_model(make, "x")
        except Down:
            pass
        assert set(tried) == {"gemini-main"} and not any(r["type"] == "fallback" for r in t.records)
        print(f"2. provider lock     : EVAL_NO_FALLBACK -> only {config.MODEL} tried ({len(tried)} attempts), no fallback")
        config.EVAL_NO_FALLBACK = False

        # 3. pre-flight refuses an oversized request before any call
        t = Trace("h3")
        t.preflight("small", 1000)
        try:
            t.preflight("huge", 2_000_000)
            raise AssertionError("oversized request was not refused")
        except ValueError as e:
            msg = str(e)
        assert [r["tokens"] for r in t.records if r["type"] == "preflight"] == [1000, 2_000_000]
        print(f"3. pre-flight        : size recorded before sending · 2,000,000 tokens refused: \"{msg[:70]}...\"")

        # 4. modality: unknown model -> text, no upload; scanned page not sent
        config.MODEL = "some-local-model"
        fake = FakeClient([resp(json.dumps({"executive_summary": "s", "findings": [finding(r["id"], "MISSING") for r in rules]}))])
        config.client = lambda: fake
        t = Trace("h4")
        rep = baseline.review_single_call(pdf_path(FNAME), doc, rules, t)
        sent = fake.sent[0][1][0]
        assert fake.uploads == 0 and isinstance(sent, str) and sent.startswith("<contract_data>") and len(rep.findings) == len(rules)
        assert any(r["type"] == "modality" for r in t.records)
        config.VISION_MODEL = "some-local-model"
        t = Trace("h4b")
        assert ingest.vision_extract(pdf_path(FNAME), 1, t) == "" and any(r["type"] == "modality" for r in t.records)
        print("4. modality          : text-only model -> extracted text in <contract_data>, no PDF upload · scanned page not sent")

        # 5. single call re-ask: one rule invalid -> asked again once, then complete
        config.MODEL = "gemini-main"
        first = [finding(r["id"], "COMPLIANT", quote) for r in rules]
        first[1]["compliance_status"] = "MAYBE"  # invalid enum
        fake = FakeClient([resp(json.dumps({"executive_summary": "s", "findings": first})),
                           resp(json.dumps({"executive_summary": "", "findings": [finding(rules[1]["id"], "MISSING")]}))])
        config.client = lambda: fake
        t = Trace("h5")
        rep = baseline.review_single_call(pdf_path(FNAME), doc, rules, t)
        ev = [r for r in t.records if r["type"] == "reask"]
        assert fake.uploads == 1 and len(fake.sent) == 2 and ev and ev[0]["rules"] == [rules[1]["id"]]
        assert {f.finding.policy_id for f in rep.findings} == {r["id"] for r in rules}
        assert any(r["type"] == "preflight" for r in t.records)
        print(f"5. validate + re-ask : {rules[1]['id']} invalid -> asked again once (2 calls) -> {len(rep.findings)}/{len(rules)} findings, none dropped")

        # 6. cross-check survives a cut answer
        fake = FakeClient([resp('{"notes": [{"finding_ids": ["P-01"', reason="MAX_TOKENS")])
        config.client = lambda: fake
        t = Trace("h6")
        notes = agent.cross_check(rep.findings, t)
        assert notes == [] and any(r["type"] == "finish_reason" for r in t.records)
        print("6. cross-check       : cut JSON -> no notes, no crash, finish_reason event in trace")
    finally:
        config.MODEL, config.FALLBACK_MODEL, config.EVAL_NO_FALLBACK, config.VISION_MODEL, config.client = old
    print("\nPASS")


if __name__ == "__main__":
    main()
