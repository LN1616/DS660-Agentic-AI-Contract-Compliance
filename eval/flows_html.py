"""Flowcharts (Thai) for the guide, the presentation hub and the course notes, drawn as inline SVG.

Style follows the course figures (vertical main path, diamonds for questions, labelled arrows) with
colour by who acts: model (AI call) / code / person / outcome. Short words in the boxes, detail below.
  1. routing flow    - where a contract goes, AI calls per path
  2. decision flow   - inside one rule: how many steps, what stops the loop, who checks
  3. final decision  - sign-off: code first, people last (never the model alone)
  4. plan for failure- what the harness does when an AI call fails (built + planned)
Limits come from src.config / src.agent; measured calls per rule from outputs/versions/summary.csv.
Usage:  python -m eval.flows_html <out.html>
"""
import sys
from html import escape
from pathlib import Path

import pandas as pd

from src import agent, config
from eval.versions import VERSIONS

SUMMARY = config.ROOT / "outputs" / "versions" / "summary.csv"

CSS = """<style>
.dsvg{--n-bg:#FFFFFF;--n-line:#C9D1DD;--n-ink:#172031;--n-ink2:#5A6578;--n-edge:#7A859A;
  --n-llm:#EEEDFC;--n-llm-b:#7C74DB;--n-code:#F4F6F9;--n-code-b:#8A94A6;--n-hum:#FFF3DC;--n-hum-b:#E0A33A;
  --n-ok:#E3F4E7;--n-ok-b:#2E8B47;--n-warn:#FDF0DA;--n-warn-b:#C27C12;--n-bad:#FBE7E7;--n-bad-b:#C23B3B;
  --n-q:#FFFFFF;--n-q-b:#3F4A5C;--n-plan:#FFFFFF;--n-badge:#3F4A5C}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .dsvg{--n-bg:#1B2230;--n-line:#3A4557;--n-ink:#E6EAF2;--n-ink2:#AAB3C4;--n-edge:#8D98AC;
  --n-llm:#25224A;--n-llm-b:#9A93F0;--n-code:#202838;--n-code-b:#7D889C;--n-hum:#3A2D14;--n-hum-b:#E6B456;
  --n-ok:#173322;--n-ok-b:#5FC678;--n-warn:#3A2B12;--n-warn-b:#EFB35A;--n-bad:#3C1C1E;--n-bad-b:#F08080;--n-q:#1B2230;--n-q-b:#C5CEDC;--n-plan:#1B2230;--n-badge:#C5CEDC}}
:root[data-theme="dark"] .dsvg{--n-bg:#1B2230;--n-line:#3A4557;--n-ink:#E6EAF2;--n-ink2:#AAB3C4;--n-edge:#8D98AC;
  --n-llm:#25224A;--n-llm-b:#9A93F0;--n-code:#202838;--n-code-b:#7D889C;--n-hum:#3A2D14;--n-hum-b:#E6B456;
  --n-ok:#173322;--n-ok-b:#5FC678;--n-warn:#3A2B12;--n-warn-b:#EFB35A;--n-bad:#3C1C1E;--n-bad-b:#F08080;--n-q:#1B2230;--n-q-b:#C5CEDC;--n-plan:#1B2230;--n-badge:#C5CEDC}
.dsvg{display:grid;gap:8px;justify-items:center}
.dsvg svg{width:100%;max-width:780px;height:auto;display:block;font-family:inherit;color:var(--n-edge)}
.dsvg .t1{font-size:13.5px;font-weight:600;fill:var(--n-ink)} .dsvg .t2{font-size:11.5px;fill:var(--n-ink2)}
.dsvg .el{font-size:11.5px;font-weight:600;fill:var(--n-ink2)} .dsvg .elbg{fill:var(--n-bg)}
.dsvg .bd{font-size:10.5px;font-weight:600;fill:var(--n-bg)} .dsvg .bdbg{fill:var(--n-badge)}
.dsvg .edge{stroke:var(--n-edge);stroke-width:1.6;fill:none} .dsvg .edge.back{stroke-dasharray:6 4}
.dsvg .ah{fill:var(--n-edge)}
.dsvg .llm{fill:var(--n-llm);stroke:var(--n-llm-b);stroke-width:1.6} .dsvg .code{fill:var(--n-code);stroke:var(--n-code-b);stroke-width:1.4;stroke-dasharray:5 4}
.dsvg .hum{fill:var(--n-hum);stroke:var(--n-hum-b);stroke-width:1.6} .dsvg .q{fill:var(--n-q);stroke:var(--n-q-b);stroke-width:1.8}
.dsvg .ok{fill:var(--n-ok);stroke:var(--n-ok-b);stroke-width:1.8} .dsvg .warn{fill:var(--n-warn);stroke:var(--n-warn-b);stroke-width:1.8}
.dsvg .bad{fill:var(--n-bad);stroke:var(--n-bad-b);stroke-width:1.8} .dsvg .start{fill:var(--n-code);stroke:var(--n-q-b);stroke-width:1.6}
.dsvg .plan{fill:var(--n-plan);stroke:var(--n-code-b);stroke-width:1.4;stroke-dasharray:3 4}
.dsvg .lg{display:flex;flex-wrap:wrap;justify-content:center;gap:12px;font-size:12px;color:var(--n-ink2)}
.dsvg .lg i{display:inline-block;width:16px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.dsvg .notes{max-width:780px;width:100%;font-size:12.5px;color:var(--n-ink2);margin:0;padding-left:18px}
</style>"""

