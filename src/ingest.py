"""Step 3 - Ingestion: read each PDF page with the cheapest method that works.

text page  -> pdfplumber text
table page -> pdfplumber text + tables rendered as Markdown
scan page  -> page image sent to a vision model (only when use_vision=True)
"""
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from . import config

MIN_TEXT_CHARS = 50


@dataclass
class Page:
    number: int
    kind: str   # "text" | "table" | "scan"
    text: str


def inspect_layout(page) -> str:
    text = page.extract_text() or ""
    if len(text.strip()) < MIN_TEXT_CHARS:
        return "scan"
    # A real table has at least 2 rows and 2 columns; ruled boxes alone don't count.
    for t in page.find_tables():
        rows = t.extract()
        if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
            return "table"
    return "text"


def table_to_markdown(rows: list[list]) -> str:
    rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in rows if any(r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def vision_extract(pdf_path: Path, page_no: int, trace=None) -> str:
    import fitz  # PyMuPDF
    from google.genai import types

    pix = fitz.open(pdf_path)[page_no - 1].get_pixmap(dpi=200)
    prompt = ("Transcribe this contract page exactly. Keep section numbers. "
              "Render tables as Markdown tables; repeat merged-cell values in each row.")

    def call():
        return config.client().models.generate_content(
            model=config.VISION_MODEL,
            contents=[types.Part.from_bytes(data=pix.tobytes("png"), mime_type="image/png"), prompt],
            config=types.GenerateContentConfig(temperature=0),
        )

    resp = trace.call(call, label=f"vision p.{page_no}") if trace else call()
    return resp.text or ""


def extract_pages(pdf_path, use_vision: bool = True, trace=None) -> list[Page]:
    pdf_path = Path(pdf_path)
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            kind = inspect_layout(p)
            if kind == "scan":
                text = vision_extract(pdf_path, i, trace) if use_vision else ""
            else:
                text = p.extract_text() or ""
                if kind == "table":
                    md = [table_to_markdown(t.extract()) for t in p.find_tables()]
                    text += "\n\n" + "\n\n".join(m for m in md if m)
            pages.append(Page(i, kind, text))
    if trace:
        kinds = {k: sum(p.kind == k for p in pages) for k in ("text", "table", "scan")}
        trace.event("ingest", file=pdf_path.name, pages=len(pages), **kinds)
    return pages
