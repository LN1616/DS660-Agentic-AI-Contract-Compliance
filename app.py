"""Step 7 - Streamlit interface for the Contract Compliance Agent.

Run:  streamlit run app.py
"""
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src import config
from src.agent import review
from src.baseline import review_single_call
from src.document import ContractDocument
from src.ingest import extract_pages
from src.report import save, to_frame
from src.trace import Trace
from eval.offline_check import DEV_SET
from eval.cuad import pdf_path

st.set_page_config(page_title="Contract Compliance Agent", page_icon="§", layout="wide")

STATUS_COLOR = {"COMPLIANT": "green", "DEVIATED": "orange", "VIOLATED": "red", "MISSING": "gray"}
RISK_COLOR = {"HIGH": "red", "MEDIUM": "orange", "LOW": "gray"}
REVIEW_OPTIONS = ["รอ legal อนุมัติ", "อนุมัติข้อเสนอแก้ไข", "ส่งกลับให้ตรวจใหม่"]

if "hitl" not in st.session_state:
    st.session_state.hitl = {}

# ---------------- sidebar: documents ----------------
with st.sidebar:
    st.title("§ Contract Compliance Agent")
    st.caption("ตรวจสัญญาจัดซื้อเทียบนโยบายบริษัท")

    st.subheader("1 · สัญญา")
    source = st.radio("แหล่งสัญญา", ["ตัวอย่างจาก CUAD", "อัปโหลด PDF"], horizontal=True, label_visibility="collapsed")
    if source == "อัปโหลด PDF":
        upload = st.file_uploader("สัญญา (PDF)", type="pdf")
        sample = None
    else:
        sample = st.selectbox("เลือกสัญญาตัวอย่าง", DEV_SET, format_func=lambda f: f.split("-EX-")[0][:28] + " · " + f.rsplit("-", 1)[-1][:28])
        upload = None

    st.subheader("2 · นโยบายบริษัท")
    rules = config.load_playbook()
    chosen = st.multiselect("กฎที่ใช้ตรวจ", [r["id"] for r in rules], default=[r["id"] for r in rules],
                            format_func=lambda i: f"{i} " + next(r["title_th"] for r in rules if r["id"] == i))
    with st.expander("ดูรายละเอียดกฎ"):
        for r in rules:
            st.markdown(f"**{r['id']} {r['title_th']}**  \n{r['text']}")

    st.subheader("3 · วิธีตรวจ")
    mode = st.radio("ระบบ", ["Agent (มีผู้ตรวจซ้ำ)", "Baseline (เรียก AI ครั้งเดียว)"], label_visibility="collapsed")
    vision = st.toggle("อ่านหน้า scan ด้วย vision model", value=True)
    st.caption(f"Model: `{config.MODEL}`")
    run = st.button("วิเคราะห์สัญญา", type="primary", width="stretch",
                    disabled=not chosen or (source == "อัปโหลด PDF" and upload is None))

# ---------------- run ----------------
if run:
    if upload is not None:
        tmp = Path(tempfile.mkdtemp()) / upload.name
        tmp.write_bytes(upload.getvalue())
        pdf = tmp
    else:
        pdf = pdf_path(sample)
    active = [r for r in rules if r["id"] in chosen]
    trace = Trace(pdf.stem[:30] + ("_agent" if mode.startswith("Agent") else "_baseline"))
    t0 = time.time()
    try:
        with st.status("Agent กำลังทำงาน ...", expanded=True) as status:
            st.write("อ่านเอกสาร: ตรวจชนิดหน้า แล้วดึงข้อความและตาราง")
            pages = extract_pages(pdf, use_vision=vision, trace=trace)
            doc = ContractDocument(pdf.stem, pages)
            kinds = {k: sum(p.kind == k for p in pages) for k in ("text", "table", "scan")}
            st.write(f"✓ {len(pages)} หน้า (ข้อความ {kinds['text']}, ตาราง {kinds['table']}, scan {kinds['scan']}) "
                     f"แบ่งได้ {len(doc.passages)} ข้อ")
            if mode.startswith("Agent"):
                report = review(doc, active, trace,
                                on_step=lambda r: st.write(f"ตรวจ {r['id']} {r['title_th']} ..."))
            else:
                st.write("ส่งสัญญาทั้งฉบับให้ AI ครั้งเดียว (baseline)")
                report = review_single_call(pdf, doc, active, trace)
            status.update(label=f"เสร็จใน {time.time() - t0:.0f} วินาที", state="complete", expanded=False)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {type(e).__name__}: {str(e)[:300]}")
        st.stop()
    _, xlsx = save(report, config.OUTPUT_DIR, trace.run_name)
    trace.save()
    st.session_state.result = {"report": report, "totals": trace.totals, "xlsx": xlsx.read_bytes(),
                               "xlsx_name": xlsx.name, "mode": mode, "seconds": time.time() - t0}
    st.session_state.hitl = {}

