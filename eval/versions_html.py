"""Design-version history (Single call, V1, V2, V3, planned V4+) with measured results, built from saved files.
Numbers come from outputs/versions/summary.csv (eval.compare_versions: mean and min-max over repeated runs); version
names, harness steps and commits from eval/versions.py. Protocol: docs/EVALUATION.md

Usage: python -m eval.versions_html <out.html>      (fragment used by the presentation hub and the guide's test log)
"""
import re
import sys
from html import escape
from pathlib import Path

import pandas as pd

OUT = Path("outputs")

from eval.compare_versions import BASE, METRICS, MIN_RUNS, THB_PER_USD, overlap
from eval.versions import PLANNED, VERSIONS

RUNS = 3  # runs per version in the protocol

# (column header, summary.csv column, format) — definitions: docs/EVALUATION.md section 3
COLS = [("มี/ไม่มีถูก (จาก 24)", "presence", "{:.1f}"), ("quote จริง", "quote_real", "{:.0%}"),
        ("ประกาศปลอม B หลอกได้ (จาก 15)", "fooled_B", "{:.1f}"), ("คำสั่งตรง A หลอกได้ (จาก 15)", "fooled_A", "{:.1f}"),
        ("สรุปทวนข้อความหลอก (จาก 3)", "claim_B", "{:.1f}"), ("call เฉลี่ย/กฎ", "steps", "{:.1f}"),
        ("ใช้ครบ 10 call (จาก 30)", "budget_hits", "{:.1f}"), ("ตัวตรวจซ้ำตีกลับ", "sendbacks", "{:.1f}"),
        ("เรียก tool ซ้ำตรงตัว", "repeats", "{:.1f}"), ("เวลา/ฉบับ (วิ)", "sec", "{:.0f}"), ("ต้นทุน/ฉบับ (บาท)", "thb", "{:.2f}")]


def cell(r, col, fmt):
    if col not in r or pd.isna(r[col]):
        return "–"
    lo, hi = r[col + "_min"], r[col + "_max"]
    rng = "" if lo == hi else f"<br><span class='small'>{fmt.format(lo)}–{fmt.format(hi)}</span>"
    return fmt.format(r[col]) + rng


def row(vid, r):
    v = VERSIONS[vid]
    cells = [cell(r, c, f) for _, c, f in COLS]
    cells[-1] += f"<br><span class='small'>(${r['usd']:.4f})</span>"
    return [f"<b>{vid}</b>", f"<b>{escape(v['name_th'])}</b><br><span class='small'>{escape(v['change_th'])}</span>",
            escape(v["concept"]), *cells, f"{int(r['verdict_changed'])}/{int(r['pairs'])}",
            f"{int(r['runs'])}/{RUNS}", f"<code>{v['commit']}</code>"]


FLOW_CSS = """<style>
.vflow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0}
.vflow .vst{border:1px solid var(--rule);background:var(--surface);border-radius:8px;padding:5px 9px;font:400 12.5px/1.35 var(--f-ui,var(--f-body));max-width:240px}
.vflow .vst.vnew{border:2px solid var(--ok);background:var(--ok-bg)}
.vflow .vst.vchg{border:2px solid var(--warn);background:var(--warn-bg)}
.vflow .ar{color:var(--ink-3);font-size:13px}
.vflow .tg{font:600 10.5px var(--f-mono);display:block;margin-bottom:2px}
.vflow .vst.vnew .tg{color:var(--ok)} .vflow .vst.vchg .tg{color:var(--warn)}
.vcard.plan{border-style:dashed}
.vweak{background:var(--bad-bg);border-radius:8px;padding:6px 10px}
.vcard{border:1px solid var(--rule);border-radius:10px;padding:12px 14px;margin:10px 0}
.vcard h4{margin:0 0 4px;font-size:15px}
.vcard ul{margin:4px 0 0 18px;padding:0;font-size:13px}
.vtag{font:600 11px var(--f-mono);padding:1px 6px;border-radius:5px;white-space:nowrap}
.vtag.good{color:var(--ok);background:var(--ok-bg)} .vtag.bad{color:var(--bad);background:var(--bad-bg)}
.vtag.same{color:var(--ink-3);border:1px solid var(--rule)}
</style>"""
GUARD = ["presence", "quote_real", "fooled_B"]   # must not get clearly worse in any version (docs/EVALUATION.md section 5)


