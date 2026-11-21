"""Routing flow + decision flow figures (Thai), for the guide, the presentation hub and the course notes.

Three figures, one per question a reader asks:
  1. routing flow   - where does a contract go, and how many AI calls does each path cost?
  2. decision flow  - inside one rule: how many steps can the agent take, what stops it, who checks it?
  3. final decision - who decides the sign-off: code, then people (never the model alone)?
Limits are read from src.config / src.agent; the measured calls per rule from outputs/versions/summary.csv.
Usage:  python -m eval.flows_html <out.html>       (prints nothing else; splice the fragment where needed)
"""
import sys
from pathlib import Path

import pandas as pd

from src import agent, config
from eval.versions import VERSIONS

SUMMARY = config.ROOT / "outputs" / "versions" / "summary.csv"

CSS = """<style>
.dflow{--df-line:var(--rule,var(--line,#D6DCE6));--df-surf:var(--surface,#fff);--df-ink2:var(--ink-2,#48546B);
  --df-llm:var(--tech-bg,#ECEBFB);--df-llm-b:var(--tech-line,#8C86E0);--df-hum:var(--human-bg,var(--warn-bg,#FFF4DF));
  --df-hum-b:var(--human-line,var(--warn,#F0B44C));--df-ok:var(--ok,#1F7A33);--df-okbg:var(--ok-bg,#E2F3E6);
  --df-warn:var(--warn,#A3610A);--df-warnbg:var(--warn-bg,#FCEFD8);--df-bad:var(--bad,#B42F2F);--df-badbg:var(--bad-bg,#FBE6E6);
  display:grid;gap:8px;font-size:13.5px;line-height:1.5}
.dflow .df-row{display:flex;flex-wrap:wrap;align-items:stretch;gap:6px}
.dflow .df-b{border:1px solid var(--df-line);background:var(--df-surf);border-radius:9px;padding:7px 10px;min-width:0;flex:1 1 150px}
.dflow .df-b b{display:block;font-size:13.5px}
.dflow .df-b small{color:var(--df-ink2);font-size:12px;display:block}
.dflow .df-llm{background:var(--df-llm);border-color:var(--df-llm-b)}
.dflow .df-code{border-style:dashed;border-color:var(--df-ink2)}
.dflow .df-hum{background:var(--df-hum);border-color:var(--df-hum-b)}
.dflow .df-q{border:2px solid var(--df-ink2);border-radius:9px;background:var(--df-surf);font-weight:600}
.dflow .df-ok{background:var(--df-okbg);border-color:var(--df-ok)} .dflow .df-warn{background:var(--df-warnbg);border-color:var(--df-warn)}
.dflow .df-bad{background:var(--df-badbg);border-color:var(--df-bad)}
.dflow .df-ar{align-self:center;color:var(--df-ink2);flex:0 0 auto}
.dflow .df-down{color:var(--df-ink2);text-align:center;line-height:1}
.dflow .df-tag{display:inline-block;font:600 11px ui-monospace,Consolas,monospace;border-radius:5px;padding:0 6px;margin-left:4px;border:1px solid var(--df-line);color:var(--df-ink2)}
.dflow .df-branch{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:6px}
.dflow .df-lbl{font:600 11.5px ui-monospace,Consolas,monospace;color:var(--df-ink2)}
.dflow .df-loop{border:2px dashed var(--df-llm-b);border-radius:12px;padding:10px;display:grid;gap:6px}
.dflow .df-legend{display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--df-ink2)}
.dflow .df-legend i{display:inline-block;width:14px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px;border:1px solid var(--df-line)}
</style>"""

LEGEND = """<div class="df-legend"><span><i class="df-llm" style="background:var(--df-llm);border-color:var(--df-llm-b)"></i>model (AI) ตัดสิน · ใช้ call</span>
<span><i style="border-style:dashed;border-color:var(--df-ink2)"></i>โค้ด ตัดสิน · ไม่ใช้ call</span>
<span><i style="background:var(--df-hum);border-color:var(--df-hum-b)"></i>คน ตัดสิน</span>
<span><i style="border:2px solid var(--df-ink2)"></i>จุดแยกทาง (คำถาม)</span></div>"""


def b(title, sub="", kind="", tag=""):
    cls = {"llm": " df-llm", "code": " df-code", "hum": " df-hum", "q": " df-q", "ok": " df-ok", "warn": " df-warn",
           "bad": " df-bad"}.get(kind, "")
    t = f'<span class="df-tag">{tag}</span>' if tag else ""
    s = f"<small>{sub}</small>" if sub else ""
    return f'<div class="df-b{cls}"><b>{title}{t}</b>{s}</div>'


