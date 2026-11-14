"""Step 7 - Streamlit interface for the Contract Compliance Agent (Thai / English).

Full loop:  company policy (sample / upload PDF) -> editable rules -> contract -> agent -> report + legal review
Run:  streamlit run app.py
"""
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from src import config
from src.agent import review
from src.baseline import review_single_call
from src.criteria import (GENERAL, GROUPS_TH, context_line, criteria_for, library_to_yaml, load_library, log_change,
                          prefix_for, profile_contract, read_log, renumber, rule_usage, save_library, today, type_label)
from src.document import ContractDocument
from src.ingest import extract_pages
from src.policy import extract_rules, merge_into_library, rules_to_yaml
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
    "tagline": ("ตรวจสัญญาทุกประเภทเทียบนโยบายบริษัท", "Check any contract against your company policy"),
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
    "m_agent": ("Agent (มีตัวตรวจซ้ำ)", "Agent (with verifier)"),
    "m_baseline": ("Single call (เรียก AI ครั้งเดียว)", "Single call (one AI call)"),
    "cap_single": ("~20 วิ · ≈0.3 บาท · สัญญาสั้น", "~20 s · ≈0.3 baht · short contracts"),
    "cap_agent": ("~1–3 นาที · ≈2 บาท · ตรวจซ้ำทุกข้อ · สัญญายาว", "~1–3 min · ≈2 baht · every quote checked · long contracts"),
    "up_req": ("PDF ภาษาไทยหรืออังกฤษ · ไฟล์ข้อความหรือสแกน (สแกนให้เปิดสวิตช์ vision ด้านล่าง)",
               "Thai or English PDF · text or scanned (for scans keep the vision switch on)"),
    "up_pages": ("ไฟล์นี้ {n} หน้า", "This file has {n} pages"),
    "rec_short": ("แนะนำ Single call", "Single call recommended"),
    "rec_long": ("สัญญายาว: แนะนำลอง Agent", "Long contract: try the Agent"),
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
    "k_ver": ("ผ่านตัวตรวจซ้ำ", "Passed verifier"),
    "summary": ("สรุปสำหรับผู้บริหาร", "Executive summary"),
    "filter": ("กรองสถานะ", "Filter by status"),
    "dl_xlsx": ("ดาวน์โหลด Excel", "Download Excel"),
    "t_rule": ("กฎ", "Rule"), "t_topic": ("หัวข้อ", "Topic"), "t_status": ("สถานะ", "Status"),
    "t_risk": ("ความเสี่ยง", "Risk"), "t_ref": ("อ้างอิงในสัญญา", "Contract reference"), "t_ver": ("ตัวตรวจซ้ำ", "Verifier"),
    "details": ("รายละเอียดรายข้อ", "Details by rule"),
    "contract_text": ("ข้อความในสัญญา", "Contract text"),
    "not_found": ("ไม่พบข้อความเกี่ยวกับหัวข้อนี้ในสัญญา", "No clause on this topic was found in the contract"),
    "ver_found": ("ตัวตรวจซ้ำ: พบข้อความนี้จริงในหน้า {p} (ตรง {s}/100)", "Verifier: quote found on page {p} (match {s}/100)"),
    "ver_missing": ("ตัวตรวจซ้ำ: อ่านข้อที่เกี่ยวข้องครบแล้วก่อนสรุปว่าไม่มี", "Verifier: relevant passages were read before concluding MISSING"),
    "ver_fail": ("ตัวตรวจซ้ำไม่ผ่าน: ต้องให้คนตรวจข้อนี้เอง", "Verifier failed: a person must check this item"),
    "issue": ("ประเด็น", "Issue"), "action": ("สิ่งที่ต้องทำ", "Action required"),
    "redline": ("ข้อเสนอแก้ไข (redline)", "Suggested redline"),
    "hitl": ("การตรวจทานโดยฝ่ายกฎหมาย (human-in-the-loop)", "Legal review (human-in-the-loop)"),
    "r_wait": ("รอ legal อนุมัติ", "Waiting for legal"), "r_ok": ("อนุมัติข้อเสนอแก้ไข", "Approve redline"),
    "r_back": ("ส่งกลับให้ตรวจใหม่", "Send back for re-check"),
    "trace_hint": ("หลังวิเคราะห์สัญญา แท็บนี้จะแสดงทุกขั้นที่ agent ทำ: ค้นอะไร อ่านข้อไหน ส่งคำตอบกี่ครั้ง และตัวตรวจซ้ำส่งกลับเพราะอะไร",
                   "After a run, this tab shows every agent step: what it searched, which passages it read, how often it submitted, and why the verifier sent answers back"),
    "loop": ("**วงจรของ agent ต่อกฎ 1 ข้อ:** ค้น (search) → อ่าน (read) → ส่งคำตอบ (submit) → ตัวตรวจซ้ำตรวจด้วยโค้ด → ไม่ผ่านส่งกลับพร้อมเหตุผล · ผ่านเข้ารายงาน",
             "**Agent loop per rule:** search → read → submit → verifier checks with code → rejected answers go back with a reason · accepted answers go into the report"),
    "m_calls": ("AI calls ทั้งหมด", "Total AI calls"), "m_wait": ("เวลารอ AI", "Time waiting for AI"),
    "m_back": ("ถูกส่งกลับโดยตัวตรวจซ้ำ", "Sent back by verifier"), "m_retry": ("Retry เพราะ Gemini ไม่ว่าง", "Retries (Gemini busy)"),
    "trace_row": ("{id} · {cat} — {n} AI calls, ส่งกลับ {r} ครั้ง", "{id} · {cat} — {n} AI calls, sent back {r} times"),
    "v_ok": ("ตัวตรวจซ้ำ: ผ่าน", "Verifier: passed"), "v_score": (" (ข้อความตรง {s}/100)", " (quote match {s}/100)"),
    "v_back": ("ตัวตรวจซ้ำ: ส่งกลับ — {f}", "Verifier: sent back — {f}"),
    "log": ("Log ทุก AI call (tokens / เวลา)", "Log of every AI call (tokens / time)"),
    "pm_auto": ("อัตโนมัติ: AI ระบุประเภทสัญญา แล้วใช้นโยบายของประเภทนั้น", "Automatic: AI finds the contract type, then uses that type's policy"),
    "go_policy_lib": ("จัดการคลังนโยบาย →", "Manage policy library →"),
    "go_policy_rules": ("แก้ไขกฎ →", "Edit rules →"),
    "pm_fixed": ("กำหนดเอง: ใช้ชุดกฎเดียวกับทุกสัญญา", "Manual: one fixed rule set for every contract"),
    "lib_status": ("คลังนโยบาย: {n} ประเภทมีนโยบาย · จัดการที่แท็บ **นโยบายบริษัท**",
                   "Policy library: {n} contract types have a policy · manage it in the **Company policy** tab"),
    "lib_title": ("คลังนโยบายตามประเภทสัญญา", "Policy library by contract type"),
    "lib_help": ("Agent ระบุประเภทของสัญญาก่อน แล้วตรวจด้วยกฎ **ใช้กับทุกสัญญา** + กฎของประเภทนั้น · "
                 "ถ้าประเภทนั้นยังไม่มีนโยบาย AI จะเขียนเกณฑ์ให้ (รหัส A-xx) และบันทึกเข้าคลังได้จากแดชบอร์ด",
                 "The agent first finds the contract type, then checks **All contracts** rules + that type's rules · "
                 "if a type has no policy yet, the AI writes criteria (ids A-xx) that you can save into the library from the dashboard"),
    "lib_pick": ("เลือกประเภทสัญญาที่จะแก้ไข", "Contract type to edit"),
    "lib_count": ("{n} ข้อ", "{n} rules"), "lib_none": ("ยังไม่มี · AI จะเขียนเกณฑ์ให้", "none yet · AI writes criteria"),
    "lib_save": ("บันทึกคลังนโยบาย", "Save policy library"), "lib_saved": ("บันทึกแล้ว", "Saved"),
    "lib_dl": ("ดาวน์โหลดคลังนโยบาย (YAML)", "Download library (YAML)"),
    "lib_upload": ("เพิ่มนโยบายจาก PDF: AI แยกเป็นกฎและจัดเข้าประเภทสัญญาให้", "Add a policy PDF: AI extracts rules and files them by contract type"),
    "lib_merge": ("แปลงและเพิ่มเข้าคลัง", "Extract and add to library"),
    "lib_merged": ("เพิ่มแล้ว: {s}", "Added: {s}"),
    "lib_cloud": ("บน Streamlit Cloud การแก้ไขจะหายเมื่อแอปรีสตาร์ท ดาวน์โหลด YAML เก็บไว้",
                  "On Streamlit Cloud edits are lost when the app restarts. Download the YAML to keep them"),
    "pb_profile": ("ระบุประเภทสัญญาและเลือกนโยบายที่ตรงประเภท ...", "Identifying the contract type and choosing its policy ..."),
    "pb_profiled": ("{type} · ทั่วไป {g} ข้อ + {src} {p} ข้อ", "{type} · {g} general + {p} {src}"),
    "src_library": ("นโยบายของประเภทนี้", "type policy"), "src_ai": ("เกณฑ์ที่ AI เขียน", "AI-written criteria"),
    "pb_criteria": ("คลังยังไม่มีนโยบายสำหรับประเภทนี้ AI กำลังเขียนเกณฑ์ ...", "No policy for this type yet, the AI is writing criteria ..."),
    "prof_title": ("ประเภทสัญญาและนโยบายที่ใช้", "Contract type and policy used"),
    "prof_type": ("ประเภทสัญญา", "Contract type"), "prof_us": ("ฝ่ายเรา", "Our company"),
    "prof_them": ("คู่สัญญา", "Other party"),
    "prof_general": ("กฎที่ใช้กับทุกสัญญา {n} ข้อ", "{n} rules for all contracts"),
    "prof_lib": ("นโยบายของ{type} {n} ข้อ (จากคลังนโยบาย)", "{n} rules from the {type} policy (library)"),
    "prof_ai": ("คลังยังไม่มีนโยบายสำหรับ{type} AI เขียนเกณฑ์ {n} ข้อ", "No {type} policy in the library: the AI wrote {n} criteria"),
    "prof_ai_note": ("เกณฑ์ A-xx ไม่ได้มาจากนโยบายบริษัท ฝ่ายกฎหมายควรตรวจก่อนบันทึกเป็นนโยบาย",
                     "A-xx criteria are not company policy yet. Legal should review them before saving"),
    "prof_save": ("บันทึกเกณฑ์เหล่านี้เป็นนโยบายของ{type}", "Save these criteria as the {type} policy"),
    "prof_saved": ("บันทึกแล้ว สัญญาประเภทนี้ครั้งถัดไปจะใช้นโยบายนี้ แก้ไขได้ที่แท็บนโยบายบริษัท",
                   "Saved. The next contract of this type uses this policy; edit it in the Company policy tab"),
    "ai_tag": ("AI เขียน", "AI-written"),
    "col_draft": ("ร่าง AI", "AI draft"),
    "col_origin": ("ที่มา", "Origin"), "col_added": ("วันที่เพิ่ม", "Added"),
    "hist_title": ("ประวัติและการใช้งานของนโยบาย", "Policy history and usage"),
    "use_title": ("การใช้งานของกฎใน{type}", "How the {type} rules were used"),
    "use_note": ("นับจากผลตรวจที่บันทึกไว้ (แท็บสัญญาทั้งหมด) · กฎที่ไม่เคยเจอปัญหาเลย หรือเจอบ่อยจนทุกสัญญาไม่ผ่าน ควรทบทวน",
                 "Counted from saved reviews (Portfolio tab) · review rules that never find anything, or that fail every contract"),
    "use_rule": ("กฎ", "Rule"), "use_n": ("ใช้ตรวจ (ฉบับ)", "Contracts"), "use_last": ("ใช้ล่าสุด", "Last used"),
    "log_title": ("บันทึกการเปลี่ยนแปลง", "Change log"), "log_empty": ("ยังไม่มีการเปลี่ยนแปลง", "No changes yet"),
    "log_when": ("เวลา", "When"), "log_action": ("การเปลี่ยนแปลง", "Change"), "log_group": ("ประเภทสัญญา", "Contract type"),
    "log_detail": ("รายละเอียด", "Detail"),
    "act_ai_draft": ("AI ร่างนโยบาย", "AI draft"), "act_pdf_import": ("นำเข้าจาก PDF", "PDF import"),
    "act_edit": ("แก้ไข", "Edit"), "act_confirm": ("ยืนยันนโยบาย", "Confirmed"),
    "col_draft_help": ("ติ๊ก = AI เขียน ยังไม่ได้ยืนยัน · เอาติ๊กออกแล้วกดบันทึกเพื่อยืนยันเป็นนโยบาย",
                       "Ticked = written by AI, not confirmed yet · untick and save to confirm it as policy"),
    "lib_draft_note": ("ประเภทนี้มีกฎที่ AI ร่างไว้ {n} ข้อ ยังไม่ได้ยืนยัน · ตรวจ แก้ หรือลบได้ในตาราง แล้วกดยืนยัน",
                       "{n} rules for this type are AI drafts, not confirmed yet · review, edit or delete them, then confirm"),
    "lib_confirm": ("ยืนยันนโยบายของประเภทนี้", "Confirm this type's policy"),
    "lib_confirmed": ("ยืนยันแล้ว", "Confirmed"),
    "prof_drafted": ("บันทึกเกณฑ์เหล่านี้เป็นร่างนโยบายของ{type}ในคลังแล้ว สัญญาประเภทนี้ครั้งถัดไปจะใช้ร่างนี้ · ตรวจ แก้ และยืนยันได้ที่แท็บนโยบายบริษัท",
                     "These criteria were saved as a draft {type} policy. The next contract of this type uses it · review, edit and confirm in the Company policy tab"),
    "prof_lib_draft": ("นโยบายของ{type} {n} ข้อ (ร่างจาก AI ยังไม่ยืนยัน)", "{n} rules from the {type} policy (AI draft, not confirmed)"),
    "go_review": ("ตรวจและยืนยันนโยบาย →", "Review and confirm the policy →"),
}

