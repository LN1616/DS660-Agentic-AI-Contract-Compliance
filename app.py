"""Step 7 - Streamlit interface for the Contract Compliance Agent (Thai / English).

Full loop:  company policy (sample / upload PDF) -> editable rules -> contract -> agent -> report + legal review
Run:  streamlit run app.py
"""
import re
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
from eval.cuad import available, pdf_path
from src import ui
from src.schemas import ContractAuditReport

st.set_page_config(page_title="Contract Compliance Agent", page_icon="§", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)

# ---------------- text in both languages ----------------
TEXT = {
    "tagline": ("ตรวจสัญญาจัดซื้อเทียบนโยบายบริษัท", "Check supplier contracts against company policy"),
    "lang": ("ภาษา", "Language"),
    "s_policy": ("1 · นโยบายบริษัท", "1 · Company policy"),
    "src_sample_th": ("นโยบายตัวอย่างภาษาไทย (บริษัทสมมติ)", "Sample Thai company policy"),
    "src_cuad": ("นโยบายสำหรับทดสอบกับ CUAD (5 ข้อ)", "CUAD test policy (5 rules)"),
    "src_upload": ("อัปโหลดนโยบายบริษัท (PDF)", "Upload company policy (PDF)"),
    "policy_file": ("ไฟล์นโยบาย (PDF)", "Policy file (PDF)"),
    "extract_btn": ("แปลงนโยบายเป็นกฎ", "Turn policy into rules"),
    "extracting": ("AI กำลังอ่านนโยบายและแยกเป็นกฎที่ตรวจได้ ...", "AI is reading the policy and extracting checkable rules ..."),
    "rules_used": ("ใช้ {n} กฎ · แก้ไขได้ที่แท็บ **นโยบายบริษัท**", "{n} rules in use · edit them in the **Company policy** tab"),
    "s_contract": ("2 · สัญญา", "2 · Contract"),
    "c_sample": ("ตัวอย่างจาก CUAD", "CUAD sample"),
    "c_upload": ("อัปโหลด PDF", "Upload PDF"),
    "no_samples": ("ไม่พบสัญญาตัวอย่าง จึงใช้ได้เฉพาะอัปโหลด PDF", "No sample contracts found, upload a PDF"),
    "contract_file": ("สัญญา (PDF)", "Contract (PDF)"),
    "pick_sample": ("เลือกสัญญาตัวอย่าง", "Choose a sample contract"),
    "s_method": ("3 · วิธีตรวจ", "3 · Method"),
    "m_agent": ("Agent (มีผู้ตรวจซ้ำ)", "Agent (with verifier)"),
    "m_baseline": ("Baseline (เรียก AI ครั้งเดียว)", "Baseline (single AI call)"),
    "vision": ("อ่านหน้า scan / ภาษาไทยที่อ่านไม่ออกด้วย vision model", "Read scanned or garbled pages with a vision model"),
    "run": ("วิเคราะห์สัญญา", "Analyse contract"),
    "tab_policy": ("① นโยบายบริษัท", "① Company policy"),
    "tab_result": ("② ผลตรวจสัญญา", "② Review results"),
    "tab_trace": ("③ เส้นทางการทำงานของ Agent", "③ Agent trace"),
    "rules_title": ("กฎที่ใช้ตรวจสัญญา", "Rules used to check the contract"),
    "rules_help": ("แก้ข้อความได้ทุกช่อง · ติ๊ก use เพื่อเลือกกฎ · เพิ่มแถวใหม่ที่ด้านล่างตาราง · "
                   "if_absent = ถ้าสัญญาไม่มีข้อนี้ให้ถือว่าอะไร (MISSING = ต้องมี, COMPLIANT = ไม่มีก็ได้)",
                   "Every cell is editable · tick use to include a rule · add rows at the bottom · "
                   "if_absent = status when the contract has no such clause (MISSING = required, COMPLIANT = optional)"),
    "rules_empty": ("อัปโหลดนโยบายบริษัท (PDF) ทางซ้าย แล้วกด **แปลงนโยบายเป็นกฎ** หรือเพิ่มกฎเองในตารางนี้",
                    "Upload a company policy (PDF) on the left and press **Turn policy into rules**, or add rules in this table"),
    "col_id": ("รหัส", "ID"), "col_title": ("หัวข้อ", "Topic"), "col_text": ("ข้อกำหนด (ใช้ตัดสิน)", "Requirement (used to judge)"),
    "col_kw": ("คำค้น (คั่นด้วย ,)", "Search words (comma-separated)"),
    "dl_yaml": ("ดาวน์โหลดกฎเป็น YAML", "Download rules as YAML"),
    "working": ("Agent กำลังทำงาน ...", "Agent is working ..."),
    "reading": ("อ่านเอกสาร: ตรวจชนิดหน้า แล้วเลือกวิธีดึงข้อความ", "Reading the document: checking each page and choosing how to extract it"),
    "pages": ("✓ {n} หน้า · {kinds} · แบ่งได้ {p} ข้อ", "✓ {n} pages · {kinds} · {p} passages"),
    "checking": ("ตรวจ {id} {title} ...", "Checking {id} {title} ..."),
    "single": ("ส่งสัญญาทั้งฉบับให้ AI ครั้งเดียว (baseline)", "Sending the whole contract to the AI in one call (baseline)"),
    "done": ("เสร็จใน {s} วินาที · ดูผลด้านล่าง", "Done in {s} s · results below"),
    "start_hint": ("1) ตรวจกฎในแท็บ **นโยบายบริษัท**  2) เลือกสัญญาทางซ้าย  3) กด **วิเคราะห์สัญญา** · ใช้เวลาประมาณ 1–3 นาทีต่อสัญญา",
                   "1) Check the rules in the **Company policy** tab  2) Choose a contract on the left  3) Press **Analyse contract** · about 1–3 minutes per contract"),
    "lang_note": ("ข้อความจาก AI อยู่ในภาษาที่ใช้ตอนวิเคราะห์ กดวิเคราะห์ใหม่เพื่อเปลี่ยนภาษา",
                  "AI-written text stays in the language used for the run. Analyse again to change it."),
    "seconds": ("วินาที", "s"),
    "k_total": ("หัวข้อที่ตรวจ", "Rules checked"), "k_high": ("ความเสี่ยงสูง", "High risk"),
    "k_med": ("ความเสี่ยงปานกลาง", "Medium risk"), "k_miss": ("ข้อที่ขาดหายไป", "Missing clauses"),
    "k_ver": ("ผ่านผู้ตรวจซ้ำ", "Passed verifier"),
    "summary": ("สรุปสำหรับผู้บริหาร", "Executive summary"),
    "filter": ("กรองสถานะ", "Filter by status"),
    "dl_xlsx": ("ดาวน์โหลด Excel", "Download Excel"),
    "t_rule": ("กฎ", "Rule"), "t_topic": ("หัวข้อ", "Topic"), "t_status": ("สถานะ", "Status"),
    "t_risk": ("ความเสี่ยง", "Risk"), "t_ref": ("อ้างอิงในสัญญา", "Contract reference"), "t_ver": ("ผู้ตรวจซ้ำ", "Verifier"),
    "details": ("รายละเอียดรายข้อ", "Details by rule"),
    "contract_text": ("ข้อความในสัญญา", "Contract text"),
    "not_found": ("ไม่พบข้อความเกี่ยวกับหัวข้อนี้ในสัญญา", "No clause on this topic was found in the contract"),
    "ver_found": ("ผู้ตรวจซ้ำ: พบข้อความนี้จริงในหน้า {p} (ตรง {s}/100)", "Verifier: quote found on page {p} (match {s}/100)"),
    "ver_missing": ("ผู้ตรวจซ้ำ: อ่านข้อที่เกี่ยวข้องครบแล้วก่อนสรุปว่าไม่มี", "Verifier: relevant passages were read before concluding MISSING"),
    "ver_fail": ("ผู้ตรวจซ้ำไม่ผ่าน: ต้องให้คนตรวจข้อนี้เอง", "Verifier failed: a person must check this item"),
    "issue": ("ประเด็น", "Issue"), "action": ("สิ่งที่ต้องทำ", "Action required"),
    "redline": ("ข้อเสนอแก้ไข (redline)", "Suggested redline"),
    "hitl": ("การตรวจทานโดยฝ่ายกฎหมาย (human-in-the-loop)", "Legal review (human-in-the-loop)"),
    "r_wait": ("รอ legal อนุมัติ", "Waiting for legal"), "r_ok": ("อนุมัติข้อเสนอแก้ไข", "Approve redline"),
    "r_back": ("ส่งกลับให้ตรวจใหม่", "Send back for re-check"),
    "trace_hint": ("หลังวิเคราะห์สัญญา แท็บนี้จะแสดงทุกขั้นที่ agent ทำ: ค้นอะไร อ่านข้อไหน ส่งคำตอบกี่ครั้ง และผู้ตรวจซ้ำส่งกลับเพราะอะไร",
                   "After a run, this tab shows every agent step: what it searched, which passages it read, how often it submitted, and why the verifier sent answers back"),
    "loop": ("**วงจรของ agent ต่อกฎ 1 ข้อ:** ค้น (search) → อ่าน (read) → ส่งคำตอบ (submit) → ผู้ตรวจซ้ำตรวจด้วยโค้ด → ไม่ผ่านส่งกลับพร้อมเหตุผล · ผ่านเข้ารายงาน",
             "**Agent loop per rule:** search → read → submit → verifier checks with code → rejected answers go back with a reason · accepted answers go into the report"),
    "m_calls": ("AI calls ทั้งหมด", "Total AI calls"), "m_wait": ("เวลารอ AI", "Time waiting for AI"),
    "m_back": ("ถูกส่งกลับโดยผู้ตรวจซ้ำ", "Sent back by verifier"), "m_retry": ("Retry เพราะ Gemini ไม่ว่าง", "Retries (Gemini busy)"),
    "trace_row": ("{id} · {cat} — {n} AI calls, ส่งกลับ {r} ครั้ง", "{id} · {cat} — {n} AI calls, sent back {r} times"),
    "v_ok": ("ผู้ตรวจซ้ำ: ผ่าน", "Verifier: passed"), "v_score": (" (ข้อความตรง {s}/100)", " (quote match {s}/100)"),
    "v_back": ("ผู้ตรวจซ้ำ: ส่งกลับ — {f}", "Verifier: sent back — {f}"),
    "log": ("Log ทุก AI call (tokens / เวลา)", "Log of every AI call (tokens / time)"),
}

