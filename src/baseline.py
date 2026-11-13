"""Baseline B2 - the original PoC: send the whole PDF + all rules to Gemini in ONE call.

No tools, no loop, no verifier. We still run the quote check afterwards, only to
MEASURE how often its citations are real (it is never sent back to fix them).
"""
from pathlib import Path

from google.genai import types
from pydantic import ValidationError

from . import config
from .document import ContractDocument
from .schemas import ClauseFinding, ContractAuditReport, ReviewedFinding, finding_json_schema
from .trace import Trace

PROMPT = """You review a supplier contract for the BUYER against the company policy rules below.
Return one finding per rule. extracted_text must be copied word for word from the contract
(empty string if MISSING). issue_description, action_required and executive_summary in {language}, suggested_redline in English.

Policy rules:
{rules}"""


def review_single_call(pdf_path: Path, doc: ContractDocument, rules: list[dict], trace: Trace,
                       lang: str = "th") -> ContractAuditReport:
    client = config.client()
    uploaded = client.files.upload(file=str(pdf_path))
    rules_text = "\n".join(f"- {r['id']} {r['title']}: {r['text'].strip()} "
                           f"(If no clause on this topic: {r['if_absent']}.)" for r in rules)
    schema = {"type": "object", "properties": {
        "executive_summary": {"type": "string"},
        "findings": {"type": "array", "items": finding_json_schema()}},
        "required": ["executive_summary", "findings"]}
    try:
        resp = trace.call(lambda: client.models.generate_content(
            model=config.MODEL,
            contents=[uploaded, PROMPT.format(rules=rules_text, language={"th": "Thai", "en": "English"}[lang])],
            config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                               response_json_schema=schema)), label="baseline single call")
    finally:
        client.files.delete(name=uploaded.name)

    data = resp.parsed if isinstance(resp.parsed, dict) else __import__("json").loads(resp.text)
    findings = []
    for raw in data.get("findings", []):
        try:
            f = ClauseFinding.model_validate(raw)
        except ValidationError:
            continue
        page, score = doc.find_quote(f.extracted_text) if f.extracted_text.strip() else (None, None)
        ok = f.compliance_status == "MISSING" or (score is not None and score >= 88)
        findings.append(ReviewedFinding(finding=f, verified=ok, verified_page=page, quote_score=score, steps=1))
    return ContractAuditReport(contract_title=doc.title, executive_summary=data.get("executive_summary", ""),
                               findings=findings)