st.session_state.setdefault("lang", "th")
st.session_state.setdefault("policy_source", None)
st.session_state.setdefault("rules_df", None)
if "library" not in st.session_state:
    st.session_state.library = load_library()


def current_library() -> dict:
    """The library as edited on screen (per-type tables), falling back to the saved file."""
    lib = {}
    for g in GROUPS_TH:
        df = st.session_state.get(f"libdf_{g}")
        lib[g] = df_to_rules(df) if df is not None else st.session_state.library.get(g, [])
    return {g: v for g, v in lib.items() if v}


def reset_library_tables(lib: dict) -> None:
    st.session_state.library = lib
    for k in [k for k in st.session_state if str(k).startswith(("libdf_", "lib_editor_"))]:
        del st.session_state[k]


def t(key: str, **kw) -> str:
    s = TEXT[key][0 if st.session_state.lang == "th" else 1]
    return s.format(**kw) if kw else s


STATUS_COLOR = {"COMPLIANT": "green", "DEVIATED": "orange", "VIOLATED": "red", "MISSING": "gray"}
RISK_COLOR = {"HIGH": "red", "MEDIUM": "orange", "LOW": "gray"}
STATUS_ICON = {"COMPLIANT": "✅", "DEVIATED": "🟠", "VIOLATED": "🔴", "MISSING": "⚪"}
POLICY_SOURCES = {"src_sample_th": config.ROOT / "data" / "sample_company_policy_th.yaml", "src_upload": None}
COLS = ["use", "draft", "id", "title_th", "title", "text", "if_absent", "keywords", "origin", "added"]