st.session_state.setdefault("lang", "th")
st.session_state.setdefault("policy_source", None)


def t(key: str, **kw) -> str:
    s = TEXT[key][0 if st.session_state.lang == "th" else 1]
    return s.format(**kw) if kw else s


STATUS_COLOR = {"COMPLIANT": "green", "DEVIATED": "orange", "VIOLATED": "red", "MISSING": "gray"}
RISK_COLOR = {"HIGH": "red", "MEDIUM": "orange", "LOW": "gray"}
STATUS_ICON = {"COMPLIANT": "✅", "DEVIATED": "🟠", "VIOLATED": "🔴", "MISSING": "⚪"}
POLICY_SOURCES = {"src_sample_th": config.ROOT / "data" / "sample_company_policy_th.yaml",
                  "src_cuad": config.PLAYBOOK_PATH, "src_upload": None}
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


def label_fn(lang: str):
    """Option-label function fixed to one language (so a widget's labels never change under it)."""
    i = 0 if lang == "th" else 1
    return lambda key: TEXT[key][i]


def pick(widget, name: str, options: list, **kw):
    """A choice that survives a language switch: the widget is per-language, the choice is stored separately."""
    saved = st.session_state.get(f"choice_{name}")
    idx = options.index(saved) if saved in options else 0
    val = widget(name, options, index=idx, key=f"{name}_{st.session_state.lang}", **kw)
    st.session_state[f"choice_{name}"] = val
    return val