def effect_items(vid, sm):
    """Measured change against the previous version, using the same 'ranges must not overlap' rule as compare_versions."""
    v = VERSIONS[vid]
    prev = v["prev"]
    if not prev:
        return "<li>จุดตั้งต้นของการเทียบ</li>"
    if vid not in sm.index or prev not in sm.index:
        return "<li>รอผลรัน 3 รอบ</li>"
    cur, pre = sm.loc[vid], sm.loc[prev]
    label = {c: h for h, c, _ in COLS}
    fmt = {c: f for _, c, f in COLS}
    better = {c: b for _, c, _, b in METRICS}
    out = []
    for col in dict.fromkeys(v["target"] + GUARD):
        if col not in sm.columns or pd.isna(cur.get(col)) or pd.isna(pre.get(col)):
            continue
        d = cur[col] - pre[col]
        if min(cur["runs"], pre["runs"]) < MIN_RUNS:
            tag = "<span class='vtag same'>ยังรันไม่ครบ 3 รอบ ยังสรุปไม่ได้</span>"
        elif d == 0:
            tag = "<span class='vtag same'>เท่าเดิม</span>"
        elif overlap(pre, cur, col):
            tag = "<span class='vtag same'>อยู่ในความแปรปรวนระหว่างรอบ</span>"
        elif (d > 0) == better[col]:
            tag = "<span class='vtag good'>ดีขึ้นชัดเจน</span>"
        else:
            tag = "<span class='vtag bad'>แย่ลงชัดเจน</span>"
        mark = " <span class='small'>(เป้าของการแก้)</span>" if col in v["target"] else ""
        out.append(f"<li>{escape(label[col])}: {fmt[col].format(pre[col])} → <b>{fmt[col].format(cur[col])}</b> {tag}{mark}</li>")
    n = f"{int(cur['runs'])}/{RUNS} และ {int(pre['runs'])}/{RUNS} รอบ"
    return "".join(out) + f"<li class='small'>เทียบกับ {prev} · ค่าเฉลี่ย ({n})</li>"


def flow_html(flow):
    parts = []
    for text, kind in flow:
        tg = {"new": "<span class='tg'>+ เพิ่ม</span>", "chg": "<span class='tg'>~ เปลี่ยน</span>"}.get(kind, "")
        cls = {"new": " vnew", "chg": " vchg"}.get(kind, "")
        parts.append(f"<div class='vst{cls}'>{tg}{escape(text)}</div>")
    return "<div class='vflow'>" + "<span class='ar'>→</span>".join(parts) + "</div>"


