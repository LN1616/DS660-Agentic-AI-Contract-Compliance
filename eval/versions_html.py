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

from src import config
from eval.compare_versions import BASE, METRICS, MIN_RUNS, THB_PER_USD, overlap
from eval.versions import PLANNED, VERSIONS

RUNS = 3  # runs per version in the protocol

# (column header, summary.csv column, format) — definitions: docs/EVALUATION.md section 3
COLS = [("มี/ไม่มีถูก (จาก 24)", "presence", "{:.1f}"), ("quote จริง", "quote_real", "{:.0%}"), ("quote ตรงข้อที่ CUAD เฉลย", "quote_gold", "{:.0%}"),
        ("ประกาศปลอม B หลอกได้ (จาก 15)", "fooled_B", "{:.1f}"), ("คำสั่งตรง A หลอกได้ (จาก 15)", "fooled_A", "{:.1f}"),
        ("สรุปทวนข้อความหลอก (จาก 3)", "claim_B", "{:.1f}"), ("call เฉลี่ย/กฎ", "steps", "{:.1f}"),
        ("ใช้ครบ 10 call (จาก 30)", "budget_hits", "{:.1f}"), ("ตัวตรวจซ้ำตีกลับ", "sendbacks", "{:.1f}"),
        ("เรียก tool ซ้ำตรงตัว", "repeats", "{:.1f}"), ("เวลา/ฉบับ (วิ)", "sec", "{:.0f}"), ("ต้นทุน/ฉบับ (บาท)", "thb", "{:.2f}"),
        ("token ขาเข้า/ฉบับ (พัน)", "tok_in", "{:.1f}"), ("call ที่ model สำรองตอบ", "fallback", "{:.0f}"),
        ("คำอธิบายปัญหายึดสัญญา (faithfulness)", "faith_issue", "{:.0%}"), ("บทสรุปยึดผลรายข้อ (faithfulness)", "faith_summary", "{:.0%}"),
        ("คำอธิบายยึดสัญญา เฉพาะข้อเท็จจริง", "faith_issue_fact", "{:.0%}"), ("บทสรุปยึดผล เฉพาะข้อเท็จจริง", "faith_summary_fact", "{:.0%}"),
        ("บทสรุปขัดผลตัดสินของโค้ด (จาก 6)", "summary_bad", "{:.1f}"), ("tool error ต่อ call", "tool_err", "{:.1%}")]


def cell(r, col, fmt):
    if col not in r or pd.isna(r[col]):
        return "–"
    lo, hi = r[col + "_min"], r[col + "_max"]
    rng = "" if lo == hi else f"<br><span class='small'>{fmt.format(lo)}–{fmt.format(hi)}</span>"
    return fmt.format(r[col]) + rng


def row(vid, r):
    v = VERSIONS[vid]
    cells = [cell(r, c, f) for _, c, f in COLS]
    cells[[c for _, c, _ in COLS].index("thb")] += f"<br><span class='small'>(${r['usd']:.4f})</span>"
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
        <div><b class="small">④ ผลที่วัดได้</b><ul>{effect_items(vid, sm)}{v.get('extra_th', '')}</ul></div>
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


def _short(c):
    return c.split("_")[0].split("-EX-")[0].replace("INC", " INC").replace("CORP", " CORP").replace("LTD", " LTD").strip()


def _marks(preds_ok):
    """One mark per run: ✓ right vs CUAD, ✗ wrong."""
    return "".join("<span style='color:var(--ok,#16a34a)'>✓</span>" if ok else "<span style='color:var(--bad,#dc2626)'>✗</span>"
                   for ok in preds_ok)


