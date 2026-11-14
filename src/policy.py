"""Company policy -> checkable rules, sorted by contract type.

A company uploads its own contracting policy (PDF). One LLM call turns it into rules
and tags each rule with the contract types it is meant for ('All' = every contract).
The rules are merged into the policy library (criteria.py), where a person reviews and
edits them before any contract is checked (human-in-the-loop on the policy side).
"""
from pathlib import Path
from typing import Literal

import yaml
from google.genai import types
from pydantic import BaseModel, Field

from . import config
from .criteria import GENERAL, GROUPS_TH, prefix_for, renumber
from .ingest import extract_pages
from .trace import Trace

Group = Literal[tuple(GROUPS_TH)]


class PolicyRule(BaseModel):
    id: str = Field(description="P-01, P-02, ... in document order")
    title: str = Field(description="Short English topic, e.g. Payment terms")
    title_th: str = Field(description="Short Thai topic")
    text: str = Field(description="The requirement, in English, specific enough to judge a contract clause. "
                                  "Say what counts as VIOLATED and what counts as DEVIATED if the policy implies it.")
    if_absent: str = Field(description="MISSING if the contract must contain this clause; COMPLIANT if having no such clause is fine")
    keywords: list[str] = Field(description="4-6 English words or phrases a contract clause on this topic would contain")
    applies_to: list[Group] = Field(description="Contract types this rule is meant for. ['All'] if it applies to every contract")


class PolicyRules(BaseModel):
    rules: list[PolicyRule]


PROMPT = """Below is a company's contracting / procurement policy.
Extract every requirement that can be checked against a CONTRACT.
Skip internal process steps that a contract cannot show (e.g. who signs a purchase order).
One rule per requirement. Our company is the one that wrote this policy.
For each rule, list the contract types it is meant for. Use ['All'] when the policy applies it to every contract
(e.g. governing law, personal data). A procurement rule usually fits Supply, Service, Maintenance, Outsourcing.

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


def merge_into_library(lib: dict[str, list[dict]], rules: list[dict]) -> dict[str, list[dict]]:
    """Add extracted rules to each contract type they apply to (a rule for All goes only into All)."""
    out = {k: list(v) for k, v in lib.items()}
    for r in rules:
        to = r.get("applies_to") or [GENERAL]
        groups = [GENERAL] if GENERAL in to else to
        clean = {k: v for k, v in r.items() if k != "applies_to"}
        for g in groups:
            out.setdefault(g, [])
            if all(x.get("title") != clean.get("title") for x in out[g]):
                out[g].append(clean)
    return {g: renumber(v, prefix_for(g)) for g, v in out.items()}


def rules_to_yaml(rules: list[dict]) -> str:
    return yaml.safe_dump({"rules": rules}, allow_unicode=True, sort_keys=False, width=100)