def rules_to_df(rules: list[dict]) -> pd.DataFrame:
    rows = [{"use": True, "draft": bool(r.get("draft")), "id": r["id"], "title_th": r.get("title_th", ""), "title": r.get("title", ""),
             "text": " ".join(str(r.get("text", "")).split()), "if_absent": r.get("if_absent", "MISSING"),
             "keywords": ", ".join(r.get("keywords", [])), "origin": r.get("origin", ""), "added": r.get("added", "")}
            for r in rules]
    return pd.DataFrame(rows, columns=COLS)


EDITED = "เพิ่มเองในแอป"
LONG_PAGES = 30  # above this, the agent is suggested (single call was tested up to ~15 pages)


@st.cache_data(show_spinner=False, max_entries=8)
def page_count(data: bytes) -> int:
    import pymupdf
    try:
        return len(pymupdf.open(stream=data, filetype="pdf"))
    except Exception:
        return 0


def df_to_rules(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        if not r["use"] or not str(r["text"]).strip():
            continue
        out.append({"id": str(r["id"]).strip() or f"P-{len(out) + 1:02d}", "title": str(r["title"] or r["title_th"]),
                    "title_th": str(r["title_th"] or r["title"]), "text": str(r["text"]),
                    "if_absent": r["if_absent"] if r["if_absent"] in ("MISSING", "COMPLIANT") else "MISSING",
                    "keywords": [k.strip() for k in str(r["keywords"]).split(",") if k.strip()],
                    "origin": str(r.get("origin") or "") if str(r.get("origin") or "") not in ("", "nan", "None") else EDITED,
                    "added": str(r.get("added") or "") if str(r.get("added") or "") not in ("", "nan", "None") else today()}
                   | ({"draft": True} if r.get("draft") is True or r.get("draft") == 1 else {}))
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
    policy_mode = pick(st.radio, "policy_mode", ["pm_auto", "pm_fixed"], format_func=label_fn(st.session_state.lang),
                       label_visibility="collapsed")
    auto = policy_mode == "pm_auto"
    if auto:
        n_types = sum(bool(v) for g, v in current_library().items() if g != GENERAL)
        st.caption(t("lib_status", n=n_types))
        st.button(t("go_policy_lib"), width="stretch", on_click=lambda: st.session_state.__setitem__("goto", "policy"))
        n_rules = 1  # the library (or the AI) always provides criteria
    else:
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
        st.button(t("go_policy_rules"), width="stretch", on_click=lambda: st.session_state.__setitem__("goto", "policy"))

    st.subheader(t("s_contract"))
    source, sample = "c_upload", None
    st.caption(t("up_req"))
    upload = st.file_uploader(t("contract_file"), type="pdf", key="contract_pdf", label_visibility="collapsed")
    n_pages = page_count(upload.getvalue()) if upload is not None else 0
    if upload is not None:
        st.caption(t("up_pages", n=n_pages) + " · " + t("rec_long" if n_pages > LONG_PAGES else "rec_short"))

    st.subheader(t("s_method"))
    mode = pick(st.radio, "method", ["m_baseline", "m_agent"], format_func=label_fn(st.session_state.lang),
                label_visibility="collapsed", captions=[t("cap_single"), t("cap_agent")])
    vision = st.toggle(t("vision"), value=True)
    st.caption(f"Model: `{config.MODEL}`")
    run = st.button(t("run"), type="primary", width="stretch",
                    disabled=n_rules == 0 or (source == "c_upload" and upload is None))


TEXT.update({
    "tab_start": ("① เริ่มต้น", "① Start"),
    "tab_dash": ("③ แดชบอร์ด", "③ Dashboard"),
    "tab_view": ("③ เปิดดูสัญญา", "③ Contract viewer"),
    "tab_trace": ("⑤ เส้นทาง Agent", "⑤ Agent trace"),
    "tab_port": ("② สัญญาทั้งหมด", "② Portfolio"),
    "tab_policy4": ("④ นโยบายบริษัท", "④ Company policy"),
    "ws_title": ("สัญญาและข้อค้นพบ", "Contract and findings"),
    "vd_block": ("ไม่ควรลงนามในสภาพนี้", "Do not sign as it stands"),
    "vd_block_sub": ("ข้อเสี่ยงสูงที่ต้องแก้ก่อนลงนาม {n} ข้อ · ไม่ตรงนโยบายทั้งหมด {m} ข้อ",
                     "{n} high-risk issues must be fixed before signing · {m} issues in total"),
    "vd_warn": ("ลงนามได้หลังเจรจาแก้ไข", "Sign after negotiating changes"),
    "vd_warn_sub": ("ไม่ตรงนโยบาย {n} ข้อ ไม่มีข้อเสี่ยงสูงที่ขัดหรือขาดหาย", "{n} issues, none high-risk violated or missing"),
    "vd_ok": ("ลงนามได้", "OK to sign"), "vd_ok_sub": ("ทุกข้อเป็นไปตามนโยบาย", "Every rule is met"),
    "vd_unver": ("ตัวตรวจซ้ำยืนยันไม่ได้ {n} ข้อ ต้องให้คนตรวจ", "{n} not confirmed by the verifier, a person must check"),
    "vd_fix": ("สิ่งที่ต้องแก้ เรียงจากเสี่ยงมากไปน้อย", "What to fix, most severe first"),
    "vd_more": ("และอีก {n} ข้อ ดูในตารางด้านล่าง", "and {n} more in the table below"),
    "summary_ai": ("สรุปสำหรับผู้บริหาร (เขียนโดย AI)", "Executive summary (written by AI)"),
    "run_meta": ("{mode} · {s} วินาที · {calls} AI calls · {tok} tokens · ต้นทุน ${cost} · {model}",
                 "{mode} · {s} s · {calls} AI calls · {tok} tokens · cost ${cost} · {model}"),
    "app_sub": ("ตรวจสัญญาทุกประเภทเทียบนโยบายบริษัทตามประเภทสัญญา", "Contract review against your company policy for each contract type"),
    "st_policy": ("นโยบาย", "Policy"), "st_contract": ("สัญญา", "Contract"),
    "st_ai": ("AI ตรวจ", "AI review"), "st_legal": ("ฝ่ายกฎหมาย", "Legal review"),
    "k_score": ("คะแนนความสอดคล้อง", "Compliance score"),
    "k_score_help": ("สัดส่วนกฎที่ผ่าน (COMPLIANT)", "Share of rules that are COMPLIANT"),
    "k_cost": ("ต้นทุนต่อสัญญา", "Cost per contract"),
    "split_title": ("ผลตรวจแยกตามสถานะ", "Findings by status"),
    "map_title": ("แผนที่สัญญา: ข้อที่ตรวจอยู่หน้าไหน", "Contract map: where each finding sits"),
    "map_note": ("แต่ละช่องคือ 1 หน้า จุดสีคือข้อที่พบในหน้านั้น ชี้เมาส์เพื่อดูชื่อ", "Each tile is a page; a dot is a finding on that page. Hover for its name"),
    "effort_title": ("แรงที่ agent ใช้ต่อกฎ", "Agent effort per rule"),
    "effort_note": ("จำนวน AI calls ต่อกฎ · ↺ = ตัวตรวจซ้ำส่งกลับ", "AI calls per rule · ↺ = sent back by the verifier"),
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
    "p_ver": ("ผ่านตัวตรวจซ้ำ", "Verified"),
    "status_names": ("ผ่าน|เบี่ยงเล็กน้อย|ขัดนโยบาย|ไม่มีข้อนี้", "Compliant|Deviated|Violated|Missing"),
    "pb_title": ("Agent กำลังตรวจสัญญา", "Agent is reviewing the contract"),
    "pb_read": ("อ่านเอกสาร: {n} หน้า · {kinds} · แบ่งได้ {p} ข้อ", "Read {n} pages · {kinds} · {p} passages"),
    "pb_reading": ("กำลังอ่านเอกสารและเลือกวิธีดึงข้อความ ...", "Reading the document and choosing how to extract each page ..."),
    "pb_wait": ("รอคิว", "waiting"), "pb_run": ("กำลังตรวจ", "checking"),
    "pb_calls": ("{n} AI calls · ส่งกลับ {r}", "{n} AI calls · sent back {r}"),
    "pb_summary": ("กำลังเขียนสรุปสำหรับผู้บริหาร ...", "Writing the executive summary ..."),
    "pb_single": ("Single call: ส่งสัญญาทั้งฉบับให้ AI ครั้งเดียว ...", "Single call: sending the whole contract in one AI call ..."),
    "skel_hint": ("ผลจะแสดงที่นี่หลังกด **วิเคราะห์สัญญา** · ระหว่างทำงานจะเห็นความคืบหน้าของ agent ทีละข้อ",
                  "Results appear here after **Analyse contract** · while it runs you see the agent's progress rule by rule"),
    "p_open": ("ดูแดชบอร์ด", "Open dashboard"),
    "p_open_pdf": ("เปิดดูสัญญา", "View contract"),
    "p_no_pdf": ("ไม่พบไฟล์ PDF ของสัญญานี้ (อาจถูกลบเมื่อแอปรีสตาร์ท)", "The PDF for this contract was not found (it may have been removed when the app restarted)"),
    "p_pick": ("เลือกผลการวิเคราะห์เก่า", "Choose a previous review"),
    "p_search": ("ค้นหา", "Search"),
    "p_search_ph": ("ชื่อสัญญา ประเภท วิธี หรือวันที่", "Contract name, type, method or date"),
    "p_click": ("คลิกแถวเพื่อเปิด", "Click a row to open"),
    "p_type": ("ประเภท", "Type"),
    "p_policy": ("นโยบายที่ใช้", "Policy used"),
    "pol_company": ("นโยบายบริษัท", "company policy"),
    "pol_company_edit": ("นโยบายบริษัท + คนแก้", "company policy + human edits"),
    "pol_ai_draft": ("AI ร่าง (ยังไม่ยืนยัน)", "AI draft (not confirmed)"),
    "pol_ai_human": ("AI + คนตรวจแล้ว", "AI + human confirmed"),
    "pol_manual": ("ชุดกำหนดเอง", "manual rule set"),
    "pol_manual_old": ("กฎชุดเดียวทุกสัญญา", "one rule set for all"),
    "p_legend": ("คลิกที่แถวเพื่อเปิดทันที · สถานะ: {s}", "Click a row to open it · status: {s}"),
    "v_prev": ("หน้าก่อน", "Previous page"), "v_next": ("หน้าถัดไป", "Next page"),
    "v_of": ("หน้า {p} / {n}", "Page {p} / {n}"),
})
VIEWS = {"start": "tab_start", "port": "tab_port", "dash": "tab_dash", "policy": "tab_policy4", "trace": "tab_trace"}


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


def saved_reports() -> list[Path]:
    files = [f for f in config.OUTPUT_DIR.glob("*.json") if not f.name.endswith(".meta.json")]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def load_saved(fp: Path) -> dict | None:
    """Rebuild a result (report, trace, PDF) from files written by an earlier run."""
    import pymupdf
    try:
        rep = ContractAuditReport.model_validate_json(fp.read_text(encoding="utf-8"))
    except Exception:
        return None
    meta_fp = fp.with_name(fp.stem + ".meta.json")
    meta = json.loads(meta_fp.read_text(encoding="utf-8")) if meta_fp.exists() else {}
    pdf = meta.get("pdf")
    if not pdf or not Path(pdf).exists():
        try:
            pdf = str(pdf_path(rep.contract_title + ".pdf"))
        except KeyError:
            pdf = None
    if pdf and not meta:  # runs saved before page attribution was fixed
        doc = ContractDocument(Path(pdf).stem, extract_pages(Path(pdf), use_vision=False))
        for r in rep.findings:
            if r.finding.extracted_text.strip():
                r.verified_page, r.quote_score = doc.find_quote(r.finding.extracted_text)
    trace_fp = Path(meta["trace"]) if meta.get("trace") else next(iter(sorted(config.TRACE_DIR.glob(f"*{fp.stem}*.json"))[-1:]), None)
    data = json.loads(trace_fp.read_text(encoding="utf-8")) if trace_fp and trace_fp.exists() else {}
    records = data.get("records", [])
    xlsx = fp.with_suffix(".xlsx")
    return {"report": rep, "records": records,
            "totals": data.get("totals", {"llm_calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0}),
            "xlsx": xlsx.read_bytes() if xlsx.exists() else b"", "xlsx_name": xlsx.name,
            "mode": meta.get("mode", "m_baseline" if fp.stem.endswith("baseline") else "m_agent"),
            "seconds": meta.get("seconds", sum(x.get("sec", 0) for x in records if x["type"] == "llm")),
            "lang": meta.get("lang", "th"), "pdf": pdf,
            "profile": meta.get("profile"), "criteria": meta.get("criteria") or [], "origin": meta.get("origin", ""),
            "n_pages": meta.get("n_pages") or (len(pymupdf.open(pdf)) if pdf else 1)}


if "demo" in st.query_params and "result" not in st.session_state:
    for _fp in saved_reports():
        _demo = load_saved(_fp)
        if _demo and _demo["pdf"]:
            st.session_state.result = _demo
            break

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

_lang = st.session_state.lang
_nav_key = f"view_{_lang}"
if run or st.session_state.get("goto"):
    st.session_state[_nav_key] = {"view": "dash"}.get(st.session_state.get("goto"), st.session_state.get("goto")) or "dash"
    st.session_state.pop("goto", None)
if st.session_state.get("choice_view") not in VIEWS:
    st.session_state.choice_view = "start"
if _nav_key not in st.session_state or st.session_state[_nav_key] not in VIEWS:
    st.session_state[_nav_key] = st.session_state.get("choice_view", "start")
_fmt = label_fn(_lang)
view = st.segmented_control("nav", list(VIEWS), key=_nav_key, label_visibility="collapsed",
                            format_func=lambda v: _fmt(VIEWS[v]))
view = view or st.session_state.get("choice_view", "start")
st.session_state.choice_view = view

# ================= tab 1: start (intro + how to use) =================
START = {
    "th": {
        "hero": "ตรวจสัญญาเทียบนโยบายบริษัทด้วย AI agent",
        "lead": "อัปโหลดสัญญา PDF แล้วระบบจะระบุประเภทสัญญา เลือกนโยบายที่ตรงประเภท ตรวจทีละข้อ "
                "และบอกว่าควรลงนามหรือไม่ พร้อมไฮไลต์ข้อความจริงในสัญญาทุกข้อ",
        "stats": "สัญญาที่ตรวจแล้ว {n} ฉบับ · คลังนโยบายมี {k} ประเภท",
        "what": [("ระบุประเภทสัญญา", "AI อ่านต้นสัญญา บอกประเภท (จาก 25 ประเภทของ CUAD) ฝ่ายเรา และคู่สัญญา แล้วดึงนโยบายของประเภทนั้นจากคลัง"),
                 ("ตรวจทีละข้อ", "Agent ค้นและอ่านสัญญาเฉพาะส่วนที่เกี่ยวกับกฎแต่ละข้อ ตัวตรวจซ้ำ (โค้ด) ยืนยันว่าข้อความที่อ้างมีอยู่จริง"),
                 ("สรุปให้ตัดสินใจ", "ลงนามได้ไหม · สิ่งที่ต้องแก้เรียงตามความเสี่ยง · PDF พร้อมไฮไลต์ · ฝ่ายกฎหมายอนุมัติข้อเสี่ยงสูง")],
        "how_title": "วิธีใช้ 5 ขั้น",
        "how": [("เลือกภาษา", "แถบซ้ายบนสุด ผลที่ AI เขียนจะเป็นภาษานั้น"),
                ("เลือกนโยบาย", "<b>อัตโนมัติ</b> (แนะนำ): ใช้คลังนโยบายตามประเภทสัญญา · <b>กำหนดเอง</b>: ใช้กฎชุดเดียวกับทุกสัญญา · แก้ไขได้ที่แท็บ ④"),
                ("อัปโหลดสัญญา", "PDF ภาษาไทยหรืออังกฤษ ถ้าเป็นไฟล์สแกนหรือข้อความไทยอ่านไม่ออก ให้เปิดสวิตช์ vision"),
                ("เลือกวิธีตรวจ", "<b>Agent</b>: ตรวจละเอียดและยืนยันทุกข้อ ประมาณ 1–2 นาที · <b>Baseline</b>: เรียก AI ครั้งเดียว เร็วกว่าแต่ไม่ได้ตรวจซ้ำ"),
                ("กดวิเคราะห์สัญญา", "ระหว่างทำงานจะเห็น agent ตรวจทีละข้อ เสร็จแล้วไปที่แดชบอร์ดเอง · ดาวน์โหลด Excel ได้")],
        "tabs_title": "แต่ละแท็บใช้ทำอะไร",
        "tabs": [("② สัญญาทั้งหมด", "ผลที่เคยตรวจ ค้นหาและคลิกแถวเพื่อเปิด"),
                 ("③ แดชบอร์ด", "ประเภทสัญญาและนโยบายที่ใช้ → ผลตัดสิน → สิ่งที่ต้องแก้ → สรุป → PDF ไฮไลต์ → อนุมัติ"),
                 ("④ นโยบายบริษัท", "คลังนโยบายตามประเภทสัญญา แก้ไขกฎ หรืออัปโหลด PDF นโยบายให้ AI แยกเป็นกฎ"),
                 ("⑤ เส้นทาง Agent", "ทุกขั้นที่ agent ค้น อ่าน ส่งคำตอบ และถูกตีกลับ พร้อม tokens เวลา ต้นทุน")],
        "status_title": "อ่านผลอย่างไร",
        "status": {"COMPLIANT": "เป็นไปตามนโยบาย", "DEVIATED": "มีแต่ต่างจากนโยบาย ควรเจรจา",
                   "VIOLATED": "ขัดนโยบาย ต้องแก้ก่อนลงนาม", "MISSING": "ไม่มีข้อที่นโยบายกำหนดให้ต้องมี"},
        "note": "ผลจาก AI เป็นการตรวจรอบแรก ข้อเสี่ยงสูงต้องให้ฝ่ายกฎหมายยืนยันก่อนใช้จริง",
    },
    "en": {
        "hero": "Check contracts against company policy with an AI agent",
        "lead": "Upload a contract PDF. The system finds the contract type, picks the matching policy, checks it rule by rule "
                "and tells you whether to sign, with every quote highlighted in the contract.",
        "stats": "{n} contracts reviewed · policy library covers {k} contract types",
        "what": [("Find the contract type", "The AI reads the start of the contract, names its type (one of CUAD's 25), our company and the other party, and loads that type's policy"),
                 ("Check rule by rule", "The agent searches and reads only the parts relevant to each rule. A verifier (code) confirms every quote exists"),
                 ("Decide", "Sign or not · what to fix, most severe first · highlighted PDF · legal approves high-risk items")],
        "how_title": "How to use it in 5 steps",
        "how": [("Pick a language", "Top of the sidebar. AI-written text follows it"),
                ("Choose the policy", "<b>Automatic</b> (recommended): the policy library by contract type · <b>Manual</b>: one rule set for every contract · edit in tab ④"),
                ("Upload the contract", "Thai or English PDF. For scans or unreadable Thai text, keep the vision switch on"),
                ("Choose the method", "<b>Agent</b>: thorough, every finding verified, about 1–2 minutes · <b>Baseline</b>: one AI call, faster, not verified"),
                ("Press Analyse contract", "You see the agent work rule by rule, then the dashboard opens · Excel download available")],
        "tabs_title": "What each tab is for",
        "tabs": [("② Portfolio", "Every past review. Search, click a row to open it"),
                 ("③ Dashboard", "Contract type and policy → verdict → what to fix → summary → highlighted PDF → approval"),
                 ("④ Company policy", "Policy library by contract type. Edit rules or upload a policy PDF for the AI to split into rules"),
                 ("⑤ Agent trace", "Every search, read, submission and send-back, with tokens, time and cost")],
        "status_title": "How to read the results",
        "status": {"COMPLIANT": "Meets the policy", "DEVIATED": "Present but differs, negotiate",
                   "VIOLATED": "Breaks the policy, fix before signing", "MISSING": "A required clause is absent"},
        "note": "AI results are a first review. Legal must confirm high-risk items before relying on them.",
    },
}

if view == "start":
    S = START[st.session_state.lang]
    n_runs = len(saved_reports())
    n_types = sum(bool(v) for g, v in current_library().items() if g != GENERAL)
    cards = "".join(f"<div class='cc-card'><div style='font-weight:700;margin-bottom:4px'>{i}. {a}</div>"
                    f"<div class='cc-muted'>{b}</div></div>" for i, (a, b) in enumerate(S["what"], 1))
    steps = "".join(f"<div class='cc-how'><div class='cc-hown'>{i}</div><div><b>{a}</b><div class='cc-muted'>{b}</div></div></div>"
                    for i, (a, b) in enumerate(S["how"], 1))
    tabs = "".join(f"<div class='cc-iss' style='grid-template-columns:150px 1fr'><b>{a}</b><span class='cc-muted'>{b}</span></div>"
                   for a, b in S["tabs"])
    stat = "".join(f"<div style='display:flex;gap:10px;align-items:center;padding:4px 0'>{ui.chip(k)}<span>{v}</span></div>"
                   for k, v in S["status"].items())
    st.html(f"""
<div class='cc-card' style='padding:24px 26px'>
  <div style='font-size:26px;font-weight:700;line-height:1.3'>{S['hero']}</div>
  <div class='cc-muted' style='font-size:15px;margin-top:6px;max-width:820px'>{S['lead']}</div>
  <div style='margin-top:10px;font-size:13px;color:#2a54d6;font-weight:600'>{S['stats'].format(n=n_runs, k=n_types)}</div>
</div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:12px'>{cards}</div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px;margin-top:12px'>
  <div class='cc-card'><div class='cc-label' style='margin-bottom:8px'>{S['how_title']}</div>{steps}</div>
  <div style='display:grid;gap:12px;align-content:start'>
    <div class='cc-card'><div class='cc-label' style='margin-bottom:4px'>{S['tabs_title']}</div>{tabs}</div>
    <div class='cc-card'><div class='cc-label' style='margin-bottom:6px'>{S['status_title']}</div>{stat}
      <div class='cc-muted' style='margin-top:8px'>{S['note']}</div></div>
  </div>
</div>""")
    b1, b2, _ = st.columns([1, 1, 2])
    b1.button(t("tab_port"), width="stretch", on_click=lambda: st.session_state.__setitem__("goto", "port"))
    b2.button(t("tab_policy4"), width="stretch", on_click=lambda: st.session_state.__setitem__("goto", "policy"))

# ================= tab 4: policy =================
def rules_editor(df: pd.DataFrame, key: str) -> pd.DataFrame:
    return st.data_editor(
        df, num_rows="dynamic", hide_index=True, width="stretch", key=key,
        column_config={
            "use": st.column_config.CheckboxColumn("use", width="small", default=True),
            "draft": st.column_config.CheckboxColumn(t("col_draft"), width="small", default=False, help=t("col_draft_help")),
            "id": st.column_config.TextColumn(t("col_id"), width="small"),
            "title_th": st.column_config.TextColumn(t("col_title") + " (TH)", width="medium"),
            "title": st.column_config.TextColumn(t("col_title") + " (EN)", width="medium"),
            "text": st.column_config.TextColumn(t("col_text"), width="large"),
            "if_absent": st.column_config.SelectboxColumn("if_absent", options=["MISSING", "COMPLIANT"], width="small"),
            "keywords": st.column_config.TextColumn(t("col_kw"), width="medium"),
            "origin": st.column_config.TextColumn(t("col_origin"), width="medium", disabled=True),
            "added": st.column_config.TextColumn(t("col_added"), width="small", disabled=True),
        })


if view == "policy" and auto:
    st.subheader(t("lib_title"))
    st.caption(t("lib_help"))
    lib_now = current_library()
    _lang = st.session_state.lang
    chips = "".join(
        f"<span class='cc-pill{' on' if lib_now.get(g) else ''}{' draft' if any(r.get('draft') for r in lib_now.get(g, [])) else ''}'>"
        f"{ui.esc(type_label(g, _lang))} · "
        f"{t('lib_count', n=len(lib_now[g])) if lib_now.get(g) else '–'}"
        f"{' · ' + t('col_draft') if any(r.get('draft') for r in lib_now.get(g, [])) else ''}</span>" for g in GROUPS_TH)
    st.html(f"<div class='cc-pills'>{chips}</div>")
    st.markdown(f"**{t('lib_pick')}**")
    group = pick(st.selectbox, "lib_group", list(GROUPS_TH), format_func=(lambda g, _l=_lang: type_label(g, _l)),
                 label_visibility="collapsed")
    if not lib_now.get(group):
        st.caption(t("lib_none"))
    n_draft = sum(bool(r.get("draft")) for r in lib_now.get(group, []))
    if n_draft:
        n1, n2 = st.columns([3, 1], vertical_alignment="center")
        n1.warning(t("lib_draft_note", n=n_draft))
        if n2.button(t("lib_confirm"), width="stretch"):
            lib = current_library()
            lib[group] = [{k: v for k, v in r.items() if k != "draft"} for r in lib.get(group, [])]
            lib = {g: renumber(v, prefix_for(g)) for g, v in lib.items()}
            save_library(lib)
            log_change("confirm", group, f"{len(lib.get(group, []))} ข้อ")
            reset_library_tables(lib)
            st.toast(t("lib_confirmed"))
            st.rerun()
    key = f"libdf_{group}"
    if key not in st.session_state:
        st.session_state[key] = rules_to_df(st.session_state.library.get(group, []))
    st.session_state[key] = rules_editor(st.session_state[key], f"lib_editor_{group}")
    c1, c2 = st.columns(2)
    if c1.button(t("lib_save"), type="primary", width="stretch"):
        before = st.session_state.library
        lib = {g: renumber(v, prefix_for(g)) for g, v in current_library().items()}
        for g in sorted(set(before) | set(lib)):
            old = {r.get("title"): r for r in before.get(g, [])}
            new = {r.get("title"): r for r in lib.get(g, [])}
            added, removed = set(new) - set(old), set(old) - set(new)
            changed = [k for k in set(new) & set(old)
                       if {x: new[k].get(x) for x in ("text", "if_absent", "keywords", "draft")}
                       != {x: old[k].get(x) for x in ("text", "if_absent", "keywords", "draft")}]
            if added or removed or changed:
                log_change("edit", g, " · ".join(x for x in (
                    f"เพิ่ม {len(added)}: {', '.join(sorted(added))[:80]}" if added else "",
                    f"ลบ {len(removed)}: {', '.join(sorted(removed))[:80]}" if removed else "",
                    f"แก้ {len(changed)}: {', '.join(sorted(changed))[:80]}" if changed else "") if x))
        save_library(lib)
        reset_library_tables(lib)
        st.toast(t("lib_saved"))
        st.rerun()
    c2.download_button(t("lib_dl"), library_to_yaml(current_library()), "policy_library.yaml", width="stretch")
    st.caption(t("lib_cloud"))
    with st.expander(t("lib_upload")):
        pol = st.file_uploader(t("policy_file"), type="pdf", key="lib_policy_pdf")
        if st.button(t("lib_merge"), disabled=pol is None):
            tmp = Path(tempfile.mkdtemp()) / pol.name
            tmp.write_bytes(pol.getvalue())
            with st.spinner(t("extracting")):
                try:
                    new = [r | {"origin": f"PDF: {pol.name[:40]}", "added": today()} for r in extract_rules(tmp)]
                    lib = merge_into_library(current_library(), new)
                    save_library(lib)
                    reset_library_tables(lib)
                    added = {}
                    for r in new:
                        for g in (r.get("applies_to") or [GENERAL]):
                            added[g] = added.get(g, 0) + 1
                    for g, n in added.items():
                        log_change("pdf_import", g, f"{n} ข้อ จาก {pol.name[:40]}")
                    st.session_state.lib_msg = t("lib_merged", s=", ".join(f"{type_label(g, _lang)} {n}" for g, n in added.items()))
                    st.rerun()
                except Exception as e:
                    st.error(f"{type(e).__name__}: {str(e)[:200]}")
        if st.session_state.get("lib_msg"):
            st.success(st.session_state.lib_msg)

    st.subheader(t("hist_title"))
    st.markdown(f"**{t('use_title', type=type_label(group, _lang))}**")
    usage = rule_usage(group, lib_now.get(group, []))
    if usage:
        st.dataframe(pd.DataFrame([{
            t("use_rule"): u["title"], t("use_n"): u["n"], t("use_last"): u["last"] or "–",
            "✕ VIOLATED": u["VIOLATED"], "∅ MISSING": u["MISSING"], "~ DEVIATED": u["DEVIATED"], "✓ COMPLIANT": u["COMPLIANT"],
        } for u in usage]), hide_index=True, width="stretch")
        st.caption(t("use_note"))
    st.markdown(f"**{t('log_title')}**")
    log = read_log()
    if not log:
        st.caption(t("log_empty"))
    else:
        st.dataframe(pd.DataFrame([{
            t("log_when"): x["time"].replace("T", " "), t("log_action"): t(f"act_{x['action']}") if f"act_{x['action']}" in TEXT else x["action"],
            t("log_group"): type_label(x["group"], _lang), t("log_detail"): x.get("detail", ""),
        } for x in log]), hide_index=True, width="stretch")

if view == "policy" and not auto:
    st.subheader(t("rules_title"))
    st.caption(t("rules_help"))
    if len(st.session_state.rules_df) == 0:
        st.info(t("rules_empty"))
    edited = rules_editor(st.session_state.rules_df, "rules_editor")
    st.session_state.rules_df = edited
    st.download_button(t("dl_yaml"), rules_to_yaml(df_to_rules(edited)), "company_policy_rules.yaml")

# ================= run: live progress board =================
if run:
    if upload is not None:
        pdf = Path(tempfile.mkdtemp()) / upload.name
        pdf.write_bytes(upload.getvalue())
    else:
        pdf = pdf_path(sample)
    active = [] if auto else df_to_rules(st.session_state.rules_df)
    lang = st.session_state.lang
    trace = Trace(f"{re.sub(r'[^A-Za-z0-9]+', '_', pdf.stem)[:28]}_{time.strftime('%m%d-%H%M%S')}"
                  f"_{'agent' if mode == 'm_agent' else 'baseline'}")
    t0 = time.time()
    board = st.empty()
    prog = {"read": t("pb_reading"), "foot": "",
            "rows": {r["id"]: {"title": rule_title(r), "state": "wait", "tools": [], "chip": "", "note": t("pb_wait")}
                     for r in active}}

    def draw():
        board.html(ui.progress_board(t("pb_title"), prog["read"], list(prog["rows"].items()), prog["foot"],
                                     time.time() - t0))

    def on_step(rule):
        prog["rows"][rule["id"]].update(state="run", note=t("pb_run"))
        draw()

    def on_tool(rule, call):
        prog["rows"][rule["id"]]["tools"].append(call)
        draw()

    def on_done(rule, r):
        row = prog["rows"][rule["id"]]
        row.update(state="done", chip=ui.chip(r.finding.compliance_status) + " " + ui.risk_chip(r.finding.risk_level),
                   note=t("pb_calls", n=r.steps, r=r.rejections))
        if rule is active[-1]:
            prog["foot"] = t("pb_summary")
        draw()

    try:
        draw()
        pages = extract_pages(pdf, use_vision=vision, trace=trace)
        doc = ContractDocument(pdf.stem, pages)
        kinds = {k: sum(p.kind == k for p in pages) for k in ("text", "table", "scan", "pymupdf", "vision")}
        prog["read"] = t("pb_read", n=len(pages), kinds=", ".join(f"{k} {v}" for k, v in kinds.items() if v),
                         p=len(doc.passages))
        draw()
        profile, origin, context = None, "", ""
        if auto:
            prog["foot"] = t("pb_profile")
            draw()
            profile = profile_contract(doc, trace, lang)
            lib = current_library()
            if not lib.get(profile.contract_type):
                prog["foot"] = t("pb_criteria")
                draw()
            active, origin = criteria_for(profile, lib, trace, lang)
            if origin == "ai":  # keep them as a DRAFT policy for this type; a person confirms or edits later
                src_name = doc.title.split("-EX-")[0][:40]
                lib[profile.contract_type] = renumber(
                    [{k: r[k] for k in ("title", "title_th", "text", "if_absent", "keywords")}
                     | {"draft": True, "origin": f"AI ร่างจากสัญญา {src_name}", "added": today()}
                     for r in active if r["source"] == "ai"], prefix_for(profile.contract_type))
                save_library(lib)
                log_change("ai_draft", profile.contract_type,
                           f"{len(lib[profile.contract_type])} ข้อ จากสัญญา {src_name}")
                reset_library_tables(lib)
            context = context_line(profile)
            prog["read"] += " · " + t("pb_profiled", type=type_label(profile.contract_type, lang),
                                      g=sum(r["source"] == "general" for r in active),
                                      p=sum(r["source"] != "general" for r in active), src=t(f"src_{origin}"))
            prog["rows"] = {r["id"]: {"title": rule_title(r) + (f" · {t('ai_tag')}" if r["source"] == "ai" else ""),
                                      "state": "wait", "tools": [], "chip": "", "note": t("pb_wait")} for r in active}
            prog["foot"] = ""
            draw()
        if mode == "m_agent":
            report = review(doc, active, trace, lang=lang, on_step=on_step, on_tool=on_tool, on_done=on_done,
                            context=context)
        else:
            prog["foot"] = t("pb_single")
            draw()
            report = review_single_call(pdf, doc, active, trace, lang=lang, context=context)
    except Exception as e:
        st.error(f"{type(e).__name__}: {str(e)[:300]}")
        st.stop()
    seconds = time.time() - t0
    js, xlsx = save(report, config.OUTPUT_DIR, trace.run_name)
    trace_fp = trace.save()
    (config.OUTPUT_DIR / "pdfs").mkdir(exist_ok=True)
    kept_pdf = config.OUTPUT_DIR / "pdfs" / f"{trace.run_name}.pdf"
    shutil.copy(pdf, kept_pdf)
    (config.OUTPUT_DIR / f"{trace.run_name}.meta.json").write_text(json.dumps(
        {"mode": mode, "lang": lang, "seconds": seconds, "n_pages": len(pages), "pdf": str(kept_pdf),
         "trace": str(trace_fp), "model": config.MODEL,
         "profile": profile.model_dump() if profile else None, "origin": origin,
         "policy_name": (type_label(profile.contract_type, "th") if profile else t(st.session_state.policy_source or "src_upload")),
         "criteria": active},
        ensure_ascii=False), encoding="utf-8")
    for k in [k for k in st.session_state if str(k).startswith(("hitl_", "vp_"))]:
        del st.session_state[k]
    st.session_state.result = load_saved(js)
    st.rerun()

res = st.session_state.get("result")

# ================= contract workspace (PDF + findings), shown inside the dashboard =================
def contract_workspace(res: dict) -> None:
    if not res.get("pdf") or not Path(res["pdf"]).exists():
        st.caption(t("p_no_pdf"))
        return
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
        pkey = f"vp_{sel}"
        st.session_state.setdefault(pkey, min(default_page, n_pages))
        b1, b2, b3 = st.columns([1, 2.2, 1], vertical_alignment="center")
        b1.button("‹", key="pg_prev", help=t("v_prev"), disabled=st.session_state[pkey] <= 1, width="stretch",
                  on_click=lambda: st.session_state.__setitem__(pkey, st.session_state[pkey] - 1))
        b3.button("›", key="pg_next", help=t("v_next"), disabled=st.session_state[pkey] >= n_pages, width="stretch",
                  on_click=lambda: st.session_state.__setitem__(pkey, st.session_state[pkey] + 1))
        page = st.session_state[pkey]
        b2.html(f"<div style='text-align:center;font-weight:600'>{t('v_of', p=page, n=n_pages)}</div>")
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



# ================= tab 2: dashboard =================
if view == "dash":
    if not res:
        st.html(ui.skeleton([t("k_score"), t("k_high"), t("k_miss"), t("k_ver"), t("k_cost")],
                            [t("split_title"), t("map_title"), t("effort_title")]))
        st.info(t("skel_hint"))
    else:
        report, totals = res["report"], res["totals"]
        c = report.counts
        findings = report.findings
        n = len(findings) or 1
        if res.get("lang", "th") != st.session_state.lang:
            st.caption(t("lang_note"))
        ai_ids = {x["id"] for x in res.get("criteria", []) if x.get("source") == "ai"}
        prof = res.get("profile")
        if prof:
            _l = st.session_state.lang
            th = _l == "th"
            name = lambda x: (x.get("title_th") if th and x.get("title_th") else x.get("title")) or ""
            ctype = prof["contract_type"]
            tname = type_label(ctype, _l)
            crit = res.get("criteria", [])
            gen = [x for x in crit if x.get("source") == "general"]
            spec = [x for x in crit if x.get("source") in ("library", "ai")]
            items = lambda xs, note: "".join(
                f"<li><b>{ui.esc(x['id'])}</b> {ui.esc(name(x))}"
                + (f" — <span class='cc-muted'>{ui.esc(x.get('why') or '')}</span>" if note else "") + "</li>" for x in xs)
            spec_head = (t("prof_ai", type=tname, n=len(spec)) if res.get("origin") == "ai"
                         else t("prof_lib_draft", type=tname, n=len(spec)) if any(x.get("draft") for x in spec)
                         else t("prof_lib", type=tname, n=len(spec)))
            st.html(
                f"<div class='cc-card'><div class='cc-label'>{t('prof_title')}</div>"
                f"<div style='display:flex;flex-wrap:wrap;gap:6px 28px;margin:6px 0 4px'>"
                f"<div><span class='cc-muted'>{t('prof_type')}</span><br><b>{ui.esc(tname)}</b></div>"
                f"<div><span class='cc-muted'>{t('prof_us')}</span><br><b>{ui.esc(prof['our_party'])}</b></div>"
                f"<div><span class='cc-muted'>{t('prof_them')}</span><br><b>{ui.esc(prof['counterparty'])}</b></div></div>"
                f"<div class='cc-muted' style='margin-bottom:8px'>{ui.esc(prof['subject'])}</div>"
                f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:4px 24px'>"
                f"<div><b>{t('prof_general', n=len(gen))}</b><ul style='margin:4px 0'>{items(gen, False)}</ul></div>"
                f"<div><b>{spec_head}</b><ul style='margin:4px 0'>{items(spec, res.get('origin') == 'ai')}</ul>"
                + (f"<div class='cc-muted'>{t('prof_ai_note')}</div>" if res.get("origin") == "ai" else "")
                + "</div></div></div>")
            if res.get("origin") == "ai" or any(x.get("draft") for x in spec):
                d1, d2 = st.columns([3, 1], vertical_alignment="center")
                d1.info(t("prof_drafted", type=tname) if res.get("origin") == "ai" else t("lib_draft_note", n=len(spec)))
                if d2.button(t("go_review"), width="stretch"):
                    st.session_state[f"choice_lib_group"] = ctype
                    st.session_state.goto = "policy"
                    st.rerun()

        counts = {s: sum(r.finding.compliance_status == s for r in findings) for s in STATUS_COLOR}
        level = ui.verdict_level(findings)
        open_issues = [r for r in findings if r.finding.compliance_status != "COMPLIANT"]
        n_block = sum(r.finding.risk_level == "HIGH" and r.finding.compliance_status in ("VIOLATED", "MISSING")
                      for r in findings)
        sub = {"block": t("vd_block_sub", n=n_block, m=len(open_issues)),
               "warn": t("vd_warn_sub", n=len(open_issues)), "ok": t("vd_ok_sub")}[level]
        unverified = c["total"] - c["verified"]
        if unverified:
            sub += " · " + t("vd_unver", n=unverified)
        st.html(ui.verdict_panel(
            level, t(f"vd_{level}"), sub, counts, status_labels(),
            [(r.finding.policy_id, r.finding.clause_category, r.finding.compliance_status, r.finding.risk_level,
              r.finding.action_required, r.finding.clause_reference) for r in open_issues],
            t("vd_fix"), t("vd_more")))
        with st.expander(t("summary_ai"), expanded=True):
            st.markdown(report.executive_summary)
        st.caption(t("run_meta", mode=t(res["mode"]), s=f"{res['seconds']:.0f}", calls=totals["llm_calls"],
                     tok=f"{totals['tokens_in'] + totals['tokens_out']:,}", cost=f"{totals['cost_usd']:.3f}",
                     model=config.MODEL))
        st.subheader(t("ws_title"))
        contract_workspace(res)

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
            f"<tr><td><b>{ui.esc(r.finding.policy_id)}</b></td><td>{ui.esc(r.finding.clause_category)}"
            f"{' <span class=cc-muted>· ' + t('ai_tag') + '</span>' if r.finding.policy_id in ai_ids else ''}</td>"
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

# ================= tab 4: agent trace =================
if view == "trace":
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
def policy_label(meta: dict, lang: str) -> str:
    """Which policy a saved run used, and where its type-specific rules came from."""
    prof, crit = meta.get("profile"), meta.get("criteria") or []
    if not prof:
        return f"{meta.get('policy_name') or t('pol_manual_old')} · {t('pol_manual')}"
    name = type_label(prof["contract_type"], lang)
    spec = [c for c in crit if c.get("source") in ("library", "ai")]
    origins = [str(c.get("origin") or "") for c in spec]
    if meta.get("origin") == "ai" or any(c.get("draft") for c in spec):
        kind = t("pol_ai_draft")
    elif any(o.startswith("AI") for o in origins):
        kind = t("pol_ai_human")
    elif any(o == EDITED for o in origins):
        kind = t("pol_company_edit")
    else:
        kind = t("pol_company")
    return f"{name} · {kind}"



if view == "port":
    st.subheader(t("p_title"))
    st.caption(t("p_note"))
    _l = st.session_state.lang
    rows, paths = [], []
    for fp in saved_reports():
        try:
            rep = ContractAuditReport.model_validate_json(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta_fp = fp.with_name(fp.stem + ".meta.json")
        try:
            meta = json.loads(meta_fp.read_text(encoding="utf-8")) if meta_fp.exists() else {}
        except Exception:
            meta = {}
        prof = meta.get("profile")
        cnt = {s: sum(r.finding.compliance_status == s for r in rep.findings) for s in STATUS_COLOR}
        n = max(len(rep.findings), 1)
        paths.append(fp)
        rows.append({
            t("p_contract"): rep.contract_title.split("-EX-")[0][:48],
            t("p_type"): type_label(prof["contract_type"], _l) if prof else "–",
            t("p_when"): time.strftime("%d %b %H:%M", time.localtime(fp.stat().st_mtime)),
            t("p_mode"): "Single call" if fp.stem.endswith("baseline") else "Agent",
            t("p_policy"): policy_label(meta, _l),
            t("k_score"): 100 * cnt["COMPLIANT"] / n,
            t("p_split"): "   ".join(f"{ui.STATUS[s][1]} {cnt[s]}" for s in STATUS_COLOR),
            t("p_high"): rep.counts["high"], t("p_miss"): rep.counts["missing"],
            t("p_ver"): f"{rep.counts['verified']}/{rep.counts['total']}",
        })
    if not rows:
        st.info(t("p_empty"))
    else:
        query = st.text_input(t("p_search"), placeholder=t("p_search_ph"), key="port_q")
        target = "dash"
        df = pd.DataFrame(rows)
        df["_i"] = range(len(df))
        if query.strip():
            q = query.strip().lower()
            df = df[df.drop(columns="_i").astype(str).apply(lambda r: q in " ".join(r).lower(), axis=1)]
        st.caption(t("p_legend", s=" · ".join(f"{ui.STATUS[s][1]} {lbl}" for s, lbl in status_labels().items())))
        st.session_state.setdefault("port_ver", 0)
        event = st.dataframe(
            df.drop(columns="_i"), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            key=f"port_table_{st.session_state.port_ver}",
            column_config={t("k_score"): st.column_config.ProgressColumn(t("k_score"), format="%.0f%%",
                                                                         min_value=0, max_value=100)})
        sel = event.selection.rows if event and event.selection else []
        if sel:
            loaded = load_saved(paths[int(df.iloc[sel[0]]["_i"])])
            st.session_state.port_ver += 1  # fresh table next time, so the old click does not reopen
            if loaded:
                for k in [k for k in st.session_state if str(k).startswith(("hitl_", "vp_"))]:
                    del st.session_state[k]
                st.session_state.result = loaded
                st.session_state.goto = target
                st.rerun()