def answer_matrix_block():
    """Every graded cell (contract × rule) against the CUAD answer, per version and per run. Saved rows only, no API."""
    import glob
    rules = {r["id"]: r for r in config.load_playbook()}
    graded = [k for k, r in rules.items() if r["if_absent"] == "MISSING"]
    data, vids = {}, []
    for vid, v in VERSIONS.items():
        runs = sorted(glob.glob(str(OUT / "versions" / v["commit"] / "run*" / "eval_rows.csv")))
        if not runs:
            continue
        vids.append(vid)
        for i, fp in enumerate(runs):
            d = pd.read_csv(fp)
            d = d[d.system.str.startswith(v["mode"])]
            for _, x in d.iterrows():
                data.setdefault((x.contract, x.rule), {"exp": x.expected}).setdefault(vid, []).append(
                    (bool(x.presence_correct) if pd.notna(x.presence_correct) else None, x.predicted))
    if not data:
        return ""
    th = "".join(f"<th>{vid}</th>" for vid in vids)
    body, tot = [], {vid: [0, 0] for vid in vids}
    hard = []
    for (c, rid), cellv in sorted(data.items()):
        if rid not in graded:
            continue
        exp = "มี" if cellv["exp"] == "PRESENT" else "ไม่มี"
        tds, wrong_all = [], 0
        for vid in vids:
            runs = cellv.get(vid, [])
            ok = [bool(o) for o, _ in runs]
            tot[vid][0] += sum(ok)
            tot[vid][1] += len(ok)
            wrong_all += len(ok) - sum(ok)
            tip = " · ".join(p for _, p in runs)
            tds.append(f"<td title='{escape(tip)}' style='text-align:center;letter-spacing:1px'>{_marks(ok)}</td>")
        total_runs = sum(len(cellv.get(v, [])) for v in vids)
        if wrong_all == total_runs:
            hard.append(f"{_short(c)} {rid}")
        body.append(f"<tr><td>{escape(_short(c))}</td><td>{rid} {escape(rules[rid]['title'])}</td><td><b>{exp}</b></td>{''.join(tds)}</tr>")
    foot = "".join(f"<td style='text-align:center'><b>{a}/{n}</b><br><span class='small'>≈ {a / max(n, 1) * 24:.1f} จาก 24</span></td>"
                   for a, n in tot.values())
    return f"""<div class="fig" id="fig-answers">
    <div class="fig-title"><h3>ผลรายข้อเทียบเฉลย CUAD ทุกเวอร์ชัน</h3><span class="small">24 ข้อที่ให้คะแนนได้ × 3 รอบต่อเวอร์ชัน · จากผลที่เก็บไว้ ไม่เรียก API · ชี้เมาส์ที่ช่องเพื่อดูคำตอบแต่ละรอบ</span></div>
    <div class="tbox"><table class="t" style="min-width:720px"><thead><tr><th>สัญญา</th><th>กฎ</th><th>เฉลย CUAD<br><span class='small'>มีข้อนี้ไหม</span></th>{th}</tr></thead>
    <tbody>{''.join(body)}<tr><td colspan="3"><b>รวมถูก</b> (ทุกรอบ)</td>{foot}</tr></tbody></table></div>
    <p class="small"><b>อ่านตาราง:</b> 1 เครื่องหมายต่อ 1 รอบ · ✓ = ตอบเรื่อง "มี/ไม่มีข้อนี้" ตรงเฉลย · ✗ = ไม่ตรง ·
    ตรงเฉลยคือ ตอบ MISSING เมื่อ CUAD ไม่มีข้อนี้ และตอบสถานะอื่นเมื่อ CUAD มี · กฎ P-03 ต่ออายุอัตโนมัติไม่นับ เพราะกรณีไม่มีข้อนี้ใช้สถานะอื่นแทน MISSING ·
    <b>ผิดทุกเวอร์ชันทุกรอบ:</b> {escape(' · '.join(hard)) or 'ไม่มี'}</p>
  </div>
"""


LONG_SET = [("SC2", "de66498", "B2"), ("V6", "e0a1dcc", "A1"), ("V7", "e100ccf", "A1")]  # test 22, 3 runs each


def _long_runs(commit):
    import glob
    return [Path(p).parent for p in sorted(glob.glob(str(OUT / "versions_long" / commit / "run*" / "eval_rows.csv")))]


def long_stats():
    """Per version on the long set: one dict per run (presence, quotes, time, cost, flagged wrong answers)."""
    import glob
    import json
    from eval.compare_versions import gold_match
    res = {}
    for vid, commit, mode in LONG_SET:
        runs = []
        for d in _long_runs(commit):
            x = pd.read_csv(d / "eval_rows.csv")
            x = x[x.system.str.startswith(mode)]
            g = x[x.presence_correct.notna()]
            verified = {}
            for fp in glob.glob(str(d / "eval_reports" / f"{mode}_*.json")):
                rep = json.load(open(fp, encoding="utf-8"))
                for f in rep["findings"]:
                    verified[(rep["contract_title"][:40], f["finding"]["policy_id"])] = f.get("verified")
            wrong = g[~g.presence_correct.astype(bool)]
            flagged = sum(verified.get((r.contract, r.rule)) is False for _, r in wrong.iterrows())
            hit, tot = gold_match(d, mode)
            n = x.contract.nunique()
            runs.append({"presence": int(g.presence_correct.astype(bool).sum()), "graded": len(g),
                         "quote_real": float(x.quote_real.dropna().mean()) if x.quote_real.notna().any() else None,
                         "quote_gold": hit / tot if tot else None, "gold_txt": f"{hit}/{tot}",
                         "wrong": len(wrong), "flagged": flagged,
                         "budget_hits": int((g.steps >= 10).sum()) if mode == "A1" else None,
                         "sec": x.sec.sum() / n, "thb": x.cost_usd.sum() / n * THB_PER_USD})
        res[vid] = runs
    return res


