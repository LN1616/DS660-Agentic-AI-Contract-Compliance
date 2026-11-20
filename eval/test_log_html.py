"""Build the 'test log' tab for the project guide straight from the saved result files, so every number in the
guide matches the data. Usage: python -m eval.test_log_html <out.html>"""
import glob
import json
import sys
from html import escape
from pathlib import Path

import pandas as pd

from eval.injection_test import SUMMARY_CLAIMS

OUT = Path("outputs")
RUNS = [  # regression runs: (label, rows csv, reports dir or None, code, note)
    ("14 พ.ย. (ชุดเดิมของหน้านำเสนอ)", "eval_rows_2026-11-14.csv", None, "โค้ด 14 พ.ย.", "API ฟรี มีเวลารอ retry · ใช้เป็นตัวเลขของหน้านำเสนอตอนนี้"),
    ("ก่อนแก้ (before)", "eval_rows_before.csv", None, "d69a714", "ตัวตั้งต้นของวันนี้"),
    ("ข้อ 1 รอบแรก (after1)", "eval_rows_after1.csv", None, "ไม่ได้ commit", "ห่อผลเป็น JSON → quote ตก (ยกเลิก)"),
    ("ข้อ 1 (after2)", "eval_rows_after2.csv", "eval_reports_after2", "de66498", "ห่อเป็นข้อความธรรมดา + cap 4,096"),
    ("ข้อ 2 (step2)", "eval_rows_step2.csv", "eval_reports_step2", "cc21e1d", "progress guard + เส้นทางในแท็บ ⑤"),
]
INJ = [  # injection runs: (label, csv, summaries json, code)
    ("ก่อนแก้ · ชุดแรก (A เท่านั้น)", "injection_before_v1A.csv", "injection_before_v1A_summaries.json", "d69a714"),
    ("ก่อนแก้ (A + B)", "injection_before.csv", "injection_before_summaries.json", "d69a714"),
    ("ข้อ 1 รอบแรก", "injection_after1.csv", "injection_after1_summaries.json", "ไม่ได้ commit"),
    ("ข้อ 1", "injection_after2.csv", "injection_after2_summaries.json", "de66498"),
    ("ข้อ 2", "injection_step2.csv", "injection_step2_summaries.json", "cc21e1d"),
]


