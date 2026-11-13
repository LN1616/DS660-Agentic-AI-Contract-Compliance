"""Company policy -> checkable rules.

A company uploads its own procurement policy (PDF). One LLM call turns it into
rules in the same format as data/policy_playbook.yaml. A person reviews and edits
the rules before any contract is checked (human-in-the-loop on the policy side).
"""
from pathlib import Path

import yaml
from google.genai import types
from pydantic import BaseModel, Field

from . import config
from .ingest import extract_pages
from .trace import Trace


class PolicyRule(BaseModel):
    id: str = Field(description="P-01, P-02, ... in document order")
    title: str = Field(description="Short English topic, e.g. Payment terms")
    title_th: str = Field(description="Short Thai topic")
    text: str = Field(description="The requirement, in English, specific enough to judge a contract clause. "
                                  "Say what counts as VIOLATED and what counts as DEVIATED if the policy implies it.")
    if_absent: str = Field(description="MISSING if the contract must contain this clause; COMPLIANT if having no such clause is fine")
    keywords: list[str] = Field(description="4-6 English words or phrases a contract clause on this topic would contain")


class PolicyRules(BaseModel):
    rules: list[PolicyRule]


PROMPT = """Below is a company's procurement / contracting policy.
Extract every requirement that can be checked against a SUPPLIER CONTRACT.
Skip internal process steps that a contract cannot show (e.g. who signs a purchase order).
One rule per requirement. The buyer is the company that wrote this policy.

POLICY:
{policy}"""


def extract_rules(policy_pdf: Path, trace: Trace | None = None) -> list[dict]:
    trace = trace or Trace("policy_extract")
    text = "\n\n".join(p.text for p in extract_pages(policy_pdf, use_vision=True, trace=trace))
    resp = trace.call(lambda: config.client().models.generate_content(
        model=config.MODEL,
        contents=PROMPT.format(policy=text[:60000]),
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                           response_schema=PolicyRules)), label="policy extract")
    parsed = resp.parsed if isinstance(resp.parsed, PolicyRules) else PolicyRules.model_validate_json(resp.text)
    rules = []
    for i, r in enumerate(parsed.rules, 1):
        d = r.model_dump()
        d["id"] = f"P-{i:02d}"
        d["if_absent"] = "COMPLIANT" if d["if_absent"].upper().startswith("COMPLIANT") else "MISSING"
        rules.append(d)
    return rules


def rules_to_yaml(rules: list[dict]) -> str:
    return yaml.safe_dump({"rules": rules}, allow_unicode=True, sort_keys=False, width=100)