def long_table_block():
    """Test 22 summary: SC2 vs V6 vs V7 on the long set, mean and min-max over the runs (same rule as the short set)."""
    st = long_stats()
    if not any(st.values()):
        return ""
    def c(runs, k, fmt):
        v = [r[k] for r in runs if r.get(k) is not None]
        if not v:
            return "–"
        m, lo, hi = sum(v) / len(v), min(v), max(v)
        return fmt.format(m) + ("" if lo == hi else f"<br><span class='small'>{fmt.format(lo)}–{fmt.format(hi)}</span>")
    rows = []
    for vid, _, mode in LONG_SET:
        runs = st.get(vid) or []
        if not runs:
            rows.append(f"<tr><td><b>{vid}</b></td>" + "<td>–</td>" * 8 + f"<td>0/{RUNS}</td></tr>")
            continue
        fl = (f"{sum(r['flagged'] for r in runs)}/{sum(r['wrong'] for r in runs)}" if mode == "A1" else "–")
        rows.append(f"<tr><td><b>{vid}</b></td><td>{c(runs, 'presence', '{:.1f}')}</td><td>{c(runs, 'quote_real', '{:.0%}')}</td>"
                    f"<td>{c(runs, 'quote_gold', '{:.0%}')}</td><td>{c(runs, 'wrong', '{:.1f}')}</td><td>{fl}</td>"
                    f"<td>{c(runs, 'budget_hits', '{:.1f}') if mode == 'A1' else '–'}</td><td>{c(runs, 'sec', '{:.0f}')}</td>"
                    f"<td>{c(runs, 'thb', '{:.2f}')}</td><td>{len(runs)}/{RUNS}</td></tr>")
    return f"""<div class="fig" id="fig-long">
    <div class="fig-title"><h3>สัญญายาว (ข้อ 22): single call เทียบ V6 และ V7</h3><span class="small">4 ฉบับ 75–154 หน้า · 3 รอบต่อเวอร์ชัน · แต่ละเวอร์ชันรันจาก commit ของตัวเอง · งบ 10 call ทุกเวอร์ชัน</span></div>
    <div class="tbox"><table class="t" style="min-width:720px"><thead><tr><th></th><th>มี/ไม่มีถูก (จาก 16)</th><th>quote จริง</th>
    <th>quote ตรงข้อที่ CUAD เฉลย</th><th>ตอบผิด (จาก 16)</th><th>ข้อที่ผิดถูกติดธงให้คนตรวจ<br><span class='small'>รวมทุกรอบ</span></th>
    <th>ใช้ครบ 10 call (จาก 16)</th><th>เวลา/ฉบับ (วิ)</th><th>ต้นทุน/ฉบับ (บาท)</th><th>รอบ</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <p class="small">เกณฑ์เดียวกับสัญญาสั้น: ต่างกันชัดเจนเมื่อช่วงต่ำสุด–สูงสุดไม่ซ้อนกัน · รอบที่ 1 ของ SC2 และ V6 คือรอบสัญญายาววันที่ 21 พ.ย. (โค้ดตรงกับ commit ของเวอร์ชัน) ·
    การทดลองเพิ่มงบเป็น 16 call (V6 1 รอบ: มี/ไม่มีถูก 8/16 · งบหมด 4/16 · 1.51 บาทต่อฉบับ) เป็นการทดลองข้างเคียง ไม่นับในตารางนี้</p>
  </div>
"""


def long_matrix_block():
    """Long set per rule vs CUAD: one mark per run for SC2, V6, V7 (same layout as the short-set matrix)."""
    rules = {r["id"]: r for r in config.load_playbook()}
    data, vids = {}, []
    for vid, commit, mode in LONG_SET:
        runs = _long_runs(commit)
        if not runs:
            continue
        vids.append(vid)
        for d in runs:
            x = pd.read_csv(d / "eval_rows.csv")
            x = x[x.system.str.startswith(mode) & x.presence_correct.notna()]
            for _, r in x.iterrows():
                data.setdefault((r.contract, r.rule), {"exp": r.expected}).setdefault(vid, []).append(
                    (bool(r.presence_correct), r.predicted))
    if not data:
        return ""
    th = "".join(f"<th>{vid}</th>" for vid in vids)
    body, tot = [], {vid: [0, 0] for vid in vids}
    for (c, rid), v in sorted(data.items()):
        tds = []
        for vid in vids:
            rr = v.get(vid, [])
            ok = [o for o, _ in rr]
            tot[vid][0] += sum(ok)
            tot[vid][1] += len(ok)
            tds.append(f"<td title='{escape(' · '.join(p for _, p in rr))}' style='text-align:center;letter-spacing:1px'>{_marks(ok)}</td>")
        exp = "มี" if v["exp"] == "PRESENT" else "ไม่มี"
        body.append(f"<tr><td>{escape(_short(c))}</td><td>{rid} {escape(rules[rid]['title'])}</td><td><b>{exp}</b></td>{''.join(tds)}</tr>")
    foot = "".join(f"<td style='text-align:center'><b>{a}/{n}</b></td>" for a, n in tot.values())
    return f"""<div class="fig" id="fig-answers-long">
    <div class="fig-title"><h3>สัญญายาว (ข้อ 22): ผลรายข้อเทียบเฉลย CUAD</h3><span class="small">4 ฉบับ × 4 กฎที่ให้คะแนนได้ · 1 เครื่องหมายต่อ 1 รอบ · ชี้เมาส์ดูคำตอบแต่ละรอบ</span></div>
    <div class="tbox"><table class="t" style="min-width:600px"><thead><tr><th>สัญญา</th><th>กฎ</th><th>เฉลย CUAD</th>{th}</tr></thead>
    <tbody>{''.join(body)}<tr><td colspan="3"><b>รวมถูก</b> (ทุกรอบ)</td>{foot}</tr></tbody></table></div>
  </div>
"""