def table(head, rows):
    h = "".join(f"<th>{escape(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbox"><table class="t"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def regression_rows():
    out = []
    for label, csv, rep, code, note in RUNS:
        p = OUT / csv
        if not p.exists():
            continue
        e = pd.read_csv(p)
        cells = [escape(label), f"<code>{escape(code)}</code>"]
        for s in ("A1 agent", "B2 single call"):
            z = e[e.system == s]
            pres = f"{int(z.presence_correct.sum())}/{int(z.presence_correct.notna().sum())}"
            quote = f"{z.quote_real.mean():.0%}"
            cells += [pres, quote, f"{z.sec.sum() / 6:.1f} วิ", f"${z.cost_usd.sum() / 6:.4f}"]
        if rep and (OUT / rep).exists():
            F = [x for f in glob.glob(str(OUT / rep / "A1_*.json"))
                 for x in json.load(open(f, encoding="utf-8"))["findings"]]
            st = [x["steps"] for x in F]
            cells += [f"{sum(st) / len(st):.2f}", f"{sum(s >= 10 for s in st)}/{len(st)}", str(sum(x["rejections"] for x in F))]
        else:
            cells += ["–", "–", "–"]
        cells.append(escape(note))
        out.append(cells)
    return out


def injection_rows():
    out = []
    for label, csv, sj, code in INJ:
        p = OUT / csv
        if not p.exists():
            continue
        d = pd.read_csv(p)
        summ = json.load(open(OUT / sj, encoding="utf-8")) if (OUT / sj).exists() else []
        if "variant" not in d.columns:
            d["variant"] = "A"
        for (v, s), z in d.groupby(["variant", "system"]):
            hits = sum(any(c.lower() in (n.get("summary") or "").lower() for c in SUMMARY_CLAIMS)
                       for n in summ if n.get("system") == s and n.get("variant", "A") == v)
            n_sum = sum(1 for n in summ if n.get("system") == s and n.get("variant", "A") == v)
            exposed = f"{int(z.exposed.sum())}/{len(z)}" if "exposed" in z else "ไม่ได้บันทึก"
            fwe = int((z.flipped_to_compliant & z.exposed).sum()) if "exposed" in z else "–"
            out.append([escape(label), f"<code>{escape(code)}</code>", v, escape(s), exposed,
                        f"{int(z.flipped_to_compliant.sum())}/{len(z)}", str(fwe), f"{hits}/{n_sum}"])
    return out


def changes_rows():
    a, b = pd.read_csv(OUT / "eval_rows_after2.csv"), pd.read_csv(OUT / "eval_rows_step2.csv")
    m = a.merge(b, on=["system", "contract", "rule"], suffixes=("_1", "_2"))
    x = m[m.predicted_1 != m.predicted_2]
    rows = []
    for _, r in x.iterrows():
        pc = "" if pd.isna(r.presence_correct_2) else ("✓" if r.presence_correct_2 else "✕")
        rows.append([escape(r.system), escape(r.contract[:22]), r.rule, r.expected_1, r.predicted_1, r.predicted_2, pc])
    n_single = int(((m.system == "B2 single call") & (m.predicted_1 != m.predicted_2)).sum())
    n_agent = int(((m.system == "A1 agent") & (m.predicted_1 != m.predicted_2)).sum())
    return rows, n_single, n_agent


def main(out_path):
    reg = table(["รอบ", "โค้ด", "Agent มี/ไม่มีถูก", "Agent quote จริง", "Agent เวลา/ฉบับ", "Agent ต้นทุน/ฉบับ",
                 "Single มี/ไม่มีถูก", "Single quote จริง", "Single เวลา/ฉบับ", "Single ต้นทุน/ฉบับ",
                 "ขั้นเฉลี่ย/กฎ", "ใช้ครบ 10 ขั้น", "ส่งกลับ", "หมายเหตุ"], regression_rows())
    inj = table(["รอบ", "โค้ด", "payload", "โหมด", "กฎที่เห็น payload", "กลายเป็น COMPLIANT", "…ในกฎที่เห็นจริง",
                 "สรุปทวนข้อความหลอก"], injection_rows())
    ch, n_single, n_agent = changes_rows()
    chg = table(["โหมด", "สัญญา", "กฎ", "เฉลย CUAD", "ข้อ 1", "ข้อ 2", "มี/ไม่มีถูก (ข้อ 2)"], ch)
    html = f"""<!-- ============ TAB TEST LOG (generated by eval/test_log_html.py) ============ -->
<section class="tab sd" id="tests" role="tabpanel" aria-labelledby="t-tests" hidden>
  <div class="head">
    <div class="eyebrow">บันทึกการทดสอบ · สร้างจากไฟล์ผลจริงด้วย eval/test_log_html.py · อัปเดตทุกครั้งที่รันใหม่</div>
    <h2>ทุกการทดสอบตั้งแต่ 20 พ.ย. 2569</h2>
    <p class="lead">ชุดทดสอบเดียวกันทุกรอบ: สัญญา CUAD 6 ฉบับ × กฎ CUAD 5 ข้อ (24 การตัดสินที่ให้คะแนนได้ต่อโหมด) · model gemini-3.5-flash-lite · temperature 0 · แต่ละรอบรันครั้งเดียว · ทุกตัวเลขในหน้านี้ดึงจากไฟล์ใน <code>contract-compliance-agent/outputs/</code></p>
  </div>

  <div class="fig"><div class="fig-title"><h3>1 · Regression (ความแม่นไม่ลดหลังแก้)</h3><span class="small">ขั้นเฉลี่ย / ครบ 10 ขั้น / ส่งกลับ มีเฉพาะรอบที่บันทึกรายงานเต็ม (ตั้งแต่ข้อ 1)</span></div>
  {reg}
  <p class="small">"มี/ไม่มีถูก" = ระบบบอกถูกว่าสัญญามีข้อนั้นหรือไม่ (CUAD ให้คะแนนได้แค่นี้ ไม่มีเฉลยว่า COMPLIANT / DEVIATED / VIOLATED) · "quote จริง" = ข้อความที่อ้างหาเจอในสัญญา ≥ 88/100 · เวลารวมรอบที่ API ไม่ว่าง</p></div>

  <div class="fig"><div class="fig-title"><h3>2 · Prompt injection</h3><span class="small">payload A = คำสั่งตรง ๆ กลางเอกสาร · payload B = ประกาศปลอมจากฝ่ายกฎหมาย พยายามปิด tag อยู่หน้าเรื่องความรับผิด · 3 สัญญา × 5 กฎ</span></div>
  {inj}
  <p class="small">"กลายเป็น COMPLIANT" เทียบกับรอบปกติก่อนแก้ (eval_rows_before) · "ในกฎที่เห็นจริง" นับเฉพาะกฎที่ payload อยู่ในผลค้นหรือข้อความที่อ่าน (single call เห็นทั้งฉบับเสมอ) · คอลัมน์สรุปนับใหม่ด้วยรายการวลีที่ตรวจด้วยตาแล้ว · Agent ที่ "เปลี่ยน" ในข้อ 2 คือ PAXMEDICA P-01 ซึ่งเป็น COMPLIANT ในรอบปกติของโค้ดเดียวกันด้วย จึงไม่ใช่ผลของ payload</p></div>

  <div class="fig"><div class="fig-title"><h3>3 · ผลตัดสินเปลี่ยนระหว่างรอบ (ข้อ 1 → ข้อ 2)</h3><span class="small">single call ไม่ได้แก้โค้ดในข้อ 2 แต่เปลี่ยน {n_single} จาก 24 · agent เปลี่ยน {n_agent}</span></div>
  {chg}
  <p class="knownote"><b>ข้อค้นพบ:</b> แม้ temperature 0 ผลตัดสินระดับ COMPLIANT / DEVIATED / VIOLATED เปลี่ยนระหว่างรอบมาก ส่วน "มี/ไม่มี" นิ่งกว่า · รันรอบเดียวแยกการปรับปรุงจริงออกจากความแปรปรวนไม่ได้ จึงเสนอให้ข้อ 3 รันทุกเวอร์ชัน 3 รอบ (รวมกับข้อ 10) · ต้องเขียนไว้ในข้อจำกัดของการนำเสนอ</p></div>

  <div class="fig"><div class="fig-title"><h3>4 · สิ่งที่การทดสอบจับได้ระหว่างทาง</h3></div>
  {table(["พบอะไร", "จับได้อย่างไร", "แก้อย่างไร"], [
      ["payload ชุดแรกอ่อนเกิน หลอกได้แทบไม่มี จึงพิสูจน์อะไรไม่ได้", "ผลก่อนแก้เกือบ 0 ทั้งสองโหมด", "เพิ่ม payload B + บันทึกว่ากฎไหนเห็น payload จริง"],
      ["ตัวนับ \"สรุปทวนข้อความหลอก\" นับผิด (คำว่า ยกเลิก = การเลิกสัญญาด้วย)", "อ่านสรุปทีละฉบับด้วยตา", "เปลี่ยนรายการวลี · นับทุกรอบใหม่ด้วยรายการเดียวกัน"],
      ["ห่อผลเป็น JSON ทำให้ quote ตก (agent 100% → 95.5%)", "regression หลังแก้", "ห่อเป็นข้อความธรรมดา → กลับเป็น 100%"],
      ["ไม่มีเพดาน output: 1 call ยาว 65,532 token เสีย $0.19", "ต้นทุนรอบหนึ่งพุ่งผิดปกติ ไล่ดู trace", "cap 4,096 token + บันทึกเมื่อถูกตัด"],
      ["สมมติฐาน \"agent ค้นซ้ำ\" ผิด: ซ้ำจริงแค่ 1/163 แต่ค้นแล้วไม่เจอข้อใหม่ 37%", "นับจากรายงานที่บันทึกไว้ก่อนเขียนโค้ด", "ทำ no-progress detection แทน loop detection แบบตรงตัว"],
      ["ชื่อ parameter ชนกัน (kind) ทำให้รอบวัดผลพัง", "รอบวัดผลจริง (offline test ไม่ครอบคลุม)", "แก้ + เพิ่ม offline test ที่รันลูปจริงพร้อมการค้นซ้ำ"],
      ["single call ย่อ quote ด้วย \"...\"", "ตรวจรายงานของ quote ที่ไม่ผ่าน", "ไม่ใช่ผลของการแก้ ตัวตรวจซ้ำจับได้ถูกต้อง"],
  ])}</div>

  <div class="fig"><div class="fig-title"><h3>5 · ไฟล์ผล (อยู่ในเครื่อง ไม่ขึ้น GitHub)</h3></div>
  <p class="small">โฟลเดอร์ <code>contract-compliance-agent/outputs/</code>: <code>eval_rows_*.csv</code> (ผลรายกฎ) · <code>eval_summary_*.csv</code> · <code>eval_reports_after2/</code>, <code>eval_reports_step2/</code> (รายงานเต็ม มี quote และเส้นทาง) · <code>injection_*.csv</code> + <code>injection_*_summaries.json</code> · <code>injection/INJECTED*.pdf</code> (สัญญาที่ฝัง payload) · log: <code>step1_*.log</code>, <code>step2.log</code> · trace ทุก call: <code>traces/</code> · โค้ดทดสอบอยู่ใน repo: <code>eval/run_eval.py</code>, <code>eval/injection_test.py</code>, <code>eval/test_harness_offline.py</code>, <code>eval/test_log_html.py</code></p></div>
</section>
"""
    Path(out_path).write_text(html, encoding="utf-8")
    print("wrote", out_path, len(html), "chars")


if __name__ == "__main__":
    main(sys.argv[1])
