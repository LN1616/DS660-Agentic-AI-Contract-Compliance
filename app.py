"""Step 7 - Streamlit interface for the Contract Compliance Agent.

Full loop:  company policy (sample / upload PDF) -> editable rules -> contract -> agent -> report + legal review
Run:  streamlit run app.py
"""
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from src import config
from src.agent import review
from src.baseline import review_single_call
from src.document import ContractDocument
from src.ingest import extract_pages
from src.policy import extract_rules, rules_to_yaml
from src.report import save, to_frame
from src.trace import Trace
from eval.offline_check import DEV_SET
from eval.cuad import pdf_path

st.set_page_config(page_title="Contract Compliance Agent", page_icon="§", layout="wide")

STATUS_COLOR = {"COMPLIANT": "green", "DEVIATED": "orange", "VIOLATED": "red", "MISSING": "gray"}
RISK_COLOR = {"HIGH": "red", "MEDIUM": "orange", "LOW": "gray"}
STATUS_ICON = {"COMPLIANT": "✅", "DEVIATED": "🟠", "VIOLATED": "🔴", "MISSING": "⚪"}
REVIEW_OPTIONS = ["รอ legal อนุมัติ", "อนุมัติข้อเสนอแก้ไข", "ส่งกลับให้ตรวจใหม่"]
POLICY_SOURCES = {
    "นโยบายตัวอย่างภาษาไทย (บริษัทสมมติ)": config.ROOT / "data" / "sample_company_policy_th.yaml",
    "นโยบายสำหรับทดสอบกับ CUAD (5 ข้อ)": config.PLAYBOOK_PATH,
    "อัปโหลดนโยบายบริษัท (PDF)": None,
}
COLS = ["use", "id", "title_th", "title", "text", "if_absent", "keywords"]


def rules_to_df(rules: list[dict]) -> pd.DataFrame:
    rows = [{"use": True, "id": r["id"], "title_th": r.get("title_th", ""), "title": r.get("title", ""),
             "text": " ".join(str(r.get("text", "")).split()), "if_absent": r.get("if_absent", "MISSING"),
             "keywords": ", ".join(r.get("keywords", []))} for r in rules]
    return pd.DataFrame(rows, columns=COLS)