def budget_block():
    """Why the call budget is 10: how many calls per rule the agent really used (saved runs, no API)."""
    import glob
    rows = []
    def add(label, frames, cap):
        d = pd.concat(frames) if frames else None
        if d is None or d.empty:
            return
        s = d.steps.dropna()
        rows.append(f"<tr><td>{label}</td><td>{len(s)}</td><td>{s.median():.0f}</td><td>{s.mean():.1f}</td><td>{int(s.max())}</td>"
                    f"<td>{int((s >= cap).sum())}/{len(s)} ({(s >= cap).mean():.0%})</td><td>{cap}</td></tr>")
    for vid, v in VERSIONS.items():
        if v["mode"] != "A1":
            continue
        fr = [pd.read_csv(f) for f in glob.glob(str(OUT / "versions" / v["commit"] / "run*" / "eval_rows.csv"))]
        add(f"{vid} · สัญญาสั้น", [f[f.system == "A1 agent"] for f in fr], 10)
    for vid, commit, mode in LONG_SET:
        if mode == "A1":
            fr = [pd.read_csv(d / "eval_rows.csv") for d in _long_runs(commit)]
            add(f"{vid} · สัญญายาว", [f[f.system == "A1 agent"] for f in fr], 10)
    side = OUT / "long_round" / "run2_budget" / "eval_rows.csv"
    if side.exists():
        f = pd.read_csv(side)
        add("V6 · สัญญายาว · ทดลองงบ 16 (1 รอบ)", [f[f.system == "A1 agent"]], 16)
    if not rows:
        return ""
    return f"""<div class="fig" id="fig-budget">
    <div class="fig-title"><h3>งบ call ต่อกฎ: ทำไมใช้ 10 และถ้าไม่จำกัดจะใช้เท่าไร</h3><span class="small">จากผลที่เก็บไว้ทุกรอบ ไม่เรียก API · 1 แถว = ทุกกฎทุกรอบของเวอร์ชันนั้น</span></div>
    <div class="tbox"><table class="t" style="min-width:620px"><thead><tr><th></th><th>จำนวนกฎ</th><th>call ต่อกฎ (มัธยฐาน)</th><th>ค่าเฉลี่ย</th><th>สูงสุด</th><th>ใช้ครบงบ</th><th>งบ</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>
    <ul class="small">
      <li><b>ถ้าไม่จำกัด ไม่มีเพดานตามธรรมชาติ:</b> กฎหนึ่งจบเมื่อ agent ส่งคำตอบแล้วตัวตรวจซ้ำผ่าน หรือส่งครบ 3 ครั้ง (ตีกลับได้ 2 ครั้ง MAX_REJECTIONS) เท่านั้น ·
        ถ้า agent ค้นไปเรื่อย ๆ โดยไม่ส่งคำตอบ ไม่มีอะไรหยุดนอกจากงบ call · งบจึงเป็นตัวกันวนไม่จบและต้นทุนบานปลาย</li>
      <li><b>ที่มาของ 10 (ตั้งตั้งแต่ V1):</b> สัญญาสั้นใช้ราว 5–6 call ต่อกฎ · 10 เผื่อการตีกลับ 1–2 ครั้ง · ทุกเวอร์ชันใช้ 10 เท่ากัน ผลจึงเทียบกันได้ ·
        ค่า "สูงสุด 10" ในตารางเวอร์ชันคือเพดาน ไม่ใช่สิ่งที่วัดได้</li>
      <li><b>ทดลองงบ 16 บนสัญญายาว (V6 1 รอบ):</b> ใช้ครบงบลดลง แต่มี/ไม่มีถูก 9 → 8/16 · ต้นทุน 1.11 → 1.51 บาทต่อฉบับ (+36%) ·
        บางกฎใช้ครบ 16 แล้วยังผิด คือ agent ค้นด้วยคำใหม่ไปเรื่อย ๆ ไม่ได้ขาดแค่ call · และข้อที่ผิดผ่านตัวตรวจซ้ำ แทนที่จะถูกติดธงให้คนตรวจ
        → งบ 10 ทำหน้าที่เป็นตาข่ายนิรภัยด้วย: เมื่อหมดงบ คำตอบถูกติดธงให้คนตรวจ · ปิดงบตามความยาวไว้ (MAX_STEPS_LONG)</li>
      <li><b>call สูงสุดต่อฉบับ</b> (5 กฎ + สรุปผู้บริหาร 1 + cross-check 1 ตั้งแต่ V6): งบ 10 = 52 call · งบ 16 = 82 call · ไม่จำกัด = ไม่มีเพดาน ·
        กฎตรวจพร้อมกัน ค่าที่ใช้จริงราว 32–37 call ต่อฉบับ (สัญญาสั้น)</li>
    </ul>
  </div>
"""