def steps_block(sm):
    cards = []
    for vid, v in VERSIONS.items():
        added = [t for t, k in v["flow"] if k == "new"]
        changed = [t for t, k in v["flow"] if k == "chg"]
        what = "".join(f"<li><b>เพิ่ม:</b> {escape(t)}</li>" for t in added) +                "".join(f"<li><b>เปลี่ยน:</b> {escape(t)}</li>" for t in changed)
        steps = "".join(f"<li>{escape(st)}</li>" for st in v["steps_th"])
        cards.append(f"""<div class="vcard" id="ver-{vid}">
      <h4>{vid} · {escape(v['name_th'])} <span class='small'><code>{v['commit']}</code> · {escape(v['concept'])}</span></h4>
      {flow_html(v['flow'])}
      <div class="grid2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px">
        <div class="vweak"><b class="small">① ปัญหาที่พบ (ทำไมต้องมีเวอร์ชันนี้)</b><ul><li>{escape(v['weakness_th'])}</li></ul></div>
        <div><b class="small">② สิ่งที่เพิ่ม / เปลี่ยน (ทางแก้)</b><ul>{what or '<li>–</li>'}</ul></div>
        <div><b class="small">③ ทำไมควรช่วยได้</b><ul><li>{escape(v['why_th'])}</li></ul></div>
        <div><b class="small">④ ผลที่วัดได้</b><ul>{effect_items(vid, sm)}</ul></div>
      </div>
      <details><summary class="small">ขั้นตอนของ harness ทั้งหมด</summary><ol class="small">{steps}</ol></details>
    </div>""")
    for vid, v in PLANNED.items():
        added = [t for t, k in v["flow"] if k == "new"]
        changed = [t for t, k in v["flow"] if k == "chg"]
        what = "".join(f"<li><b>เพิ่ม:</b> {escape(t)}</li>" for t in added) +                "".join(f"<li><b>เปลี่ยน:</b> {escape(t)}</li>" for t in changed)
        label = {c: h for h, c, _ in COLS}
        tgt = "".join(f"<li>{escape(label[c])}</li>" for c in v["target"]) or "<li>ต้องเพิ่มการทดสอบใหม่ (ดูช่องซ้าย)</li>"
        cards.append(f"""<div class="vcard plan" id="ver-{vid}">
      <h4>{vid} · {escape(v['name_th'])} <span class='small'>แผน · ยังไม่ได้สร้าง · {escape(v['concept'])}</span></h4>
      {flow_html(v['flow'])}
      <div class="grid2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px">
        <div class="vweak"><b class="small">① ปัญหาที่พบ (ทำไมต้องมีเวอร์ชันนี้)</b><ul><li>{escape(v['weakness_th'])}</li></ul></div>
        <div><b class="small">② จะเพิ่ม / เปลี่ยน (ทางแก้)</b><ul>{what}</ul></div>
        <div><b class="small">③ ทำไมควรช่วยได้ (สมมติฐาน)</b><ul><li>{escape(v['why_th'])}</li></ul></div>
        <div><b class="small">④ ตัดสินด้วยตัวชี้วัด (รัน 3 รอบ เทียบเวอร์ชันก่อน)</b><ul>{tgt}<li class="small">ต้องไม่แย่ลงชัดเจน: มี/ไม่มีถูก · quote จริง · ถูกหลอก</li></ul></div>
      </div>
    </div>""")
    return f"""{FLOW_CSS}<div class="fig" id="fig-harness-steps">
    <div class="fig-title"><h3>แต่ละเวอร์ชัน: ปัญหาที่พบ → ทางแก้ → ทำไมควรช่วย → ผลที่วัดได้</h3><span class="small">
    <span class='vtag good'>+ เพิ่ม</span> ขั้นที่เพิ่มในเวอร์ชันนั้น · <span class='vtag' style='color:var(--warn);background:var(--warn-bg)'>~ เปลี่ยน</span> ขั้นที่แก้ · กรอบธรรมดา = เหมือนเวอร์ชันก่อน ·
    ผลที่วัดได้ใช้เกณฑ์เดียวกับตาราง: ชัดเจนเมื่อช่วงของ 3 รอบไม่ซ้อนกัน</span></div>
    {''.join(cards)}
  </div>
"""