# ---------------- results ----------------
res = st.session_state.get("result")
if not res:
    st.header("รายงานตรวจสัญญา")
    st.info("เลือกสัญญาและกฎทางซ้าย แล้วกด **วิเคราะห์สัญญา** · agent ใช้เวลาประมาณ 1–3 นาทีต่อสัญญา")
    st.stop()

report, totals = res["report"], res["totals"]
c = report.counts
st.header(report.contract_title.split("-EX-")[0][:60])
st.caption(f"{res['mode']} · {totals['llm_calls']} AI calls · {res['seconds']:.0f} วินาที · "
           f"{totals['tokens_in'] + totals['tokens_out']:,} tokens · ~${totals['cost_usd']:.3f}")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("หัวข้อที่ตรวจ", c["total"])
k2.metric("ความเสี่ยงสูง", c["high"])
k3.metric("ความเสี่ยงปานกลาง", c["medium"])
k4.metric("ข้อที่ขาดหายไป", c["missing"])
k5.metric("ผ่านผู้ตรวจซ้ำ", f"{c['verified']}/{c['total']}")

(st.warning if c["high"] else st.success)(f"**สรุปสำหรับผู้บริหาร:** {report.executive_summary}")

df = to_frame(report)
f1, f2 = st.columns([3, 1])
show = f1.multiselect("กรองสถานะ", list(STATUS_COLOR), default=list(STATUS_COLOR))
f2.download_button("ดาวน์โหลด Excel", res["xlsx"], res["xlsx_name"], width="stretch")
view = df[df["status"].isin(show)][["policy", "category", "status", "risk", "reference", "verified", "steps", "sent_back"]]
st.dataframe(view, hide_index=True, width="stretch",
             column_config={"policy": "กฎ", "category": "หัวข้อ", "status": "สถานะ", "risk": "ความเสี่ยง",
                            "reference": "อ้างอิงในสัญญา", "verified": "ผู้ตรวจซ้ำ",
                            "steps": st.column_config.NumberColumn("AI calls"), "sent_back": "ถูกส่งกลับ"})

st.subheader("รายละเอียดรายข้อ")
for r in report.findings:
    f = r.finding
    if f.compliance_status not in show:
        continue
    icon = {"COMPLIANT": "✅", "DEVIATED": "🟠", "VIOLATED": "🔴", "MISSING": "⚪"}[f.compliance_status]
    with st.expander(f"{icon} {f.policy_id} · {f.clause_category} — {f.compliance_status} / {f.risk_level}",
                     expanded=f.risk_level == "HIGH"):
        left, right = st.columns(2)
        with left:
            st.markdown(f":{STATUS_COLOR[f.compliance_status]}-badge[{f.compliance_status}] "
                        f":{RISK_COLOR[f.risk_level]}-badge[{f.risk_level}]")
            st.markdown(f"**ข้อความในสัญญา** · {f.clause_reference}")
            st.info(f.extracted_text or "ไม่พบข้อความเกี่ยวกับหัวข้อนี้ในสัญญา")
            if r.verified and r.verified_page:
                st.success(f"ผู้ตรวจซ้ำ: พบข้อความนี้จริงในหน้า {r.verified_page} (ตรง {r.quote_score:.0f}/100)")
            elif r.verified:
                st.success("ผู้ตรวจซ้ำ: อ่านข้อที่เกี่ยวข้องครบแล้วก่อนสรุปว่าไม่มี")
            else:
                st.error("ผู้ตรวจซ้ำไม่ผ่าน: ต้องให้คนตรวจข้อนี้เอง")
        with right:
            st.markdown(f"**ประเด็น**  \n{f.issue_description}")
            st.markdown(f"**สิ่งที่ต้องทำ**  \n{f.action_required}")
            if f.suggested_redline:
                st.markdown("**ข้อเสนอแก้ไข (redline)**")
                st.code(f.suggested_redline, language=None, wrap_lines=True)
            if f.risk_level == "HIGH":
                st.session_state.hitl[f.policy_id] = st.radio(
                    "การตรวจทานโดยฝ่ายกฎหมาย (human-in-the-loop)", REVIEW_OPTIONS, horizontal=True,
                    key=f"hitl_{f.policy_id}")
        st.caption("เส้นทางของ agent: " + (" → ".join(r.tool_calls) or "single call"))
