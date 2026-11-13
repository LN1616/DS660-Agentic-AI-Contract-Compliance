"""Visual building blocks for the Streamlit app: theme CSS, cards, charts (plain HTML), PDF highlighter.

Colour roles follow one rule each:
  status (COMPLIANT / DEVIATED / VIOLATED / MISSING) -> fixed status palette, always with icon + label
  magnitude (AI calls per rule)                      -> one hue (blue)
Text always uses ink colours, never the series colour.
"""
import html
import re

import pymupdf

STATUS = {  # colour, icon, soft background
    "COMPLIANT": ("#0ca30c", "✓", "#e6f6e6"),
    "DEVIATED": ("#fab219", "~", "#fff4da"),
    "VIOLATED": ("#d03b3b", "✕", "#fbe6e6"),
    "MISSING": ("#ec835a", "∅", "#fdeee8"),
}
RISK = {"HIGH": "#d03b3b", "MEDIUM": "#fab219", "LOW": "#8a8f9c"}
BLUE = "#2a78d6"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
html, body, [class*="st-"], .stMarkdown, .stButton button, input, textarea, select {
  font-family: "IBM Plex Sans Thai", "Leelawadee UI", system-ui, sans-serif; }
.block-container { padding-top: 3.4rem; max-width: 1440px; }
h1, h2, h3 { letter-spacing: -0.01em; }
[data-testid="stSidebar"] { border-right: 1px solid #e4e7ef; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #e4e7ef; border-radius: 12px; padding: 12px 16px; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #e4e7ef; }
.stTabs [data-baseweb="tab"] { padding: 8px 14px; font-weight: 500; }
.cc-card { background: #fff; border: 1px solid #e4e7ef; border-radius: 12px; padding: 16px 18px; }
.cc-label { font-size: 12px; letter-spacing: .05em; text-transform: uppercase; color: #6b7184; font-weight: 600; }
.cc-muted { color: #6b7184; font-size: 13px; }
.cc-chip { display: inline-flex; align-items: center; gap: 5px; font: 600 11.5px "IBM Plex Mono", monospace;
  padding: 2px 9px; border-radius: 999px; color: #1b2133; white-space: nowrap; }
.cc-chip i { font-style: normal; width: 15px; height: 15px; border-radius: 50%; color: #fff; display: inline-grid;
  place-items: center; font-size: 10px; }
.cc-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; background: #fff; border: 1px solid #e4e7ef;
  border-radius: 14px; padding: 14px 18px; margin-bottom: 8px; }
.cc-logo { width: 38px; height: 38px; border-radius: 10px; background: #1e2a5a; color: #f0a93b; display: grid;
  place-items: center; font-weight: 700; font-size: 20px; }
.cc-title { font-weight: 600; font-size: 17px; color: #1b2133; }
.cc-steps { display: flex; gap: 0; margin-left: auto; flex-wrap: wrap; }
.cc-step { display: flex; align-items: center; gap: 7px; font-size: 13px; color: #6b7184; padding: 4px 10px; }
.cc-step b { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-size: 11px;
  border: 2px solid #cfd4e0; color: #6b7184; background: #fff; }
.cc-step.done b { background: #0ca30c; border-color: #0ca30c; color: #fff; }
.cc-step.now { color: #1b2133; font-weight: 600; }
.cc-step.now b { border-color: #2a78d6; color: #2a78d6; }
.cc-step + .cc-step::before { content: ""; width: 18px; height: 2px; background: #cfd4e0; margin-right: 4px; }
.cc-seg { display: flex; gap: 2px; height: 34px; border-radius: 6px; overflow: hidden; margin: 10px 0 8px; }
.cc-seg div { display: grid; place-items: center; color: #fff; font: 600 12px "IBM Plex Mono", monospace; min-width: 0; }
.cc-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12.5px; color: #3c4256; }
.cc-legend span { display: inline-flex; align-items: center; gap: 6px; }
.cc-legend s { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.cc-map { display: grid; grid-template-columns: repeat(auto-fill, minmax(34px, 1fr)); gap: 4px; margin-top: 10px; }
.cc-pg { height: 46px; border-radius: 5px; background: #f1f3f8; border: 1px solid #e4e7ef; position: relative;
  font: 500 10.5px "IBM Plex Mono", monospace; color: #8a8f9c; display: flex; align-items: flex-end; justify-content: center;
  padding-bottom: 3px; }
.cc-pg .dots { position: absolute; top: 5px; left: 0; right: 0; display: flex; gap: 2px; justify-content: center; flex-wrap: wrap; }
.cc-pg .dots i { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid #fff; }
.cc-bars { display: grid; grid-template-columns: minmax(150px, 46%) 1fr 64px; gap: 8px 10px; align-items: center; margin-top: 10px;
  font-size: 13px; color: #1b2133; }
.cc-bar { height: 12px; background: #f1f3f8; border-radius: 0 4px 4px 0; position: relative; }
.cc-bar div { height: 100%; background: #2a78d6; border-radius: 0 4px 4px 0; }
.cc-bars .v { font: 500 12px "IBM Plex Mono", monospace; color: #3c4256; text-align: right; }
.cc-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.cc-table th { text-align: left; font-size: 12px; color: #6b7184; font-weight: 600; padding: 8px; border-bottom: 1px solid #e4e7ef; }
.cc-table td { padding: 9px 8px; border-bottom: 1px solid #eef0f5; vertical-align: middle; }
.cc-thin { display: flex; gap: 2px; height: 8px; border-radius: 4px; overflow: hidden; min-width: 120px; }
.cc-quote { font-family: Georgia, "Times New Roman", serif; background: #f6f7fb; border-left: 0; border-radius: 8px;
  padding: 10px 12px; font-size: 14px; color: #1b2133; }
</style>
"""


def esc(s) -> str:
    return html.escape(str(s))


def chip(status: str) -> str:
    color, icon, soft = STATUS[status]
    return f'<span class="cc-chip" style="background:{soft}"><i style="background:{color}">{icon}</i>{status}</span>'


def risk_chip(risk: str) -> str:
    return (f'<span class="cc-chip" style="background:#f1f3f8"><i style="background:{RISK[risk]}">!</i>{risk}</span>')


def header(title: str, subtitle: str, steps: list[tuple[str, str]]) -> str:
    """steps: [(label, 'done'|'now'|'')]"""
    st_html = "".join(f'<div class="cc-step {s}"><b>{"✓" if s == "done" else i + 1}</b>{esc(lbl)}</div>'
                      for i, (lbl, s) in enumerate(steps))
    return (f'<div class="cc-head"><div class="cc-logo">§</div><div><div class="cc-title">{esc(title)}</div>'
            f'<div class="cc-muted">{esc(subtitle)}</div></div><div class="cc-steps">{st_html}</div></div>')


def status_split(counts: dict, labels: dict, title: str) -> str:
    """Tall segmented bar: one whole (all findings) split by status, <= 4 parts."""
    total = sum(counts.values()) or 1
    segs = "".join(
        f'<div title="{labels[s]}: {n}" style="flex:{n};background:{STATUS[s][0]}">{n if n / total > 0.08 else ""}</div>'
        for s, n in counts.items() if n)
    legend = "".join(f'<span><s style="background:{STATUS[s][0]}"></s>{STATUS[s][1]} {esc(labels[s])}</span>'
                     for s in counts)
    return (f'<div class="cc-card"><div class="cc-label">{esc(title)}</div>'
            f'<div class="cc-seg">{segs}</div><div class="cc-legend">{legend}</div></div>')


def page_map(n_pages: int, marks: list[tuple[int, str, str]], title: str, note: str) -> str:
    """Contract map: one tile per page; a dot per finding located on that page (colour = status)."""
    by_page: dict[int, list] = {}
    for page, status, label in marks:
        by_page.setdefault(page, []).append((status, label))
    tiles = []
    for p in range(1, n_pages + 1):
        dots = "".join(f'<i title="{esc(lbl)}" style="background:{STATUS[s][0]}"></i>' for s, lbl in by_page.get(p, []))
        tip = "; ".join(lbl for _, lbl in by_page.get(p, [])) or f"p.{p}"
        tiles.append(f'<div class="cc-pg" title="{esc(tip)}"><div class="dots">{dots}</div>{p}</div>')
    return (f'<div class="cc-card"><div class="cc-label">{esc(title)}</div><div class="cc-muted">{esc(note)}</div>'
            f'<div class="cc-map">{"".join(tiles)}</div></div>')


def effort_bars(rows: list[tuple[str, int, int]], title: str, note: str, unit_back: str) -> str:
    """Ranked horizontal bars, one hue: AI calls per rule; send-backs printed as text."""
    rows = sorted(rows, key=lambda r: -r[1])
    top = max([r[1] for r in rows] + [1])
    body = "".join(
        f'<div>{esc(name)}</div><div class="cc-bar" title="{esc(name)}: {calls} AI calls, {back} {unit_back}">'
        f'<div style="width:{100 * calls / top:.0f}%"></div></div>'
        f'<div class="v">{calls}{f" · ↺{back}" if back else ""}</div>' for name, calls, back in rows)
    return (f'<div class="cc-card"><div class="cc-label">{esc(title)}</div><div class="cc-muted">{esc(note)}</div>'
            f'<div class="cc-bars">{body}</div></div>')


def thin_split(counts: dict) -> str:
    return '<div class="cc-thin">' + "".join(
        f'<div title="{s}: {n}" style="flex:{n};background:{STATUS[s][0]}"></div>' for s, n in counts.items() if n) + "</div>"


# ---------------- PDF page with highlighted quotes ----------------
def _hex_rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def quote_rects(page, quote: str) -> list:
    """Find a (possibly long, multi-line) quote on the page by searching it in short word windows."""
    words = re.sub(r"\s+", " ", quote).strip().split(" ")
    rects, size = [], 6
    for i in range(0, len(words), size):
        chunk = " ".join(words[i:i + size])
        if len(chunk) < 12 and i:
            continue
        rects += page.search_for(chunk)
    return rects


def render_page(pdf_path: str, page_no: int, highlights: tuple, zoom: float = 1.6) -> bytes:
    """highlights: ((quote, status, label), ...) -> PNG of the page with coloured highlight boxes."""
    doc = pymupdf.open(pdf_path)
    page = doc[page_no - 1]
    for quote, status, _ in highlights:
        if not quote:
            continue
        for r in quote_rects(page, quote):
            page.draw_rect(r, color=None, fill=_hex_rgb(STATUS[status][0]), fill_opacity=0.28, overlay=True)
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