def rule_title(r: dict) -> str:
    return r.get("title_th") if st.session_state.lang == "th" and r.get("title_th") else r.get("title", "")


# ================= sidebar =================
with st.sidebar:
    st.radio(t("lang"), ["th", "en"], horizontal=True, key="lang",
             format_func=lambda x: {"th": "ไทย", "en": "English"}[x])
    st.caption(t("tagline"))

    st.subheader(t("s_policy"))
    src_key = pick(st.selectbox, "policy", list(POLICY_SOURCES), format_func=label_fn(st.session_state.lang), label_visibility="collapsed")
    if st.session_state.policy_source != src_key:
        path = POLICY_SOURCES[src_key]
        st.session_state.rules_df = (rules_to_df(yaml.safe_load(path.read_text(encoding="utf-8"))["rules"])
                                     if path else pd.DataFrame(columns=COLS))
        st.session_state.policy_source = src_key
    if POLICY_SOURCES[src_key] is None:
        pol = st.file_uploader(t("policy_file"), type="pdf", key="policy_pdf")
        if st.button(t("extract_btn"), disabled=pol is None, width="stretch"):
            tmp = Path(tempfile.mkdtemp()) / pol.name
            tmp.write_bytes(pol.getvalue())
            with st.spinner(t("extracting")):
                try:
                    st.session_state.rules_df = rules_to_df(extract_rules(tmp))
                except Exception as e:
                    st.error(f"{type(e).__name__}: {str(e)[:200]}")
    n_rules = int(st.session_state.rules_df["use"].sum()) if len(st.session_state.rules_df) else 0
    st.caption(t("rules_used", n=n_rules))

    st.subheader(t("s_contract"))
    samples = available(DEV_SET)
    source = pick(st.radio, "contract", ["c_sample", "c_upload"] if samples else ["c_upload"], format_func=label_fn(st.session_state.lang),
                  horizontal=True, label_visibility="collapsed")
    if not samples:
        st.caption(t("no_samples"))
    if source == "c_upload":
        upload, sample = st.file_uploader(t("contract_file"), type="pdf", key="contract_pdf"), None
    else:
        upload = None
        sample = pick(st.selectbox, "sample", samples, label_visibility="collapsed",
                      format_func=lambda f: f.split("-EX-")[0][:26] + " · " + f.rsplit("-", 1)[-1][:28])

    st.subheader(t("s_method"))
    mode = pick(st.radio, "method", ["m_agent", "m_baseline"], format_func=label_fn(st.session_state.lang), label_visibility="collapsed")
    vision = st.toggle(t("vision"), value=True)
    st.caption(f"Model: `{config.MODEL}`")
    run = st.button(t("run"), type="primary", width="stretch",
                    disabled=n_rules == 0 or (source == "c_upload" and upload is None))