LEGEND = """<div class="lg"><span><i style="background:var(--n-llm);border:1.5px solid var(--n-llm-b)"></i>AI ตัดสิน (ใช้ call)</span>
<span><i style="background:var(--n-code);border:1.5px dashed var(--n-code-b)"></i>โค้ดตัดสิน (ไม่ใช้ call)</span>
<span><i style="background:var(--n-hum);border:1.5px solid var(--n-hum-b)"></i>คนตัดสิน</span>
<span><i style="background:var(--n-q);border:1.8px solid var(--n-q-b);transform:rotate(45deg) scale(.8)"></i>คำถาม</span>
<span><i style="border:1.5px dotted var(--n-code-b)"></i>แผน ยังไม่ได้สร้าง</span></div>"""

COLW, ROWH, PAD = 245, 100, 30
NODE = {"w": 196, "h": 56}
DIA = {"w": 224, "h": 82}


class Flow:
    def __init__(self, cols=3):
        self.cols, self.nodes, self.edges = cols, {}, []

    def n(self, key, col, row, kind, line1, line2="", badge="", shape=None):
        shape = shape or ("dia" if kind == "q" else "pill" if kind in ("start", "ok", "warn", "bad") else "rect")
        self.nodes[key] = dict(col=col, row=row, kind=kind, l1=line1, l2=line2, badge=badge, shape=shape)
        return self

    def e(self, a, b, label="", how="auto", side="R"):
        self.edges.append((a, b, label, how, side))
        return self

    # geometry
    def c(self, k):
        nd = self.nodes[k]
        return PAD + 40 + nd["col"] * COLW + COLW / 2, PAD + nd["row"] * ROWH + DIA["h"] / 2

    def size(self, k):
        nd = self.nodes[k]
        return (DIA["w"], DIA["h"]) if nd["shape"] == "dia" else (NODE["w"], NODE["h"])

    def pt(self, k, side):
        x, y = self.c(k)
        w, h = self.size(k)
        return {"T": (x, y - h / 2), "B": (x, y + h / 2), "L": (x - w / 2, y), "R": (x + w / 2, y)}[side]

    def svg(self, label):
        rows = max(n["row"] for n in self.nodes.values()) + 1
        W, H = PAD * 2 + 80 + self.cols * COLW, PAD * 2 + (rows - 1) * ROWH + DIA["h"]
        out = [f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="{escape(label)}">',
               '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
               'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ah"/></marker></defs>']
        labels = []
        lane = {"R": 0, "L": 0}
        for a, b, lab, how, side in self.edges:
            ax, ay = self.c(a); bx, by = self.c(b)
            na, nb = self.nodes[a], self.nodes[b]
            cls = "edge"
            if how == "back":  # loop back up, outside the boxes
                lane[side] += 1
                s, d = self.pt(a, side), self.pt(b, side)
                off = 26 + 14 * (lane[side] - 1)
                lx = (max(s[0], d[0]) + off) if side == "R" else (min(s[0], d[0]) - off)
                path = f"M{s[0]:.0f},{s[1]:.0f} H{lx:.0f} V{d[1]:.0f} H{d[0]:.0f}"
                cls += " back"
                lp = (lx - 6, (s[1] + d[1]) / 2, "end") if side == "R" else (lx - 6, (s[1] + d[1]) / 2, "end")
            elif na["col"] == nb["col"]:
                s, d = self.pt(a, "B"), self.pt(b, "T")
                path = f"M{s[0]:.0f},{s[1]:.0f} V{d[1]:.0f}"
                lp = (s[0] + 8, s[1] + 16, "start")
            elif na["row"] == nb["row"]:
                sd = "R" if bx > ax else "L"
                s, d = self.pt(a, sd), self.pt(b, "L" if sd == "R" else "R")
                path = f"M{s[0]:.0f},{s[1]:.0f} H{d[0]:.0f}"
                lp = ((s[0] + d[0]) / 2, s[1] - 7, "middle")
            elif na["shape"] == "dia":
                sd = "R" if bx > ax else "L"
                s, d = self.pt(a, sd), self.pt(b, "T")
                path = f"M{s[0]:.0f},{s[1]:.0f} H{d[0]:.0f} V{d[1]:.0f}"
                lp = ((s[0] + d[0]) / 2, s[1] - 7, "middle")
            else:  # join into another column further down
                s, d = self.pt(a, "B"), self.pt(b, "T")
                mid = d[1] - 18
                path = f"M{s[0]:.0f},{s[1]:.0f} V{mid:.0f} H{d[0]:.0f} V{d[1]:.0f}"
                lp = (s[0] + 8, s[1] + 16, "start")
            out.append(f'<path d="{path}" class="{cls}" marker-end="url(#ah)"/>')
            if lab:
                labels.append(lp + (lab,))
        for k, nd in self.nodes.items():
            x, y = self.c(k)
            w, h = self.size(k)
            if nd["shape"] == "dia":
                out.append(f'<polygon points="{x},{y - h / 2} {x + w / 2},{y} {x},{y + h / 2} {x - w / 2},{y}" class="{nd["kind"]}"/>')
            else:
                rx = h / 2 if nd["shape"] == "pill" else 10
                out.append(f'<rect x="{x - w / 2:.0f}" y="{y - h / 2:.0f}" width="{w}" height="{h}" rx="{rx:.0f}" class="{nd["kind"]}"/>')
            if nd["l2"]:
                out.append(f'<text x="{x:.0f}" y="{y - 3:.0f}" text-anchor="middle" class="t1">{escape(nd["l1"])}</text>')
                out.append(f'<text x="{x:.0f}" y="{y + 14:.0f}" text-anchor="middle" class="t2">{escape(nd["l2"])}</text>')
            else:
                out.append(f'<text x="{x:.0f}" y="{y + 5:.0f}" text-anchor="middle" class="t1">{escape(nd["l1"])}</text>')
            if nd["badge"]:
                bw = 12 + 6.4 * len(nd["badge"])
                bx, by = x + w / 2 - bw + 8, y - h / 2 - 9
                if nd["shape"] == "dia":
                    bx = x + 20
                out.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{bw:.0f}" height="18" rx="9" class="bdbg"/>'
                           f'<text x="{bx + bw / 2:.0f}" y="{by + 13:.0f}" text-anchor="middle" class="bd">{escape(nd["badge"])}</text>')
        for x, y, anchor, lab in labels:
            pw = 10 + 7 * len(lab)
            rx = x - pw / 2 if anchor == "middle" else (x - 3 if anchor == "start" else x - pw + 3)
            out.append(f'<rect x="{rx:.0f}" y="{y - 12:.0f}" width="{pw:.0f}" height="16" rx="4" class="elbg"/>'
                       f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" class="el">{escape(lab)}</text>')
        out.append("</svg>")
        return "".join(out)


def figure(fid, title, sub, flow, alt, notes):
    li = "".join(f"<li>{n}</li>" for n in notes)
    return (f'<div class="fig" id="{fid}"><div class="fig-title"><h3>{title}</h3><span class="small">{sub}</span></div>'
            f'<div class="dsvg">{LEGEND}{flow.svg(alt)}<ul class="notes">{li}</ul></div></div>')


def faith_flow(res: str = "") -> str:
    """Standard RAGAS faithfulness (left) next to how package B measures it (right), then the result."""
    f = (Flow(cols=2)
         .n("s0", 0, 0, "start", "📥 คำถาม + คำตอบ + context", "จากระบบ RAG ที่กำลังรัน")
         .n("s1", 0, 1, "llm", "แยกคำตอบเป็น statement", "ข้อความสั้นที่ตรวจได้ทีละข้อ", "call 1")
         .n("s2", 0, 2, "llm", "ตัดสินทีละ statement", "context รองรับไหม (ใช่ / ไม่)", "call 2")
         .n("s3", 0, 3, "code", "คะแนน = รองรับ ÷ ทั้งหมด", "0–1 · สูง = ยึดหลักฐาน")
         .n("s4", 0, 4, "ok", "คะแนนต่อคำตอบ")
         .n("o0", 1, 0, "start", "📂 รายงานที่เก็บไว้ 18 รอบ", "6 เวอร์ชัน × 3 รอบ · ไม่รันใหม่")
         .n("o1", 1, 1, "code", "โค้ดสร้าง context", "กฎ + หน้าที่อ้าง / ผลรายข้อ", "0 call")
         .n("o2", 1, 2, "llm", "แยก claim + ตัดสินในครั้งเดียว", "structured output · ถูกลงครึ่ง", "1 call")
         .n("o3", 1, 3, "code", "ตัด claim ที่เป็นคำแนะนำ", "ควร / ต้อง / แนะนำ → เฉพาะข้อเท็จจริง", "0 call")
         .n("o4", 1, 4, "code", "คะแนน 2 แบบ + ตรวจด้วยโค้ด", "บทสรุปขัดผลตัดสิน? · tool error")
         .n("o5", 1, 5, "hum", "คนตรวจ 20 claim แบบปิดเฉลย", "ตรงกับ AI ≥ 80% → เชื่อตัวเลขได้")
         .n("o6", 1, 6, "ok", "ผลต่อเวอร์ชัน → ตารางด้านล่าง")
         .e("s0", "s1").e("s1", "s2").e("s2", "s3").e("s3", "s4")
         .e("o0", "o1").e("o1", "o2").e("o2", "o3").e("o3", "o4").e("o4", "o5").e("o5", "o6"))
    notes = [
        "<b>ซ้าย · มาตรฐาน RAGAS Faithfulness:</b> ใช้ LLM 2 ขั้น ขั้นแรกแยกคำตอบเป็น statement ขั้นสองตัดสินแต่ละ statement กับ context ที่ระบบดึงมา (แบบ NLI) "
        "คะแนน = statement ที่ context รองรับ ÷ statement ทั้งหมด · วัดว่าคำตอบ <i>ยึดหลักฐานที่ดึงมา</i> ไม่ได้วัดว่าคำตอบถูกตามความจริง",
        "<b>ขวา · ของเรา (ชุดงาน B):</b> หลักเดียวกัน ต่างกัน 4 จุด ① ใช้รายงานที่เก็บไว้ ไม่รัน agent ใหม่ "
        "② context สร้างด้วยโค้ดตามชนิดข้อความ: คำอธิบายปัญหา = ข้อความกฎ + หน้าสัญญาที่มีข้อความที่อ้าง · บทสรุป = ผลรายข้อทั้งหมด "
        "③ รวม 2 ขั้นเป็น 1 call ด้วย structured output (ต้นทุนครึ่งหนึ่ง ทั้งชุดราว 12 บาท) ④ เพิ่มสิ่งที่ RAGAS ไม่มี: ตัดคำแนะนำออกด้วยโค้ด ตรวจบทสรุปกับผลตัดสินของโค้ด และให้คนตรวจผู้ตรวจ",
    ]
    if res:
        notes.append(res)
    return figure("fig-faithflow", "Faithfulness · มาตรฐาน RAGAS เทียบกับวิธีของเรา",
                  "ซ้าย: วิธีมาตรฐาน · ขวา: ชุดงาน B (eval/faithfulness.py)", f,
                  "ผังเทียบขั้นตอนวัด faithfulness แบบ RAGAS กับวิธีของโครงการ", notes)


def measured():
    if not SUMMARY.exists():
        return None
    sm = pd.read_csv(SUMMARY).set_index("version")
    for vid in reversed([v for v in VERSIONS if v.startswith("V")]):
        if vid in sm.index and sm.loc[vid, "runs"] >= 3 and pd.notna(sm.loc[vid].get("steps")):
            r = sm.loc[vid]
            return vid, r["steps"], r.get("budget_hits"), r["sec"]
    return None


def project_flows() -> str:
    S, R, T = config.MAX_STEPS, config.MAX_REJECTIONS, agent.QUOTE_THRESHOLD
    m = measured()
    meas = (f"วัดจริง ({m[0]}, เฉลี่ย 3 รอบ, สัญญา CUAD 6 ฉบับ): {m[1]:.1f} call ต่อกฎ · ใช้ครบงบ {S} call {m[2]:.0f} จาก 30 กฎ · "
            f"{m[3]:.0f} วินาทีต่อฉบับ" if m else "ยังไม่มีผลวัด 3 รอบ")

    f1 = (Flow()
          .n("pdf", 1, 0, "start", "📄 PDF สัญญา")
          .n("read", 1, 1, "code", "อ่าน + แบ่งเป็นข้อ", "pdfplumber · TF-IDF", "0 call")
          .n("q1", 1, 2, "q", "ชื่อสัญญาบอกประเภทไหม?")
          .n("title", 0, 3, "code", "โค้ดอ่านประเภทจากชื่อ", "97% ของ CUAD", "0 call")
          .n("ai", 2, 3, "llm", "AI ตัดสินจากเนื้อหา", "เมื่อชื่อไม่บอก")
          .n("party", 1, 4, "llm", "ระบุคู่สัญญา + เรื่อง", "เราอยู่ฝั่งไหน", "1 call")
          .n("q2", 1, 5, "q", "คลังมีนโยบายของประเภทนี้?")
          .n("lib", 0, 6, "code", "ใช้นโยบายในคลัง", "มีเวอร์ชัน + ผู้ยืนยัน", "0 call")
          .n("draft", 2, 6, "llm", "AI ร่างเกณฑ์ 6 ข้อ", "เป็นร่าง รอคนยืนยัน", "1 call")
          .n("q3", 1, 7, "q", "เลือกวิธีตรวจ")
          .n("single", 0, 8, "llm", "Single call", "ทุกกฎในครั้งเดียว", "1 call")
          .n("agent", 2, 8, "llm", "Agent · 5 กฎพร้อมกัน", "กฎละ ≤ 10 call → ผัง 2", f"≤ {5 * S} call")
          .n("sum", 1, 9, "llm", "สรุปผู้บริหาร", "", "1 call")
          .n("end", 1, 10, "start", "⚖️ ผลตัดสินการลงนาม → ผัง 3")
          .e("pdf", "read").e("read", "q1").e("q1", "title", "ใช่").e("q1", "ai", "ไม่")
          .e("title", "party").e("ai", "party").e("party", "q2")
          .e("q2", "lib", "มี").e("q2", "draft", "ไม่มี").e("lib", "q3").e("draft", "q3")
          .e("q3", "single", "เร็ว · ถูก").e("q3", "agent", "ตรวจละเอียด").e("single", "sum").e("agent", "sum").e("sum", "end"))
    n1 = [f"ต่อฉบับ: single call ≈ 3 call · agent ≤ {5 * S + 2} call (5 กฎ)",
          "ชื่อสัญญาบอกประเภท: โค้ดตัดสิน 494 จาก 510 ฉบับใน CUAD ถูก 97.2% · อีก 16 ฉบับให้ AI ตัดสิน",
          meas]

    f2 = (Flow()
          .n("rule", 1, 0, "start", "📋 กฎ 1 ข้อ", "")
          .n("pick", 1, 1, "llm", "AI เลือก tool", f"call 1 ถึง {S - 1}", "1 call")
          .n("q1", 1, 2, "q", "เลือกอะไร?")
          .n("tool", 0, 2, "code", "ค้น / อ่านสัญญา", "ตัวจับการค้นไม่คืบหน้า")
          .n("q2", 1, 3, "q", f"ตัวตรวจซ้ำผ่านไหม?")
          .n("ok", 1, 4, "ok", "✅ ได้ผลของกฎนี้")
          .n("q3", 2, 4, "q", f"ตีกลับครบ {R} ครั้ง?")
          .n("flag", 2, 5, "bad", "⚠️ เก็บไว้ · ให้คนตรวจ")
          .n("cap", 0, 4, "warn", f"⏱ call ที่ {S}: บังคับส่ง")
          .e("rule", "pick").e("pick", "q1").e("q1", "tool", "ค้น / อ่าน")
          .e("tool", "pick", "ผลห่อเป็นข้อมูล", "back", "L")
          .e("q1", "q2", "ส่งคำตอบ").e("q2", "ok", "ผ่าน").e("q2", "q3", "ไม่ผ่าน")
          .e("q3", "flag", "ครบ").e("q3", "pick", "ยัง: ส่งเหตุผลกลับ", "back", "R")
          .e("tool", "cap", f"ครบ {S - 1} call"))
    n2 = [f"ตัวตรวจซ้ำ (โค้ด): quote ต้องตรงกับ PDF ≥ {T}/100 · ตอบว่าไม่มีข้อนี้ได้เมื่ออ่าน 3 ส่วนที่เกี่ยวข้องที่สุดครบแล้ว",
          "ตัวจับการค้นไม่คืบหน้า (โค้ด): ค้นซ้ำไม่รันซ้ำ · ค้นแล้วไม่เจอส่วนใหม่จะเตือน · 2 ครั้งติดบอกส่วนที่ต้องอ่าน",
          f"หยุดได้ 3 ทาง: ผ่าน · ตีกลับครบ {R} ครั้ง · ครบงบ {S} call (call สุดท้ายเรียกได้เฉพาะ submit_finding แล้วตรวจซ้ำเหมือนเดิม)",
          f"call ละไม่เกิน {config.CALL_TIMEOUT_MS // 1000} วินาที · ทุกกฎเดินผังนี้แยกกันและพร้อมกัน (V4) · {meas}"]

    f3 = (Flow()
          .n("all", 1, 0, "start", "📑 ผลของทุกกฎ")
          .n("q1", 1, 1, "q", "เสี่ยงสูง + ผิด/ไม่มีข้อ?")
          .n("red", 2, 1, "bad", "🔴 ไม่แนะนำให้ลงนาม")
          .n("q2", 1, 2, "q", "มีข้อไม่สอดคล้องไหม?")
          .n("amber", 2, 2, "warn", "🟠 ลงนามได้หลังแก้ไข")
          .n("green", 1, 3, "ok", "🟢 ลงนามได้")
          .n("legal", 1, 4, "hum", "👩‍⚖️ ฝ่ายกฎหมายพิจารณา", "ข้อเสี่ยงสูง + ข้อเสนอแก้ไข")
          .n("q3", 1, 5, "q", "อนุมัติข้อเสนอแก้ไข?")
          .n("again", 0, 5, "llm", "AI ตรวจใหม่", "พร้อมความเห็นของฝ่ายกฎหมาย")
          .n("final", 1, 6, "code", "ตรวจรอบสุดท้ายด้วย Agent", "ข้อเสี่ยงที่ยังค้างต้องมีเหตุผล")
          .n("rec", 1, 7, "hum", "✍️ บันทึกการตัดสินใจ", "ลงนาม · ส่งแก้ · ปฏิเสธ")
          .e("all", "q1").e("q1", "red", "ใช่").e("q1", "q2", "ไม่").e("q2", "amber", "ใช่").e("q2", "green", "ไม่")
          .e("green", "legal").e("red", "legal", "", "back", "R").e("amber", "legal", "", "back", "R")
          .e("legal", "q3").e("q3", "again", "ส่งกลับ").e("again", "legal", "", "back", "L")
          .e("q3", "final", "อนุมัติ").e("final", "rec"))
    n3 = ["สองคำถามแรกเป็นโค้ด (verdict_level) ไม่ใช่ AI · AI ไม่ได้ตัดสินว่าลงนามได้หรือไม่",
          "ส่งกลับได้หลายรอบ ทุกรอบบันทึกความเห็นและผลใหม่ไว้ · คนเป็นผู้ตัดสินสุดท้ายเสมอ"]

    f4 = (Flow()
          .n("fail", 1, 0, "bad", "⚡ AI call ล้ม", "")
          .n("retry", 1, 1, "code", "🔁 Retry สูงสุด 4 ครั้ง", "รอ 5 → 10 → 20 → 40 วิ")
          .n("q1", 1, 2, "q", "ยังล้มอยู่ไหม?")
          .n("go", 2, 2, "ok", "✅ ทำงานต่อ")
          .n("fallback", 1, 3, "plan", "🔀 Model สำรอง", "แผน V6")
          .n("save", 1, 4, "plan", "💾 เก็บผลกฎที่เสร็จ · ทำต่อได้", "แผน V6")
          .n("stop", 0, 3, "warn", "⛔ หยุด แจ้ง error", "ตอนนี้: เริ่มใหม่ทั้งฉบับ")
          .e("fail", "retry").e("retry", "q1").e("q1", "go", "หาย").e("q1", "fallback", "ยังล้ม")
          .e("q1", "stop", "ตอนนี้").e("fallback", "save"))
    n4 = ["เส้นทึบ = มีแล้ว (retry 4 ครั้ง + timeout ต่อ call) · กรอบจุด = แผน V6 (model สำรอง + บันทึกผลทีละกฎ)",
          "ตัวรันเวอร์ชันหยุดรันที่ค้างเกิน 30 นาที ลบผลครึ่งทางแล้วรันใหม่ 1 ครั้ง (เพิ่ม 21 พ.ย. หลังพบ call ค้าง 2.5 ชั่วโมง)"]

    return CSS + "".join([
        figure("fig-routeflow", "ผัง 1 · Routing flow: สัญญาไปทางไหน และใช้กี่ call", "ระบบเลือกนโยบายและวิธีตรวจอย่างไร",
               f1, "routing flow ของระบบตรวจสัญญา", n1),
        figure("fig-decisionflow", "ผัง 2 · Decision flow ใน 1 กฎ: agent เดินได้กี่ขั้น อะไรหยุดมัน", "ทุกกฎเดินผังนี้พร้อมกัน",
               f2, "decision flow ภายในหนึ่งกฎ", n2),
        figure("fig-finalflow", "ผัง 3 · Final decision: โค้ดตัดสินก่อน คนตัดสินสุดท้าย", "AI ไม่ได้ตัดสินการลงนาม",
               f3, "ผังการตัดสินใจลงนาม", n3),
        figure("fig-failflow", "ผัง 4 · Plan for failure: เมื่อ AI call ล้ม", "แบบเดียวกับรูป 6.1 ของรายวิชา",
               f4, "ผังจัดการความล้มเหลว", n4)])


def course_flows() -> str:
    """Generic figures for the course notes: choosing a pattern (fig 6.2 redrawn) + the EP06 support agent."""
    p = (Flow()
         .n("try", 1, 0, "start", "ลอง pattern แถวบนสุด")
         .n("q", 1, 1, "q", "ถูกไหม · กี่ call · ราคา?")
         .n("stop", 0, 2, "ok", "✅ หยุดที่แถวนี้")
         .n("down", 2, 2, "warn", "⬇️ ลงแถวถัดไป")
         .e("try", "q").e("q", "stop", "ผ่าน").e("q", "down", "พังให้เห็นจริง").e("down", "try", "ลองแถวถัดไป", "back", "R"))
    s = (Flow()
         .n("ask", 1, 0, "start", "💬 คำถามลูกค้า")
         .n("route", 1, 1, "llm", "Router แยกประเภท", "", "1 call")
         .n("money", 0, 2, "hum", "เงิน · คืนเงิน · ข้อยกเว้น", "ส่งเจ้าหน้าที่", "0 call")
         .n("pol", 1, 2, "llm", "ค้นคลังนโยบาย + ร่างคำตอบ", "", "1 call")
         .n("unsure", 2, 2, "hum", "ไม่แน่ใจ / บั๊ก", "ส่งคน / ทีมเทคนิค", "0 call")
         .n("q", 1, 3, "q", "อ้างอิงมีในเอกสารจริง?")
         .n("send", 1, 4, "ok", "✅ ตอบพร้อมลิงก์นโยบาย")
         .n("none", 2, 4, "bad", "❌ ไม่พบ → ส่งคน")
         .e("ask", "route").e("route", "money", "เงิน").e("route", "pol", "นโยบาย").e("route", "unsure", "อื่น ๆ")
         .e("pol", "q").e("q", "send", "ผ่าน").e("q", "none", "ไม่ผ่าน"))
    return CSS + figure("fig-choosepattern", "เลือก pattern จากตาราง 19.3", "รูป 6.2 ของรายวิชา วาดใหม่", p,
                        "ผังเลือก pattern", ["เริ่มแถวบน วัดความถูกต้อง จำนวน call และต้นทุน · ลงแถวถัดไปเฉพาะเมื่อพังให้เห็นจริง"]) \
        + figure("fig-supportflow", "ตัวอย่าง EP06 · support agent สายการบิน", "routing + decision flow · 2 call ต่อคำถามนโยบาย", s,
                 "ผัง support agent", ["คำถามเรื่องเงินและเรื่องที่ไม่แน่ใจไม่ผ่าน AI เลย · คำตอบนโยบายต้องผ่านการตรวจข้อความอ้างอิงด้วยโค้ด"])


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(project_flows(), encoding="utf-8")
    print("written", sys.argv[1])