def _old_long_matrix_block():
    """Superseded: 1-run long round (kept for the record)."""
    runs = [("single call", OUT / "long_round" / "run1", "B2"), ("V6 · งบ 10 call", OUT / "long_round" / "run1", "A1"),
            ("V6 · งบตามความยาว (16)", OUT / "long_round" / "run2_budget", "A1")]
    runs = [r for r in runs if (r[1] / "eval_rows.csv").exists()]
    if not runs:
        return ""
    rules = {r["id"]: r for r in config.load_playbook()}
    cells = {}
    for name, d, mode in runs:
        x = pd.read_csv(d / "eval_rows.csv")
        x = x[x.system.str.startswith(mode) & x.presence_correct.notna()]
        for _, r in x.iterrows():
            cells.setdefault((r.contract, r.rule), {"exp": r.expected})[name] = (bool(r.presence_correct), r.predicted, r.steps)
    th = "".join(f"<th>{escape(n)}</th>" for n, _, _ in runs)
    body, tot = [], {n: 0 for n, _, _ in runs}
    for (c, rid), v in sorted(cells.items()):
        tds = []
        for n, _, mode in runs:
            if n not in v:
                tds.append("<td>–</td>")
                continue
            ok, pred, steps = v[n]
            tot[n] += ok
            st = f" · {int(steps)} call" if mode == "A1" and pd.notna(steps) else ""
            tds.append(f"<td style='text-align:center'>{_marks([ok])} <span class='small'>{escape(pred)}{st}</span></td>")
        exp = "มี" if v["exp"] == "PRESENT" else "ไม่มี"
        body.append(f"<tr><td>{escape(_short(c))}</td><td>{rid} {escape(rules[rid]['title'])}</td><td><b>{exp}</b></td>{''.join(tds)}</tr>")
    n = len(cells)
    foot = "".join(f"<td style='text-align:center'><b>{t}/{n}</b></td>" for t in tot.values())
    return f"""<div class="fig" id="fig-answers-long">
    <div class="fig-title"><h3>สัญญายาว (ข้อ 22): ผลรายข้อเทียบเฉลย CUAD</h3><span class="small">4 ฉบับ 75–154 หน้า · 1 รอบ · จากผลที่เก็บไว้</span></div>
    <div class="tbox"><table class="t" style="min-width:720px"><thead><tr><th>สัญญา</th><th>กฎ</th><th>เฉลย CUAD</th>{th}</tr></thead>
    <tbody>{''.join(body)}<tr><td colspan="3"><b>รวมถูก</b></td>{foot}</tr></tbody></table></div>
  </div>
"""


def long_summary():
    """One-line result of the long round for a version measured only there (read from the saved summaries)."""
    import json
    parts = []
    for name, d in (("งบ 10 call", "run1"), ("งบตามความยาว 16 call", "run2_budget")):
        p = OUT / "long_round" / d / "long_round_summary.json"
        if not p.exists():
            continue
        s = json.load(open(p, encoding="utf-8"))["systems"]
        a, b = s.get("A1 agent", {}), s.get("B2 single call")
        parts.append(f"<b>{name}:</b> มี/ไม่มีถูก {a.get('presence')} · quote จริง {a.get('quote_real', 0):.0%} · quote ตรงข้อที่ CUAD เฉลย {a.get('quote_gold')} · "
                     f"{a.get('sec_per_contract'):.0f} วิ · {a.get('baht_per_contract'):.2f} บาทต่อฉบับ"
                     + (f" (single call: {b['presence']} · quote จริง {b['quote_real']:.0%} · {b['quote_gold']} · {b['sec_per_contract']:.0f} วิ · {b['baht_per_contract']:.2f} บาท)" if b else ""))
    if not parts:
        return "วัดบนสัญญายาว · ยังไม่มีผล"
    return ("<span class='small'><b>วัดบนสัญญายาว 4 ฉบับ (75–154 หน้า) 1 รอบ · ไม่เทียบตรงกับคอลัมน์สัญญาสั้นได้</b><br>"
            + "<br>".join(parts) + "<br>ผลรายข้อ: ตาราง \"สัญญายาว (ข้อ 22)\" ด้านบน</span>")


