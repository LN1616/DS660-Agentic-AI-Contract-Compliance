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


CONTRACT_DECISION_TH = {"pending": "รอพิจารณา", "sent": "ส่งข้อเสนอแก้ไขให้คู่สัญญาแล้ว",
                        "approved": "อนุมัติให้ลงนาม", "rejected": "ปฏิเสธสัญญา"}
CHANGE_TH = {"fixed": "แก้ไขแล้ว", "better": "ดีขึ้น", "open": "ยังไม่แก้", "new": "ประเด็นใหม่",
             "worse": "แย่ลง", "same": "ผ่านเหมือนเดิม"}


def excel_bytes(report: ContractAuditReport, hitl: dict | None = None, record: dict | None = None) -> bytes:
    """record (optional): version, decision, decision_log, compare - the contract-level audit trail."""
    import io
    record = record or {}
    dec = record.get("decision") or {}
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        pd.DataFrame([{"contract": report.contract_title, "version": record.get("version", 1),
                       "decision": CONTRACT_DECISION_TH.get(dec.get("decision", "pending")),
                       "decided_by": dec.get("by", ""), "decided_at": dec.get("at", ""), "reason": dec.get("reason", ""),
                       "check": "ตรวจรอบสุดท้าย (Agent)" if record.get("kind") == "final" else "ตรวจปกติ",
                       "checked_at": record.get("created") or "",
                       "summary": report.executive_summary, **report.counts}]
                     ).to_excel(w, sheet_name="summary", index=False)
        to_frame(report, hitl).to_excel(w, sheet_name="findings", index=False)
        log = record.get("decision_log") or []
        pd.DataFrame([{"at": e.get("at", ""), "decision": CONTRACT_DECISION_TH.get(e.get("decision"), e.get("decision")),
                       "by": e.get("by", ""), "reason": e.get("reason", "")} for e in log],
                     columns=["at", "decision", "by", "reason"]).to_excel(w, sheet_name="decision_history", index=False)
        if record.get("compare"):
            v = record.get("version", 2)
            pd.DataFrame([{"policy": c["id"], "topic": c["topic"], f"v{v - 1}": c["old"], f"v{v}": c["new"],
                           "change": CHANGE_TH.get(c["change"], c["change"]),
                           "approved_redline_match_new": "" if c["redline_score"] is None else c["redline_score"],
                           "approved_redline_match_old": "" if c.get("redline_old_score") is None else c["redline_old_score"]}
                          for c in record["compare"]]).to_excel(w, sheet_name=f"compare_v{v - 1}_v{v}", index=False)
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