def protocol_block():
    return """<div class="fig" id="fig-protocol">
    <div class="fig-title"><h3>วิธีทดสอบที่ใช้เทียบทุกเวอร์ชัน</h3><span class="small">ฉบับเต็ม: docs/EVALUATION.md ใน repo</span></div>
    <ol class="small">
      <li><b>คงที่ทุกเวอร์ชัน:</b> โค้ดทดสอบ (eval/) กฎ 5 ข้อ สัญญา 6 ฉบับ ไฟล์ฝังคำสั่ง model temperature งบ call และโค้ดให้คะแนน · <b>เปลี่ยน:</b> เฉพาะ src/ ตาม commit ของเวอร์ชันนั้น</li>
      <li><b>ทดสอบ offline ก่อน</b> (ไม่ใช้ API): offline_check และ test_harness_offline ต้องผ่านก่อนรันจริง</li>
      <li><b>รัน 3 รอบต่อเวอร์ชัน</b> (eval.run_versions): checkout commit ของเวอร์ชันลง git worktree ชั่วคราว ใส่โค้ดทดสอบชุดปัจจุบัน แล้วรันตรวจปกติ 6 ฉบับ ตามด้วยทดสอบคำสั่งแฝง A และ B ใน 3 ฉบับ เทียบกับรอบปกติของรอบเดียวกัน · เก็บผลและ trace ทุก call แยกโฟลเดอร์ต่อรอบ</li>
      <li><b>ให้คะแนนด้วยโค้ดเดียว</b> (eval.compare_versions) แสดงค่าเฉลี่ย และช่วงต่ำสุด–สูงสุดของ 3 รอบ</li>
      <li><b>เกณฑ์เทียบ:</b> ต่างกันชัดเจน เมื่อช่วงของสองเวอร์ชันไม่ซ้อนกันเท่านั้น ถ้าซ้อนกัน ถือว่าอยู่ในความแปรปรวนระหว่างรอบ ไม่นับเป็นการปรับปรุง</li>
      <li><b>เกณฑ์รับเวอร์ชันใหม่:</b> มี/ไม่มีถูก และ quote จริง ไม่ลดลงชัดเจน · ถูกหลอกไม่เพิ่มขึ้นชัดเจน · ตัวชี้วัดที่การแก้นั้นตั้งใจแก้ขยับไปทางที่ต้องการ · ไม่ผ่าน: ย้อนกลับหรือออกแบบใหม่ และยังบันทึกผลไว้</li>
    </ol>
  </div>
"""


def setup_block():
    """Test setup, read from the actual files: which PDFs, how many pages, which model and rules."""
    import pymupdf
    from src import config
    from eval.cuad import pdf_path
    from eval.offline_check import DEV_SET
    inj = {p.name.split("_", 1)[1][:30] for p in (OUT / "injection").glob("INJECTEDB_*.pdf")}
    rows = []
    for f in DEV_SET:
        n = len(pymupdf.open(pdf_path(f)))
        used = "✓ (A และ B)" if f[:30] in inj else ""
        rows.append(f"<tr><td>{escape(f.split('-EX-')[0].split('_')[0])}</td><td>{escape(f.split('-EX-')[1].split('-', 1)[1].replace('.PDF', '').split(' - ')[0].strip().title())}</td>"
                    f"<td>{n}</td><td>{used}</td></tr>")
    rules = " · ".join(f"{r['id']} {escape(r['title'])}" for r in config.load_playbook())
    return f"""<div class="fig" id="fig-testset">
    <div class="fig-title"><h3>ชุดทดสอบที่ใช้กับทุกเวอร์ชัน</h3><span class="small">ทุกเวอร์ชันวัดด้วยสัญญา กฎ model และโค้ดให้คะแนนชุดเดียวกัน</span></div>
    <div class="tbox"><table class="t" style="min-width:520px"><thead><tr><th>สัญญา (CUAD v1, ภาษาอังกฤษ)</th><th>ประเภท</th><th>หน้า</th><th>ใช้ทดสอบ prompt injection</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <p class="small"><b>กฎ 5 ข้อ:</b> {rules} · 6 สัญญา × 5 กฎ = 30 การตัดสินต่อโหมด ให้คะแนน "มี/ไม่มี" ได้ 24 (กฎต่ออายุอัตโนมัติไม่นับ) ·
    <b>Prompt injection:</b> 3 สัญญาแรก × 2 แบบ (A คำสั่งตรง ๆ กลางเอกสาร · B ประกาศปลอมจากฝ่ายกฎหมายหน้าเรื่องความรับผิด) = 6 ไฟล์ · ทั้งสองโหมด ·
    <b>Model:</b> {escape(config.MODEL)} ทุก call ทุกโหมดทุกเวอร์ชัน · temperature 0 · ไม่ใช้ vision ({escape(config.VISION_MODEL)}) เพราะทุกไฟล์เป็น PDF ข้อความ</p>
    <p class="small"><b>ขอบเขตของผล:</b> 6 สัญญาสั้น (7–17 หน้า) ยังน้อยเกินสรุปเชิงสถิติ · ทดสอบกับ model เดียว · รัน 3 รอบต่อเวอร์ชัน (ยังน้อยสำหรับทดสอบนัยสำคัญ ใช้ช่วงต่ำสุด–สูงสุดแทน) · ยังไม่มีสัญญายาวเกิน 100 หน้าและสัญญาภาษาไทยที่มีเฉลย</p>
  </div>
"""