TEXT.update({
    "tab_dash": ("② แดชบอร์ด", "② Dashboard"),
    "tab_view": ("③ เปิดดูสัญญา", "③ Contract viewer"),
    "tab_trace": ("④ เส้นทาง Agent", "④ Agent trace"),
    "tab_port": ("⑤ สัญญาทั้งหมด", "⑤ Portfolio"),
    "app_sub": ("ตรวจสัญญาจัดซื้อเทียบนโยบายบริษัท", "Supplier contract review against company policy"),
    "st_policy": ("นโยบาย", "Policy"), "st_contract": ("สัญญา", "Contract"),
    "st_ai": ("AI ตรวจ", "AI review"), "st_legal": ("ฝ่ายกฎหมาย", "Legal review"),
    "k_score": ("คะแนนความสอดคล้อง", "Compliance score"),
    "k_score_help": ("สัดส่วนกฎที่ผ่าน (COMPLIANT)", "Share of rules that are COMPLIANT"),
    "k_cost": ("ต้นทุนต่อสัญญา", "Cost per contract"),
    "split_title": ("ผลตรวจแยกตามสถานะ", "Findings by status"),
    "map_title": ("แผนที่สัญญา: ข้อที่ตรวจอยู่หน้าไหน", "Contract map: where each finding sits"),
    "map_note": ("แต่ละช่องคือ 1 หน้า จุดสีคือข้อที่พบในหน้านั้น ชี้เมาส์เพื่อดูชื่อ", "Each tile is a page; a dot is a finding on that page. Hover for its name"),
    "effort_title": ("แรงที่ agent ใช้ต่อกฎ", "Agent effort per rule"),
    "effort_note": ("จำนวน AI calls ต่อกฎ · ↺ = ผู้ตรวจซ้ำส่งกลับ", "AI calls per rule · ↺ = sent back by the verifier"),
    "sent_back": ("ครั้งที่ถูกส่งกลับ", "send-backs"),
    "findings": ("ผลตรวจรายข้อ", "Findings"),
    "open_viewer": ("ดูในสัญญา →", "Open in contract →"),
    "v_pick": ("เลือกข้อที่ต้องการดู", "Choose a finding"),
    "v_page": ("หน้า", "Page"),
    "v_all": ("ไฮไลต์ทุกข้อในหน้านี้", "Highlight every finding on this page"),
    "v_nohl": ("ไม่พบตำแหน่งข้อความในหน้านี้ (เช่น MISSING หรือเอกสารสแกน)", "No highlight on this page (e.g. MISSING, or a scanned page)"),
    "v_none": ("วิเคราะห์สัญญาก่อน แล้วเปิดดูสัญญาพร้อมไฮไลต์ได้ที่นี่", "Analyse a contract first, then view it here with highlights"),
    "p_title": ("สัญญาที่ตรวจแล้วทั้งหมด", "All reviewed contracts"),
    "p_note": ("รวมจากทุกครั้งที่กดวิเคราะห์ (โฟลเดอร์ outputs)", "Every run saved in the outputs folder"),
    "p_empty": ("ยังไม่มีสัญญาที่ตรวจแล้ว", "No reviewed contracts yet"),
    "p_contract": ("สัญญา", "Contract"), "p_when": ("เมื่อ", "When"), "p_mode": ("วิธี", "Method"),
    "p_split": ("สถานะ", "Status split"), "p_high": ("เสี่ยงสูง", "High"), "p_miss": ("ขาด", "Missing"),
    "p_ver": ("ผ่านผู้ตรวจซ้ำ", "Verified"),
    "status_names": ("ผ่าน|เบี่ยงเล็กน้อย|ขัดนโยบาย|ไม่มีข้อนี้", "Compliant|Deviated|Violated|Missing"),
})


