"""Turn a report into a table, JSON and Excel."""
import json
from pathlib import Path

import pandas as pd

from .schemas import ContractAuditReport


DECISION_TH = {"r_wait": "รออนุมัติ", "r_ok": "อนุมัติ", "r_back": "ส่งกลับ", "rechecked": "ตรวจใหม่แล้ว รออนุมัติ"}


def to_frame(report: ContractAuditReport, hitl: dict | None = None) -> pd.DataFrame:
    hitl = hitl or {}
    rows = []
    for r in report.findings:
        f = r.finding
        h = hitl.get(f.policy_id, {})
        rows.append({
            "policy": f.policy_id, "category": f.clause_category, "status": f.compliance_status,
            "risk": f.risk_level, "reference": f.clause_reference,
            "verified": "yes" if r.verified else "NO", "page_found": r.verified_page,
            "steps": r.steps, "sent_back": r.rejections,
            "quote": f.extracted_text, "issue": f.issue_description,
            "action": f.action_required, "redline": f.suggested_redline,
            "tools_used": " > ".join(r.tool_calls),
            "legal_decision": DECISION_TH.get(h.get("decision", ""), ""), "legal_comment": h.get("comment", ""),
            "decided_at": h.get("at", ""),
        })
    return pd.DataFrame(rows)


def excel_bytes(report: ContractAuditReport, hitl: dict | None = None) -> bytes:
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        pd.DataFrame([{"contract": report.contract_title, "summary": report.executive_summary, **report.counts}]
                     ).to_excel(w, sheet_name="summary", index=False)
        to_frame(report, hitl).to_excel(w, sheet_name="findings", index=False)
    return buf.getvalue()


def save(report: ContractAuditReport, out_dir: Path, name: str) -> tuple[Path, Path]:
    out_dir.mkdir(exist_ok=True)
    js = out_dir / f"{name}.json"
    js.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    xlsx = out_dir / f"{name}.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame([{"contract": report.contract_title, "summary": report.executive_summary, **report.counts}]
                     ).to_excel(w, sheet_name="summary", index=False)
        to_frame(report).to_excel(w, sheet_name="findings", index=False)
    return js, xlsx