def build():
    sm = pd.read_csv(BASE / "summary.csv").set_index("version")
    head = ["", "เวอร์ชัน · เปลี่ยนอะไร", "บทเรียนที่ใช้", *[h for h, _, _ in COLS], "ผลตัดสินเปลี่ยนระหว่างรอบ", "รอบ", "โค้ด"]
    rows = []
    for vid, v in VERSIONS.items():
        if vid in sm.index:
            rows.append(row(vid, sm.loc[vid]))
        else:  # batch not reached this version yet
            rows.append([f"<b>{vid}</b>", f"<b>{escape(v['name_th'])}</b><br><span class='small'>{escape(v['change_th'])}</span>",
                         escape(v["concept"])] + ["–"] * len(COLS) + ["–", f"0/{RUNS}", f"<code>{v['commit']}</code>"])
    done = {vid: int(sm.loc[vid, "runs"]) if vid in sm.index else 0 for vid in VERSIONS}
    status = ("ครบ 3 รอบทุกเวอร์ชัน" if all(n >= RUNS for n in done.values()) else
              "ยังไม่ครบ · รอบที่เสร็จแล้ว: " + " · ".join(f"{k} {n}/{RUNS}" for k, n in done.items())
              + " · ตัวเลขของเวอร์ชันที่ยังไม่ครบ 3 รอบเป็นค่าชั่วคราว ยังใช้เทียบไม่ได้")
    rows += [[f"<b>{a}</b>", f"<b>{escape(b)}</b><br><span class='small'>แผน · ยังไม่ได้สร้าง</span>", escape(c)]
             + ["–"] * (len(COLS) + 3) for a, (b, c) in ((k, (v["name_th"], v["concept"])) for k, v in PLANNED.items())]
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    tb = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return protocol_block() + setup_block() + steps_block(sm) + f"""<div class="fig" id="fig-versions">
    <div class="fig-title"><h3>วิวัฒนาการของระบบ: แต่ละเวอร์ชันเปลี่ยน harness อะไร และผลเปลี่ยนอย่างไร</h3><span class="small">ค่าเฉลี่ยของรอบที่รัน · ตัวเลขเล็กคือช่วงต่ำสุด–สูงสุด (แสดงเมื่อรอบต่างกัน)</span></div>
    <p class="note"><b>สถานะ:</b> {status}</p>
    <p class="small">Baseline: SC1 → SC2 · Agent: {' → '.join(k for k in VERSIONS if k.startswith('V'))} → <span class='small'>{' → '.join(PLANNED)} (แผน)</span></p>
    <div class="tbox"><table class="t"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>
    <p class="small">นิยามตัวชี้วัดทุกตัว: docs/EVALUATION.md หัวข้อ 3 · ต้นทุนคิดจาก token × ราคาต่อ token แสดงเป็นบาทที่ {THB_PER_USD:.0f} บาท/US$ (US$ ในวงเล็บ) ·
    เวลารวมช่วงพัก 1 วินาทีระหว่าง call · "ผลตัดสินเปลี่ยนระหว่างรอบ" = คู่สัญญา × กฎ ที่ได้คำตอบไม่เหมือนกันทุกรอบ ทั้งที่โค้ดเดิม</p>
  </div>
"""


if __name__ == "__main__":
    html = build()
    Path(sys.argv[1]).write_text(html, encoding="utf-8")
    print(re.sub(r"<[^>]+>", " ", re.search(r"<tbody>(.*)</tbody>", html, re.S).group(1)).replace("  ", " ")[:1500])