def faith_block(sm):
    """Package B results (eval/faithfulness.py on the saved reports of every run)."""
    need = ["faith_issue", "faith_issue_fact", "faith_summary", "faith_summary_fact", "summary_bad"]
    if not all(c in sm.columns for c in need):
        return ""
    def c(vid, col):
        if vid not in sm.index or pd.isna(sm.loc[vid].get(col)):
            return "–"
        r = sm.loc[vid]
        lo, hi = r[col + "_min"], r[col + "_max"]
        f = "{:.0%}" if col != "summary_bad" else "{:.0f}"
        return f.format(r[col]) + ("" if lo == hi else f"<br><span class='small'>{f.format(lo)}–{f.format(hi)}</span>")
    rows = "".join(f"<tr><td><b>{vid}</b></td><td>{c(vid, 'faith_issue_fact')}</td><td>{c(vid, 'faith_issue')}</td>"
                   f"<td>{c(vid, 'faith_summary_fact')}</td><td>{c(vid, 'faith_summary')}</td><td>{c(vid, 'summary_bad')}</td>"
                   f"<td>{c(vid, 'tool_err') if 'tool_err' in sm.columns else '–'}</td></tr>" for vid in VERSIONS if vid in sm.index)
    hc = (config.OUTPUT_DIR / "faithfulness_human_check.csv").exists()
    from eval.flows_html import CSS, faith_flow
    def rng(vids, col):
        v = [sm.loc[k, col] for k in vids if k in sm.index and pd.notna(sm.loc[k].get(col))]
        return f"{min(v):.0%}–{max(v):.0%}" if v else "–"
    ag, sc = [k for k in VERSIONS if k.startswith("V")], [k for k in VERSIONS if k.startswith("SC")]
    res = (f"<b>ผล (เฉพาะข้อเท็จจริง ค่าเฉลี่ยของแต่ละเวอร์ชัน):</b> คำอธิบายปัญหายึดสัญญา agent {rng(ag, 'faith_issue_fact')} · single call {rng(sc, 'faith_issue_fact')} · "
           f"บทสรุปยึดผลรายข้อ agent {rng(ag, 'faith_summary_fact')} · single call {rng(sc, 'faith_summary_fact')} · "
           f"บทสรุปที่ขัดผลตัดสินของโค้ด {int(sm['summary_bad'].fillna(0).sum())} ฉบับ · ยังเป็นค่าประมาณจนกว่าคนตรวจ 20 claim เสร็จ")
    return CSS + faith_flow(res) + f"""<div class="fig" id="fig-faith">
    <div class="fig-title"><h3>ชุดงาน B · ข้อความที่ AI เขียนยึดหลักฐานแค่ไหน (faithfulness)</h3><span class="small">eval/faithfulness.py · ใช้รายงานที่เก็บไว้ของทุกรอบ ไม่รัน agent ใหม่ · 3 รอบต่อเวอร์ชัน</span></div>
    <div class="tbox"><table class="t"><thead><tr><th></th><th>คำอธิบายปัญหายึดสัญญา<br><span class='small'>เฉพาะข้อเท็จจริง</span></th><th>คำอธิบาย<br><span class='small'>ทุก claim</span></th>
    <th>บทสรุปยึดผลรายข้อ<br><span class='small'>เฉพาะข้อเท็จจริง</span></th><th>บทสรุป<br><span class='small'>ทุก claim</span></th><th>บทสรุปขัดผลตัดสินของโค้ด<br><span class='small'>จาก 6</span></th><th>tool error ต่อ call</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
    <ul class="small">
      <li><b>วิธี:</b> AI ผู้ตรวจ (model เดียวกัน) แยกข้อความเป็น claim แล้วตัดสินทีละ claim ว่า context รองรับไหม · คะแนน = claim ที่รองรับ ÷ claim ทั้งหมด (แนวเดียวกับ RAGAS Faithfulness) ·
        context ของคำอธิบาย = ข้อความกฎ + หน้าสัญญาที่มีข้อความที่อ้าง (ไม่มีข้อความอ้าง: 3 ส่วนที่เกี่ยวข้องที่สุด) · context ของบทสรุป = ผลรายข้อทั้งหมด · ต้นทุนผู้ตรวจทั้งชุดราว 12 บาท</li>
      <li><b>"เฉพาะข้อเท็จจริง"</b> ตัด claim ที่เป็นคำแนะนำ (มีคำว่า ควร / ต้อง / แนะนำ) ออกด้วยโค้ด เพราะผู้ตรวจยังนับคำแนะนำเป็น claim ทั้งที่สั่งให้ตัดออก · รายงานทั้งสองแบบ</li>
      <li><b>อ่านผล:</b> agent เขียนคำอธิบายยึดสัญญามากกว่า single call (ราว 90–93% เทียบ 81–85%) และบทสรุปของ agent ยึดผลรายข้อ 89–98% เทียบ single call 73–84% · ระหว่าง V1–V4 อยู่ในความแปรปรวนระหว่างรอบ ·
        บทสรุปไม่มีฉบับใดขัดกับผลตัดสินการลงนามของโค้ด และไม่อ้างรหัสกฎที่ไม่มีอยู่ · tool error ของ V3–V4 เป็น 0 (V1–V2 ไม่มีบันทึกเส้นทางให้นับ)</li>
      <li><b>ยังเชื่อตัวเลขเต็มที่ไม่ได้:</b> ผู้ตรวจเป็น AI ยังต้องเทียบกับคนตรวจ 20 claim (ตรงกัน ≥ 80%) · {"แบบฟอร์มพร้อมแล้ว: <code>outputs/faithfulness_human_check.csv</code> (เฉลยของ AI แยกไว้อีกไฟล์)" if hc else "ยังไม่ได้สร้างแบบฟอร์ม"} · claim ที่ถูกตัดสินว่าไม่รองรับบางส่วนเป็นการตีความของระบบ (เช่น "ตามนโยบายถือเป็น DEVIATED") ไม่ใช่ข้อเท็จจริงที่ผิด</li>
    </ul>
  </div>
"""