def df_to_rules(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        if not r["use"] or not str(r["text"]).strip():
            continue
        out.append({"id": str(r["id"]).strip() or f"P-{len(out) + 1:02d}", "title": str(r["title"] or r["title_th"]),
                    "title_th": str(r["title_th"] or r["title"]), "text": str(r["text"]),
                    "if_absent": r["if_absent"] if r["if_absent"] in ("MISSING", "COMPLIANT") else "MISSING",
                    "keywords": [k.strip() for k in str(r["keywords"]).split(",") if k.strip()]})
    return out


def load_source(name: str):
    path = POLICY_SOURCES[name]
    if path is not None:
        st.session_state.rules_df = rules_to_df(yaml.safe_load(path.read_text(encoding="utf-8"))["rules"])
    else:
        st.session_state.rules_df = pd.DataFrame(columns=COLS)
    st.session_state.policy_source = name


st.session_state.setdefault("policy_source", None)

# ================= sidebar =================
with st.sidebar:
    st.title("§ Contract Compliance Agent")
    st.caption("ตรวจสัญญาจัดซื้อเทียบนโยบายบริษัท")

    st.subheader("1 · นโยบายบริษัท")
    src_name = st.selectbox("แหล่งนโยบาย", list(POLICY_SOURCES), label_visibility="collapsed")
    if st.session_state.policy_source != src_name:
        load_source(src_name)
    if POLICY_SOURCES[src_name] is None:
        pol = st.file_uploader("ไฟล์นโยบาย (PDF)", type="pdf", key="policy_pdf")
        if st.button("แปลงนโยบายเป็นกฎ", disabled=pol is None, width="stretch"):
            tmp = Path(tempfile.mkdtemp()) / pol.name
            tmp.write_bytes(pol.getvalue())
            with st.spinner("AI กำลังอ่านนโยบายและแยกเป็นกฎที่ตรวจได้ ..."):
                try:
                    st.session_state.rules_df = rules_to_df(extract_rules(tmp))
                except Exception as e:
                    st.error(f"{type(e).__name__}: {str(e)[:200]}")
    n_rules = int(st.session_state.rules_df["use"].sum()) if len(st.session_state.rules_df) else 0
    st.caption(f"ใช้ {n_rules} กฎ · แก้ไขได้ที่แท็บ **นโยบายบริษัท**")

    st.subheader("2 · สัญญา")
    source = st.radio("แหล่งสัญญา", ["ตัวอย่างจาก CUAD", "อัปโหลด PDF"], horizontal=True, label_visibility="collapsed")
    if source == "อัปโหลด PDF":
        upload, sample = st.file_uploader("สัญญา (PDF)", type="pdf", key="contract_pdf"), None
    else:
        upload = None
        sample = st.selectbox("เลือกสัญญาตัวอย่าง", DEV_SET,
                              format_func=lambda f: f.split("-EX-")[0][:26] + " · " + f.rsplit("-", 1)[-1][:28])

    st.subheader("3 · วิธีตรวจ")
    mode = st.radio("ระบบ", ["Agent (มีผู้ตรวจซ้ำ)", "Baseline (เรียก AI ครั้งเดียว)"], label_visibility="collapsed")
    vision = st.toggle("อ่านหน้า scan / ภาษาไทยที่อ่านไม่ออกด้วย vision model", value=True)
    st.caption(f"Model: `{config.MODEL}`")
    run = st.button("วิเคราะห์สัญญา", type="primary", width="stretch",
                    disabled=n_rules == 0 or (source == "อัปโหลด PDF" and upload is None))

tab_policy, tab_result, tab_trace = st.tabs(["① นโยบายบริษัท", "② ผลตรวจสัญญา", "③ เส้นทางการทำงานของ Agent"])

# ================= tab 1: policy =================
with tab_policy:
    st.subheader("กฎที่ใช้ตรวจสัญญา")
    st.caption("แก้ข้อความได้ทุกช่อง · ติ๊ก use เพื่อเลือกกฎ · เพิ่มแถวใหม่ที่ด้านล่างตาราง · "
               "if_absent = ถ้าสัญญาไม่มีข้อนี้ให้ถือว่าอะไร (MISSING = ต้องมี, COMPLIANT = ไม่มีก็ได้)")
    if len(st.session_state.rules_df) == 0:
        st.info("อัปโหลดนโยบายบริษัท (PDF) ทางซ้าย แล้วกด **แปลงนโยบายเป็นกฎ** หรือเพิ่มกฎเองในตารางนี้")
    edited = st.data_editor(
        st.session_state.rules_df, num_rows="dynamic", hide_index=True, width="stretch", key="rules_editor",
        column_config={
            "use": st.column_config.CheckboxColumn("use", width="small", default=True),
            "id": st.column_config.TextColumn("รหัส", width="small"),
            "title_th": st.column_config.TextColumn("หัวข้อ", width="medium"),
            "title": st.column_config.TextColumn("Topic (EN)", width="medium"),
            "text": st.column_config.TextColumn("ข้อกำหนด (ใช้ตัดสิน)", width="large"),
            "if_absent": st.column_config.SelectboxColumn("if_absent", options=["MISSING", "COMPLIANT"], width="small"),
            "keywords": st.column_config.TextColumn("คำค้น (คั่นด้วย ,)", width="medium"),
        })
    st.session_state.rules_df = edited
    st.download_button("ดาวน์โหลดกฎเป็น YAML", rules_to_yaml(df_to_rules(edited)), "company_policy_rules.yaml")

# ================= run =================
if run:
    pdf = None
    if upload is not None:
        pdf = Path(tempfile.mkdtemp()) / upload.name
        pdf.write_bytes(upload.getvalue())
    else:
        pdf = pdf_path(sample)
    active = df_to_rules(st.session_state.rules_df)
    trace = Trace(pdf.stem[:30] + ("_agent" if mode.startswith("Agent") else "_baseline"))
    t0 = time.time()
    with tab_result:
        try:
            with st.status("Agent กำลังทำงาน ...", expanded=True) as status:
                st.write("อ่านเอกสาร: ตรวจชนิดหน้า แล้วเลือกวิธีดึงข้อความ")
                pages = extract_pages(pdf, use_vision=vision, trace=trace)
                doc = ContractDocument(pdf.stem, pages)
                kinds = {k: sum(p.kind == k for p in pages) for k in ("text", "table", "scan", "pymupdf", "vision")}
                st.write(f"✓ {len(pages)} หน้า · " + ", ".join(f"{k} {v}" for k, v in kinds.items() if v)
                         + f" · แบ่งได้ {len(doc.passages)} ข้อ")
                if mode.startswith("Agent"):
                    report = review(doc, active, trace,
                                    on_step=lambda r: st.write(f"ตรวจ {r['id']} {r.get('title_th', r['title'])} ..."))
                else:
                    st.write("ส่งสัญญาทั้งฉบับให้ AI ครั้งเดียว (baseline)")
                    report = review_single_call(pdf, doc, active, trace)
                status.update(label=f"เสร็จใน {time.time() - t0:.0f} วินาที · ดูผลด้านล่าง", state="complete",
                              expanded=False)
        except Exception as e:
            st.error(f"{type(e).__name__}: {str(e)[:300]}")
            st.stop()
    _, xlsx = save(report, config.OUTPUT_DIR, trace.run_name)
    trace.save()
    st.session_state.result = {"report": report, "totals": trace.totals, "records": trace.records,
                               "xlsx": xlsx.read_bytes(), "xlsx_name": xlsx.name, "mode": mode,
                               "seconds": time.time() - t0, "rules": active}

res = st.session_state.get("result")

# ================= tab 2: results =================
with tab_result:
    if not res:
        st.info("1) ตรวจกฎในแท็บ **นโยบายบริษัท**  2) เลือกสัญญาทางซ้าย  3) กด **วิเคราะห์สัญญา** "
                "· agent ใช้เวลาประมาณ 1–3 นาทีต่อสัญญา")
    else:
        report, totals = res["report"], res["totals"]
        c = report.counts
        st.header(report.contract_title.split("-EX-")[0][:60])
        st.caption(f"{res['mode']} · {totals['llm_calls']} AI calls · {res['seconds']:.0f} วินาที · "
                   f"{totals['tokens_in'] + totals['tokens_out']:,} tokens · ~${totals['cost_usd']:.3f}")
        k = st.columns(5)
        k[0].metric("หัวข้อที่ตรวจ", c["total"])
        k[1].metric("ความเสี่ยงสูง", c["high"])
        k[2].metric("ความเสี่ยงปานกลาง", c["medium"])
        k[3].metric("ข้อที่ขาดหายไป", c["missing"])
        k[4].metric("ผ่านผู้ตรวจซ้ำ", f"{c['verified']}/{c['total']}")
        (st.warning if c["high"] else st.success)(f"**สรุปสำหรับผู้บริหาร:** {report.executive_summary}")

        df = to_frame(report)
        f1, f2 = st.columns([3, 1])
        show = f1.multiselect("กรองสถานะ", list(STATUS_COLOR), default=list(STATUS_COLOR))
        f2.download_button("ดาวน์โหลด Excel", res["xlsx"], res["xlsx_name"], width="stretch")
        st.dataframe(df[df["status"].isin(show)][["policy", "category", "status", "risk", "reference", "verified"]],
                     hide_index=True, width="stretch",
                     column_config={"policy": "กฎ", "category": "หัวข้อ", "status": "สถานะ", "risk": "ความเสี่ยง",
                                    "reference": "อ้างอิงในสัญญา", "verified": "ผู้ตรวจซ้ำ"})

        st.subheader("รายละเอียดรายข้อ")
        for r in report.findings:
            f = r.finding
            if f.compliance_status not in show:
                continue
            with st.expander(f"{STATUS_ICON[f.compliance_status]} {f.policy_id} · {f.clause_category} — "
                             f"{f.compliance_status} / {f.risk_level}", expanded=f.risk_level == "HIGH"):
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
                    if f.risk_level == "HIGH" or not r.verified:
                        st.radio("การตรวจทานโดยฝ่ายกฎหมาย (human-in-the-loop)", REVIEW_OPTIONS, horizontal=True,
                                 key=f"hitl_{f.policy_id}")

# ================= tab 3: agent trace =================
with tab_trace:
    if not res:
        st.info("หลังวิเคราะห์สัญญา แท็บนี้จะแสดงทุกขั้นที่ agent ทำ: ค้นอะไร อ่านข้อไหน ส่งคำตอบกี่ครั้ง "
                "และผู้ตรวจซ้ำส่งกลับเพราะอะไร")
    else:
        recs = res["records"]
        llm = [x for x in recs if x["type"] == "llm"]
        st.markdown("**วงจรของ agent ต่อกฎ 1 ข้อ:** ค้น (search) → อ่าน (read) → ส่งคำตอบ (submit) → "
                    "ผู้ตรวจซ้ำตรวจด้วยโค้ด → ไม่ผ่านส่งกลับพร้อมเหตุผล · ผ่านเข้ารายงาน")
        t = st.columns(4)
        t[0].metric("AI calls ทั้งหมด", len(llm))
        t[1].metric("เวลารอ AI", f"{sum(x['sec'] for x in llm):.0f} วินาที")
        t[2].metric("ถูกส่งกลับโดยผู้ตรวจซ้ำ", sum(1 for x in recs if x["type"] == "verify" and not x["ok"]))
        t[3].metric("Retry เพราะ Gemini ไม่ว่าง", sum(1 for x in recs if x["type"] == "retry"))
        for r in res["report"].findings:
            f = r.finding
            verifies = [x for x in recs if x["type"] == "verify" and x["rule"] == f.policy_id]
            with st.expander(f"{f.policy_id} · {f.clause_category} — {r.steps} AI calls, ส่งกลับ {r.rejections} ครั้ง"):
                for i, call in enumerate(r.tool_calls, 1):
                    st.markdown(f"`{i:>2}` {call}")
                for v in verifies:
                    if v["ok"]:
                        st.success("ผู้ตรวจซ้ำ: ผ่าน" + (f" (ข้อความตรง {v['score']:.0f}/100)" if v.get("score") else ""))
                    else:
                        st.warning(f"ผู้ตรวจซ้ำ: ส่งกลับ — {v['feedback']}")
        with st.expander("Log ทุก AI call (tokens / เวลา)"):
            st.dataframe(pd.DataFrame(llm), hide_index=True, width="stretch")