def status_labels() -> dict:
    return dict(zip(STATUS_COLOR, t("status_names").split("|")))


def finding_page(r) -> int | None:
    if r.verified_page:
        return r.verified_page
    m = re.search(r"(?:page|หน้า|p\.)\s*(\d+)", r.finding.clause_reference, re.I)
    return int(m.group(1)) if m else None


@st.cache_data(show_spinner=False, max_entries=64)
def page_png(pdf: str, page: int, highlights: tuple) -> bytes:
    return ui.render_page(pdf, page, highlights)


def load_demo():
    """?demo=1 -> show the latest saved agent review of a sample contract, without calling the AI."""
    import json
    import pymupdf
    for fp in sorted(config.OUTPUT_DIR.glob("*_agent.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        rep = ContractAuditReport.model_validate_json(fp.read_text(encoding="utf-8"))
        try:
            pdf = pdf_path(rep.contract_title + ".pdf")
        except KeyError:
            continue
        doc = ContractDocument(pdf.stem, extract_pages(pdf, use_vision=False))
        for r in rep.findings:  # page attribution with the current verifier
            if r.finding.extracted_text.strip():
                r.verified_page, r.quote_score = doc.find_quote(r.finding.extracted_text)
        traces = sorted(config.TRACE_DIR.glob(f"*{fp.stem}*.json"))
        data = json.loads(traces[-1].read_text(encoding="utf-8")) if traces else {}
        records = data.get("records", [])
        totals = data.get("totals", {"llm_calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0})
        xlsx = fp.with_suffix(".xlsx")
        return {"report": rep, "totals": totals, "records": records,
                "xlsx": xlsx.read_bytes() if xlsx.exists() else b"", "xlsx_name": xlsx.name, "mode": "m_agent",
                "seconds": sum(x.get("sec", 0) for x in records if x["type"] == "llm"), "lang": "th",
                "pdf": str(pdf), "n_pages": len(pymupdf.open(pdf))}
    return None


if "demo" in st.query_params and "result" not in st.session_state:
    demo = load_demo()
    if demo:
        st.session_state.result = demo

res = None  # set after a run or from session

# ================= header with progress =================
_res = st.session_state.get("result")
_legal_done = bool(_res) and all(
    st.session_state.get(f"hitl_{r.finding.policy_id}") == "r_ok"
    for r in _res["report"].findings if r.finding.risk_level == "HIGH" or not r.verified)
_steps = [(t("st_policy"), "done" if n_rules else "now"),
          (t("st_contract"), "done" if _res else ("now" if n_rules else "")),
          (t("st_ai"), "done" if _res else ""),
          (t("st_legal"), "done" if _legal_done else ("now" if _res else ""))]
_title = _res["report"].contract_title.split("-EX-")[0][:60] if _res else "Contract Compliance Agent"
st.html(ui.header(_title, t("app_sub"), _steps))

tab_policy, tab_dash, tab_view, tab_trace, tab_port = st.tabs(
    [t("tab_policy"), t("tab_dash"), t("tab_view"), t("tab_trace"), t("tab_port")])

# ================= tab 1: policy =================
with tab_policy:
    st.subheader(t("rules_title"))
    st.caption(t("rules_help"))
    if len(st.session_state.rules_df) == 0:
        st.info(t("rules_empty"))
    edited = st.data_editor(
        st.session_state.rules_df, num_rows="dynamic", hide_index=True, width="stretch", key="rules_editor",
        column_config={
            "use": st.column_config.CheckboxColumn("use", width="small", default=True),
            "id": st.column_config.TextColumn(t("col_id"), width="small"),
            "title_th": st.column_config.TextColumn(t("col_title") + " (TH)", width="medium"),
            "title": st.column_config.TextColumn(t("col_title") + " (EN)", width="medium"),
            "text": st.column_config.TextColumn(t("col_text"), width="large"),
            "if_absent": st.column_config.SelectboxColumn("if_absent", options=["MISSING", "COMPLIANT"], width="small"),
            "keywords": st.column_config.TextColumn(t("col_kw"), width="medium"),
        })
    st.session_state.rules_df = edited
    st.download_button(t("dl_yaml"), rules_to_yaml(df_to_rules(edited)), "company_policy_rules.yaml")

# ================= run =================
if run:
    if upload is not None:
        pdf = Path(tempfile.mkdtemp()) / upload.name
        pdf.write_bytes(upload.getvalue())
    else:
        pdf = pdf_path(sample)
    active = df_to_rules(st.session_state.rules_df)
    lang = st.session_state.lang
    trace = Trace(pdf.stem[:30] + ("_agent" if mode == "m_agent" else "_baseline"))
    t0 = time.time()
    with tab_dash:
        try:
            with st.status(t("working"), expanded=True) as status:
                st.write(t("reading"))
                pages = extract_pages(pdf, use_vision=vision, trace=trace)
                doc = ContractDocument(pdf.stem, pages)
                kinds = {k: sum(p.kind == k for p in pages) for k in ("text", "table", "scan", "pymupdf", "vision")}
                st.write(t("pages", n=len(pages), kinds=", ".join(f"{k} {v}" for k, v in kinds.items() if v),
                           p=len(doc.passages)))
                if mode == "m_agent":
                    report = review(doc, active, trace, lang=lang,
                                    on_step=lambda r: st.write(t("checking", id=r["id"], title=rule_title(r))))
                else:
                    st.write(t("single"))
                    report = review_single_call(pdf, doc, active, trace, lang=lang)
                status.update(label=t("done", s=f"{time.time() - t0:.0f}"), state="complete", expanded=False)
        except Exception as e:
            st.error(f"{type(e).__name__}: {str(e)[:300]}")
            st.stop()
    _, xlsx = save(report, config.OUTPUT_DIR, trace.run_name)
    trace.save()
    for k in [k for k in st.session_state if str(k).startswith("hitl_")]:
        del st.session_state[k]
    st.session_state.result = {"report": report, "totals": trace.totals, "records": trace.records,
                               "xlsx": xlsx.read_bytes(), "xlsx_name": xlsx.name, "mode": mode,
                               "seconds": time.time() - t0, "lang": lang, "pdf": str(pdf), "n_pages": len(pages)}
    st.rerun()

res = st.session_state.get("result")

# ================= tab 2: dashboard =================
with tab_dash:
    if not res:
        st.info(t("start_hint"))
    else:
        report, totals = res["report"], res["totals"]
        c = report.counts
        findings = report.findings
        n = len(findings) or 1
        st.caption(f"{t(res['mode'])} · {totals['llm_calls']} AI calls · "
                   f"{totals['tokens_in'] + totals['tokens_out']:,} tokens · `{config.MODEL}`")
        if res.get("lang", "th") != st.session_state.lang:
            st.caption(t("lang_note"))
        k = st.columns(5)
        compliant = sum(r.finding.compliance_status == "COMPLIANT" for r in findings)
        k[0].metric(t("k_score"), f"{100 * compliant / n:.0f}%", help=t("k_score_help"))
        k[1].metric(t("k_high"), c["high"])
        k[2].metric(t("k_miss"), c["missing"])
        k[3].metric(t("k_ver"), f"{c['verified']}/{c['total']}")
        k[4].metric(t("k_cost"), f"${totals['cost_usd']:.3f}", help=f"{res['seconds']:.0f} {t('seconds')} · {totals['llm_calls']} AI calls")
        (st.warning if c["high"] else st.success)(f"**{t('summary')}:** {report.executive_summary}")

        counts = {s: sum(r.finding.compliance_status == s for r in findings) for s in STATUS_COLOR}
        a, b = st.columns([1, 1])
        a.html(ui.status_split(counts, status_labels(), t("split_title")))
        a.html(ui.effort_bars([(f"{r.finding.policy_id} {r.finding.clause_category}"[:34], r.steps, r.rejections)
                               for r in findings], t("effort_title"), t("effort_note"), t("sent_back")))
        marks = [(finding_page(r), r.finding.compliance_status, f"{r.finding.policy_id} {r.finding.clause_category}")
                 for r in findings if finding_page(r)]
        b.html(ui.page_map(res.get("n_pages") or max([m[0] for m in marks] + [1]), marks, t("map_title"), t("map_note")))

        st.subheader(t("findings"))
        f1, f2 = st.columns([3, 1])
        show = f1.multiselect(t("filter"), list(STATUS_COLOR), default=list(STATUS_COLOR))
        f2.download_button(t("dl_xlsx"), res["xlsx"], res["xlsx_name"], width="stretch")
        rows = "".join(
            f"<tr><td><b>{ui.esc(r.finding.policy_id)}</b></td><td>{ui.esc(r.finding.clause_category)}</td>"
            f"<td>{ui.chip(r.finding.compliance_status)}</td><td>{ui.risk_chip(r.finding.risk_level)}</td>"
            f"<td class='cc-muted'>{ui.esc(r.finding.clause_reference)}</td>"
            f"<td>{'✓ p.' + str(r.verified_page) if r.verified and r.verified_page else ('✓' if r.verified else '✕')}</td></tr>"
            for r in findings if r.finding.compliance_status in show)
        st.html(f"<div class='cc-card'><table class='cc-table'><tr><th>{t('t_rule')}</th><th>{t('t_topic')}</th>"
                f"<th>{t('t_status')}</th><th>{t('t_risk')}</th><th>{t('t_ref')}</th><th>{t('t_ver')}</th></tr>{rows}</table></div>")

        st.subheader(t("details"))
        for r in findings:
            f = r.finding
            if f.compliance_status not in show:
                continue
            with st.expander(f"{STATUS_ICON[f.compliance_status]} {f.policy_id} · {f.clause_category} — "
                             f"{f.compliance_status} / {f.risk_level}", expanded=f.risk_level == "HIGH"):
                left, right = st.columns(2)
                with left:
                    st.html(ui.chip(f.compliance_status) + " " + ui.risk_chip(f.risk_level))
                    st.markdown(f"**{t('contract_text')}** · {f.clause_reference}")
                    st.html(f"<div class='cc-quote'>{ui.esc(f.extracted_text or t('not_found'))}</div>")
                    if r.verified and r.verified_page:
                        st.success(t("ver_found", p=r.verified_page, s=f"{r.quote_score:.0f}"))
                    elif r.verified:
                        st.success(t("ver_missing"))
                    else:
                        st.error(t("ver_fail"))
                with right:
                    st.markdown(f"**{t('issue')}**  \n{f.issue_description}")
                    st.markdown(f"**{t('action')}**  \n{f.action_required}")
                    if f.suggested_redline:
                        st.markdown(f"**{t('redline')}**")
                        st.code(f.suggested_redline, language=None, wrap_lines=True)
                    if f.risk_level == "HIGH" or not r.verified:
                        st.radio(t("hitl"), ["r_wait", "r_ok", "r_back"], format_func=label_fn(st.session_state.lang),
                                 horizontal=True, key=f"hitl_{f.policy_id}")

# ================= tab 3: contract viewer =================
with tab_view:
    if not res or not res.get("pdf") or not Path(res["pdf"]).exists():
        st.info(t("v_none"))
    else:
        findings = res["report"].findings
        n_pages = res.get("n_pages") or 1
        left, mid, right = st.columns([1.05, 3.1, 1.45])
        with left:
            ids = [r.finding.policy_id for r in findings]
            sel = st.radio(t("v_pick"), ids, key="viewer_pick",
                           format_func=lambda i: next(f"{STATUS_ICON[r.finding.compliance_status]} {i} · "
                                                      f"{r.finding.clause_category}" for r in findings
                                                      if r.finding.policy_id == i))
            chosen = next(r for r in findings if r.finding.policy_id == sel)
            default_page = finding_page(chosen) or 1
            page = st.number_input(t("v_page"), 1, n_pages, value=min(default_page, n_pages), key=f"viewer_page_{sel}")
            show_all = st.toggle(t("v_all"), value=True)
        with mid:
            targets = [r for r in findings if finding_page(r) == page and (show_all or r is chosen)]
            hl = tuple((r.finding.extracted_text, r.finding.compliance_status, r.finding.policy_id) for r in targets)
            st.image(page_png(res["pdf"], int(page), hl), width="stretch")
            if not any(h[0] for h in hl):
                st.caption(t("v_nohl"))
        with right:
            f = chosen.finding
            st.html(f"<div class='cc-card'><div class='cc-label'>{ui.esc(f.policy_id)} · {ui.esc(f.clause_category)}</div>"
                    f"<div style='margin:8px 0'>{ui.chip(f.compliance_status)} {ui.risk_chip(f.risk_level)}</div>"
                    f"<div class='cc-muted'>{ui.esc(f.clause_reference)}</div></div>")
            st.markdown(f"**{t('issue')}**  \n{f.issue_description}")
            st.markdown(f"**{t('action')}**  \n{f.action_required}")
            if f.suggested_redline:
                st.markdown(f"**{t('redline')}**")
                st.code(f.suggested_redline, language=None, wrap_lines=True)

# ================= tab 4: agent trace =================
with tab_trace:
    if not res:
        st.info(t("trace_hint"))
    else:
        recs = res["records"]
        llm = [x for x in recs if x["type"] == "llm"]
        st.markdown(t("loop"))
        m = st.columns(4)
        m[0].metric(t("m_calls"), len(llm))
        m[1].metric(t("m_wait"), f"{sum(x['sec'] for x in llm):.0f} {t('seconds')}")
        m[2].metric(t("m_back"), sum(1 for x in recs if x["type"] == "verify" and not x["ok"]))
        m[3].metric(t("m_retry"), sum(1 for x in recs if x["type"] == "retry"))
        for r in res["report"].findings:
            f = r.finding
            with st.expander(t("trace_row", id=f.policy_id, cat=f.clause_category, n=r.steps, r=r.rejections)):
                for i, call in enumerate(r.tool_calls, 1):
                    st.markdown(f"`{i:>2}` {call}")
                for v in [x for x in recs if x["type"] == "verify" and x["rule"] == f.policy_id]:
                    if v["ok"]:
                        st.success(t("v_ok") + (t("v_score", s=f"{v['score']:.0f}") if v.get("score") else ""))
                    else:
                        st.warning(t("v_back", f=v["feedback"]))
        with st.expander(t("log")):
            st.dataframe(pd.DataFrame(llm), hide_index=True, width="stretch")

# ================= tab 5: portfolio =================
with tab_port:
    st.subheader(t("p_title"))
    st.caption(t("p_note"))
    files = sorted(config.OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for fp in files:
        try:
            rep = ContractAuditReport.model_validate_json(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        cnt = {s: sum(r.finding.compliance_status == s for r in rep.findings) for s in STATUS_COLOR}
        rows.append(
            f"<tr><td><b>{ui.esc(rep.contract_title.split('-EX-')[0][:40])}</b></td>"
            f"<td class='cc-muted'>{time.strftime('%d %b %H:%M', time.localtime(fp.stat().st_mtime))}</td>"
            f"<td>{'Baseline' if fp.stem.endswith('baseline') else 'Agent'}</td>"
            f"<td>{ui.thin_split(cnt)}</td><td>{rep.counts['high']}</td><td>{rep.counts['missing']}</td>"
            f"<td>{rep.counts['verified']}/{rep.counts['total']}</td></tr>")
    if not rows:
        st.info(t("p_empty"))
    else:
        legend = "".join(f'<span><s style="background:{ui.STATUS[s][0]}"></s>{ui.STATUS[s][1]} {ui.esc(lbl)}</span>'
                         for s, lbl in status_labels().items())
        st.html(f"<div class='cc-card'><div class='cc-legend' style='margin-bottom:8px'>{legend}</div>"
                f"<table class='cc-table'><tr><th>{t('p_contract')}</th><th>{t('p_when')}</th><th>{t('p_mode')}</th>"
                f"<th>{t('p_split')}</th><th>{t('p_high')}</th><th>{t('p_miss')}</th><th>{t('p_ver')}</th></tr>"
                f"{''.join(rows)}</table></div>")