def takeaways_block():
    """Key takeaways after every version has 3 runs on both test sets (22 Nov). Numbers: summary.csv and the long set."""
    return """<div class="fig" id="fig-takeaways">
    <div class="fig-title"><h3>Key takeaways (ทุกเวอร์ชัน 3 รอบ · 22 พ.ย.)</h3><span class="small">สัญญาสั้น 6 ฉบับ SC1–V7 · สัญญายาว 4 ฉบับ SC2 · V6 · V7 · เกณฑ์: ชัดเจนเมื่อช่วงต่ำสุด–สูงสุดไม่ซ้อนกัน</span></div>
    <ol class="small">
      <li><b>ความแม่นเรื่อง "มี/ไม่มีข้อนี้" ไม่ต่างกันชัดเจนในทุกเวอร์ชัน</b> · สัญญาสั้น 20.7–22.3 จาก 24 · สัญญายาว 9.0–10.7 จาก 16 · ช่วงซ้อนกันทั้งหมด ·
        ข้อที่ผิดกระจุกอยู่ไม่กี่ช่อง (สัญญาสั้น 20 จาก 24 ช่องถูกทุกเวอร์ชันทุกรอบ) และบางช่องเฉลยของ CUAD เองตีความได้สองทาง</li>
      <li><b>H1 ไม่เป็นจริง:</b> agent ไม่ได้หาข้อสัญญาเจอมากกว่า single call บนสัญญายาว (SC2 10.7 · V6 9.7 · V7 9.0 จาก 16)</li>
      <li><b>สิ่งที่ harness ให้จริง คือหลักฐานที่เชื่อได้และความผิดที่มองเห็น:</b> quote มีจริง 100% ใน agent ทุกเวอร์ชันบนสัญญายาว (single call 89%) ·
        quote ตรงข้อที่ CUAD เฉลย 92–93% เทียบ 80% · ข้อที่ผิดถูกติดธงให้คนตรวจ (V6 15 จาก 19)</li>
      <li><b>ความปลอดภัยแก้ได้ด้วย harness ไม่ใช่ด้วย prompt:</b> ประกาศปลอมหลอก single call ได้ 9 จาก 15 · prompt กันได้แค่ลดเหลือ 3.3 · agent ที่ห่อเนื้อสัญญาเป็นข้อมูลถูกหลอก 0 ทุกเวอร์ชันตั้งแต่ V2</li>
      <li><b>harness ลดต้นทุนและเวลาได้ชัดเจน:</b> V3 ตัวจับการค้นไม่คืบหน้า · V4 ตรวจกฎขนาน 36 → 31 วิ · V5 งบ context token −10% ต้นทุน 0.75 → 0.68 บาท ·
        แต่การเพิ่มความสามารถ (V6 tool ใหม่ ค้นหน้า 2 cross-check) ทำให้แพงขึ้น 0.68 → 0.86 บาทโดยไม่แม่นขึ้น</li>
      <li><b>แก้ตามหลักฐาน และยอมรับเมื่อสมมติฐานผิด:</b> งบ call 16 ไม่ช่วย (และซ่อนความผิดจากตัวตรวจซ้ำ) · prompt ของ V7 แก้ได้ 1 ข้อแต่ทำให้อีกข้อผิด ·
        ไล่ทีละข้อพบว่าสาเหตุที่เหลือคือคำค้นบนสัญญายาว (ข้อยกเว้นความเสียหายทางอ้อมไม่มีคำว่า liability) ไม่ใช่งบหรือการตีความ</li>
      <li><b>เลือกใช้:</b> V5 เป็นค่าเริ่มต้น (แม่นเท่ากันและถูกที่สุดในกลุ่ม agent) · V6 สำหรับสัญญายาวเมื่อต้องการ cross-check และตามอ้างอิง · single call เหมาะเป็น baseline หรือร่างแรกที่ต้องการเร็วและถูก แต่ต้องมีคนตรวจ quote และระวังข้อความหลอก</li>
      <li><b>ข้อจำกัด:</b> สัญญา 10 ฉบับและ model เดียว · 3 รอบยังน้อยสำหรับทดสอบนัยสำคัญ · faithfulness ของ V6/V7 ยังไม่ได้คำนวณ · prompt ของ V7 ไม่ได้ให้ single call ด้วย</li>
    </ol>
  </div>
"""


