"""Output contract for the agent. Every model answer must fit these models."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["COMPLIANT", "DEVIATED", "VIOLATED", "MISSING"]
Risk = Literal["HIGH", "MEDIUM", "LOW"]


class ClauseFinding(BaseModel):
    """What the policy checker submits for one policy rule."""
    policy_id: str = Field(description="Policy rule id, e.g. P-01")
    clause_category: str = Field(description="Topic of the clause, e.g. Limitation of liability")
    clause_reference: str = Field(description="Section number and page, e.g. 'Section 12.1, page 9'. 'Not found' if MISSING.")
    extracted_text: str = Field(description="Exact sentence(s) copied verbatim from the contract. Empty string if MISSING.")
    compliance_status: Status
    risk_level: Risk
    issue_description: str = Field(description="What is wrong or why it complies. Write in the report language.")
    action_required: str = Field(description="What the buyer should do. Write in the report language.")
    suggested_redline: str = Field(description="Proposed replacement wording in English. Empty string if COMPLIANT.")


class ReviewedFinding(BaseModel):
    """A finding plus what the harness observed while producing it."""
    finding: ClauseFinding
    verified: bool                     # passed the verifier
    verified_page: Optional[int] = None  # page where the quote was found
    quote_score: Optional[float] = None  # fuzzy match score 0-100
    steps: int = 0                      # LLM calls used
    rejections: int = 0                 # times the verifier sent it back
    tool_calls: list[str] = []


class ContractAuditReport(BaseModel):
    contract_title: str
    executive_summary: str             # in the report language
    findings: list[ReviewedFinding]

    @property
    def counts(self) -> dict:
        f = [r.finding for r in self.findings]
        return {
            "total": len(f),
            "high": sum(x.risk_level == "HIGH" for x in f),
            "medium": sum(x.risk_level == "MEDIUM" for x in f),
            "missing": sum(x.compliance_status == "MISSING" for x in f),
            "verified": sum(r.verified for r in self.findings),
        }


def finding_json_schema() -> dict:
    """Plain JSON schema for function-calling parameters (no $defs / anyOf)."""
    schema = ClauseFinding.model_json_schema()
    props = {}
    for name, p in schema["properties"].items():
        q = {k: v for k, v in p.items() if k in ("type", "enum", "description")}
        q.setdefault("type", "string")
        props[name] = q
    return {"type": "object", "properties": props, "required": list(props)}