def row(*boxes):
    return '<div class="df-row">' + '<span class="df-ar">→</span>'.join(boxes) + "</div>"


def branch(*cols):
    return '<div class="df-branch">' + "".join(f"<div>{c}</div>" for c in cols) + "</div>"


DOWN = '<div class="df-down">↓</div>'


def measured():
    """Calls per rule and budget hits of the newest agent version that has 3 runs."""
    if not SUMMARY.exists():
        return None
    sm = pd.read_csv(SUMMARY).set_index("version")
    for vid in reversed([v for v in VERSIONS if v.startswith("V")]):
        if vid in sm.index and sm.loc[vid, "runs"] >= 3 and pd.notna(sm.loc[vid].get("steps")):
            r = sm.loc[vid]
            return vid, r["steps"], r.get("budget_hits"), r["thb"], r["sec"]
    return None


def project_flows() -> str:
    steps, sendbacks, thr = config.MAX_STEPS, config.MAX_REJECTIONS, agent.QUOTE_THRESHOLD
    m = measured()
    meas = (f"วัดจริง ({m[0]}, เฉลี่ย 3 รอบ บนสัญญา CUAD 6 ฉบับ): {m[1]:.1f} call ต่อกฎ · ใช้ครบงบ {steps} call "
            f"{m[2]:.0f} จาก 30 กฎ · {m[4]:.0f} วินาทีต่อฉบับ" if m else "ยังไม่มีผลวัด 3 รอบ")
    routing = f"""<div class="fig" id="fig-routeflow">
  <div class="fig-title"><h3>ผัง 1 · Routing flow: สัญญาหนึ่งฉบับไปทางไหน และใช้กี่ call</h3><span class="small">ตอบคำถาม "ระบบเลือกนโยบายและวิธีตรวจอย่างไร"</span></div>
  <div class="dflow">{LEGEND}
    {row(b("PDF สัญญา"), b("อ่าน PDF + แบ่งเป็นข้อ", "pdfplumber · TF-IDF", "code", "0 call"))}
    {DOWN}
    {row(b("ชื่อสัญญาระบุประเภทไหม?", "เช่น \"OUTSOURCING AGREEMENT\"", "q"))}
    {branch(b("ใช่: โค้ดตัดสินประเภทจากชื่อ", "ชื่อผสมใช้ประเภทสุดท้าย · 480/494 ถูกบน CUAD", "code"),
            b("ไม่: model ตัดสินจากเนื้อหา", "เฉพาะ 16 จาก 510 ฉบับใน CUAD", "llm"))}
    {row(b("ระบุคู่สัญญาและเรื่องของสัญญา", "ใช้บอกว่าเราอยู่ฝั่งไหน", "llm", "1 call"))}
    {DOWN}
    {row(b("คลังมีนโยบายของประเภทนี้ไหม?", "", "q"))}
    {branch(b("มี: ใช้นโยบายในคลัง", "มีเวอร์ชันและผู้ยืนยัน", "code", "0 call"),
            b("ไม่มี: AI ร่างเกณฑ์ 6 ข้อ", "เก็บเป็นร่าง รอคนยืนยัน", "llm", "1 call"))}
    {DOWN}
    {row(b("เลือกวิธีตรวจ", "", "q"))}
    {branch(b("Single call: AI ตอบทุกกฎในครั้งเดียว", "ส่ง PDF ทั้งฉบับ · ตรวจ quote หลังได้คำตอบ", "llm", "1 call"),
            b("Agent: worker 1 ตัวต่อกฎ ตรวจพร้อมกัน", f"แต่ละกฎ ≤ {steps} call (ผัง 2) · 5 กฎ ≤ {5 * steps} call", "llm", f"≤ {5 * steps} call"))}
    {row(b("สรุปผู้บริหาร", "จากผลทุกกฎ", "llm", "1 call"), b("ผลตัดสินการลงนาม (ผัง 3)", "", "code"))}
    <p class="small">ต่อฉบับ: single call ≈ 3 call · agent ≤ {5 * steps + 2} call (5 กฎ) · {meas}</p>
  </div>
</div>"""

    decision = f"""<div class="fig" id="fig-decisionflow">
  <div class="fig-title"><h3>ผัง 2 · Decision flow ภายใน 1 กฎ: agent เดินได้กี่ขั้น อะไรหยุดมัน ใครตรวจ</h3><span class="small">ทุกกฎเดินผังนี้แยกกัน และพร้อมกัน (V4)</span></div>
  <div class="dflow">{LEGEND}
    {row(b("เริ่ม: กฎ 1 ข้อ", "ข้อความกฎ + สถานะเมื่อไม่มีข้อนี้ + ประเภทและคู่สัญญา", "code"))}
    {DOWN}
    <div class="df-loop"><span class="df-lbl">วน call 1 ถึง {steps - 1} · งบ {steps} call ต่อกฎ · call ละไม่เกิน {config.CALL_TIMEOUT_MS // 1000} วินาที</span>
      {row(b("model เลือก tool", "search_contract · read_passage · submit_finding", "llm", "1 call"),
           b("ตัวจับการค้นไม่คืบหน้า", "ค้นซ้ำ: ไม่รัน · ไม่เจอส่วนใหม่: เตือน · 2 ครั้งติด: บอกส่วนที่ต้องอ่าน", "code"),
           b("ผลของ tool ห่อใน &lt;contract_data&gt;", "เนื้อสัญญาเป็นข้อมูล ไม่ใช่คำสั่ง", "code"))}
      {DOWN}
      {row(b("model ส่ง submit_finding", "สถานะ · ความเสี่ยง · quote · ข้อเสนอแก้ไข", "llm"))}
      {DOWN}
      {row(b("ตัวตรวจซ้ำผ่านไหม?", f"quote ต้องตรงกับ PDF ≥ {thr}/100 · ตอบว่าไม่มีข้อนี้ได้เมื่ออ่าน 3 ส่วนที่เกี่ยวข้องที่สุดครบแล้ว", "q"))}
      {branch(b("ผ่าน: ได้ผลของกฎนี้", "ออกจากวง", "ok"),
              b(f"ไม่ผ่าน ครั้งที่ 1–{sendbacks}: ส่งเหตุผลกลับให้ model แก้", "กลับไปวนต่อ", "warn"),
              b(f"ไม่ผ่าน ครั้งที่ {sendbacks + 1}: เก็บคำตอบไว้ ติดป้ายต้องให้คนตรวจ", "ออกจากวง", "bad"))}
    </div>
    {DOWN}
    {row(b(f"call ที่ {steps}: เปิดให้เรียกได้เฉพาะ submit_finding", "ทุกกฎจึงจบด้วยคำตอบเสมอ แล้วผ่านตัวตรวจซ้ำเหมือนเดิม", "code"))}
    <p class="small">หยุดได้ 3 ทาง: ตัวตรวจซ้ำผ่าน · ตีกลับครบ {sendbacks} ครั้ง · ครบงบ {steps} call · {meas}</p>
  </div>
</div>"""

    final = f"""<div class="fig" id="fig-finalflow">
  <div class="fig-title"><h3>ผัง 3 · Final decision flow: ผลตัดสินการลงนาม โค้ดตัดสินก่อน คนตัดสินสุดท้าย</h3><span class="small">model ไม่ได้ตัดสินว่าลงนามได้หรือไม่</span></div>
  <div class="dflow">{LEGEND}
    {row(b("ผลทุกกฎ (finding)", "สถานะ COMPLIANT / DEVIATED / VIOLATED / MISSING + ความเสี่ยง", "code"))}
    {DOWN}
    {row(b("มีข้อเสี่ยงสูงที่ VIOLATED หรือ MISSING ไหม?", "verdict_level() ในโค้ด", "q"))}
    {branch(b("ใช่: ไม่แนะนำให้ลงนามจนกว่าจะแก้ไข", "", "bad"),
            b("ไม่: มีข้อที่ยังไม่ COMPLIANT ไหม?", "", "q"))}
    {branch("", b("ใช่: ลงนามได้ภายหลังการเจรจาแก้ไข", "", "warn"))}
    {branch("", b("ไม่: สามารถลงนามได้", "ทุกข้อสอดคล้องกับนโยบาย", "ok"))}
    {DOWN}
    {row(b("ฝ่ายกฎหมายพิจารณาข้อเสี่ยงสูง", "อนุมัติข้อเสนอแก้ไข · หรือส่งกลับให้ AI ตรวจใหม่พร้อมความเห็น", "hum"))}
    {DOWN}
    {row(b("ก่อนอนุมัติให้ลงนาม: ตรวจรอบสุดท้ายด้วย Agent", "ข้อเสี่ยงสูงที่ยังไม่แก้ ต้องระบุเหตุผล", "code"),
         b("บันทึกการตัดสินใจ", "อนุมัติให้ลงนาม · ส่งข้อเสนอแก้ไขให้คู่สัญญา · ปฏิเสธสัญญา", "hum"))}
  </div>
</div>"""
    return CSS + routing + decision + final


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(project_flows(), encoding="utf-8")
    print("written", sys.argv[1])