def build():
    sm = pd.read_csv(BASE / "summary.csv").set_index("version")
    head = ["", "เวอร์ชัน · เปลี่ยนอะไร", "บทเรียนที่ใช้", *[h for h, _, _ in COLS], "ผลตัดสินเปลี่ยนระหว่างรอบ", "รอบ", "โค้ด"]
    rows = []
    ncols = 3 + len(COLS) + 3
    for vid, v in VERSIONS.items():
        if vid in sm.index:
            rows.append(row(vid, sm.loc[vid]))
        elif v.get("eval_set") == "long":  # measured on the long round only: say so instead of "0/3"
            rows.append(f"<tr><td><b>{vid}</b></td><td><b>{escape(v['name_th'])}</b><br><span class='small'>{escape(v['change_th'])}</span></td>"
                        f"<td>{escape(v['concept'])}</td><td colspan='{ncols - 4}'>{long_summary()}</td><td><code>{v['commit']}</code></td></tr>")
        else:  # batch not reached this version yet
            rows.append([f"<b>{vid}</b>", f"<b>{escape(v['name_th'])}</b><br><span class='small'>{escape(v['change_th'])}</span>",
                         escape(v["concept"])] + ["–"] * len(COLS) + ["–", f"0/{RUNS}", f"<code>{v['commit']}</code>"])
    done = {vid: int(sm.loc[vid, "runs"]) if vid in sm.index else 0 for vid, v in VERSIONS.items()
            if v.get("eval_set") != "long"}
    longs = [vid for vid, v in VERSIONS.items() if v.get("eval_set") == "long"]
    status = ((f"ครบ 3 รอบทุกเวอร์ชันบนสัญญาสั้น ({', '.join(done)})" if all(n >= RUNS for n in done.values()) else
               "ยังไม่ครบ · รอบที่เสร็จแล้ว: " + " · ".join(f"{k} {n}/{RUNS}" for k, n in done.items())
               + " · ตัวเลขของเวอร์ชันที่ยังไม่ครบ 3 รอบเป็นค่าชั่วคราว ยังใช้เทียบไม่ได้")
              + (f" · {', '.join(longs)} วัดบนสัญญายาว 4 ฉบับแทน (ข้อ 22) ไม่ได้รันชุดสัญญาสั้นซ้ำเพื่อประหยัดต้นทุน"
                 " เพราะสิ่งที่เพิ่มมุ่งแก้สัญญายาว · ผลของ V6 บนสัญญาสั้นจึงยังไม่ได้วัด" if longs else ""))
    rows += [[f"<b>{a}</b>", f"<b>{escape(b)}</b><br><span class='small'>แผน · ยังไม่ได้สร้าง</span>", escape(c)]
             + ["–"] * (len(COLS) + 3) for a, (b, c) in ((k, (v["name_th"], v["concept"])) for k, v in PLANNED.items())]
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    tb = "".join(r if isinstance(r, str) else "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return takeaways_block() + protocol_block() + setup_block() + answer_matrix_block() + long_table_block() + long_matrix_block() + budget_block() + steps_block(sm) + faith_block(sm) + f"""<div class="fig" id="fig-versions">
    <div class="fig-title"><h3>วิวัฒนาการของระบบ: แต่ละเวอร์ชันเปลี่ยน harness อะไร และผลเปลี่ยนอย่างไร</h3><span class="small">ค่าเฉลี่ยของรอบที่รัน · ตัวเลขเล็กคือช่วงต่ำสุด–สูงสุด (แสดงเมื่อรอบต่างกัน)</span></div>
    <p class="note"><b>สถานะ:</b> {status}</p>
    <p class="small">Baseline: SC1 → SC2 · Agent: {' → '.join(k for k in VERSIONS if k.startswith('V'))}{(" → <span class='small'>" + ' → '.join(PLANNED) + " (แผน)</span>") if PLANNED else ""}</p>
    <div class="tbox"><table class="t"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>
    <p class="small">นิยามตัวชี้วัดทุกตัว: docs/EVALUATION.md หัวข้อ 3 · ต้นทุนคิดจาก token × ราคาต่อ token แสดงเป็นบาทที่ {THB_PER_USD:.0f} บาท/US$ (US$ ในวงเล็บ) ·
    เวลารวมช่วงพัก 1 วินาทีระหว่าง call · "ผลตัดสินเปลี่ยนระหว่างรอบ" = คู่สัญญา × กฎ ที่ได้คำตอบไม่เหมือนกันทุกรอบ ทั้งที่โค้ดเดิม</p>
  </div>
"""


if __name__ == "__main__":
    html = build()
    Path(sys.argv[1]).write_text(html, encoding="utf-8")
    print(re.sub(r"<[^>]+>", " ", re.search(r"<tbody>(.*)</tbody>", html, re.S).group(1)).replace("  ", " ")[:1500])
