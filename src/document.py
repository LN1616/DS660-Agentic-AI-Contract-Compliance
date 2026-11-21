"""Step 4 - The contract as something the agent can search, plus the verifier's checks.

The agent never sees the whole contract. It searches, reads passages, and the
harness keeps track of what it has read (working memory outside the context).
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from .ingest import Page

# Headings at the start of a line: "Section 5", "ARTICLE VII", "12.1 Limitation",
# "2.2.Availability" (no space), "7. TERM", "7 TERM"
HEADING = re.compile(
    r"^\s*(?:"
    r"(?P<a>(?i:section|article)\s+[\dIVXLC]+(?:\.\d+)*)\.?\s"
    r"|(?P<b>\d{1,2}(?:\.\d{1,2}){1,3})\.?\s*(?=[A-Z(\"“])"
    r"|(?P<c>\d{1,2})\.\s*(?=[A-Z(\"“])"
    r"|(?P<d>\d{1,2})\s+(?=[A-Z]{2,})"
    r")"
)
MAX_PASSAGE = 1200

# V6 indexes for long contracts (built once per document, plain code)
ATTACH_HEAD = re.compile(r"^\s*(EXHIBIT|SCHEDULE|APPENDIX|ANNEX|ATTACHMENT)\s+([A-Z0-9][\w.-]*)", re.MULTILINE)
REF = re.compile(r"(?i)\b(section|article|clause|exhibit|schedule|appendix|annex|attachment)\s+([A-Z0-9][\w.-]*)")
DEFINES = [re.compile(r'["“]([A-Z][\w\s/&-]{1,50}?)["”]\s*(?:shall\s+)?(?:means?|has the meaning|refers to)'),
           re.compile(r'\((?:the\s+|each,?\s+an?\s+|an?\s+|hereinafter\s+)?["“]([A-Z][\w\s/&-]{1,50}?)["”]\)')]


def _num(label: str) -> str:
    """'Section 9.3.' / 'ARTICLE 9' / '9.3' -> '9.3' (lower case, no trailing dot)."""
    m = re.search(r"([\dIVXLC]+(?:\.\d+)*)\.?\s*$", label.strip(), flags=re.IGNORECASE)
    return (m.group(1) if m else label.strip()).lower().rstrip(".")


@dataclass
class Passage:
    id: str
    section: str
    page: int
    text: str


def normalize(s: str) -> str:
    s = s.replace("-\n", "").replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


PAGE_FOOTER = re.compile(r"(?i)^\s*(page\s+\d+\s+of\s+\d+.*|-?\s*\d{1,3}\s*-?|source:.*)$")


def strip_boilerplate(text: str, boilerplate: set[str]) -> str:
    return "\n".join(l for l in text.splitlines() if l.strip() not in boilerplate and not PAGE_FOOTER.match(l))


def split_passages(pages: list[Page]) -> list[Passage]:
    passages, buf, section, start_page = [], [], "", 1

    def flush():
        text = "\n".join(buf).strip()
        while text:
            chunk, text = text[:MAX_PASSAGE], text[MAX_PASSAGE:]
            passages.append(Passage(f"P{len(passages) + 1}", section, start_page, chunk))

    for page in pages:
        for line in page.text.splitlines():
            m = HEADING.match(line)
            if m and buf:
                flush()
                buf = []
            if m or not buf:
                section = next(g for g in m.groups() if g).strip() if m else section
                start_page = page.number
            buf.append(line)
    if buf:
        flush()
    return passages


class ContractDocument:
    def __init__(self, title: str, pages: list[Page]):
        self.title = title
        self.pages = pages
        self.passages = split_passages(pages)
        self._by_id = {p.id: p for p in self.passages}
        self._vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self._matrix = self._vec.fit_transform([p.text for p in self.passages])
        self._norm_pages = {p.number: normalize(strip_boilerplate(p.text, self._boilerplate(pages)))
                            for p in pages}
        self._build_indexes()
        self.reset()

    def _build_indexes(self):
        """Section numbers, attachment headings and defined terms -> passage ids (for follow_reference and
        lookup_definition). An attachment heading listed in a table of contents near the start is skipped
        when the same heading appears again later (the attachment itself)."""
        self._sections: dict[str, list[str]] = {}
        for p in self.passages:
            if p.section:
                self._sections.setdefault(_num(p.section), []).append(p.id)
        self._attach: dict[str, str] = {}
        for i, p in enumerate(self.passages):
            for m in ATTACH_HEAD.finditer(p.text):
                key = f"{m.group(1).lower()} {m.group(2).lower().rstrip('.')}"
                if key not in self._attach or i > len(self.passages) * 0.3:
                    self._attach[key] = p.id
        self._defs: dict[str, str] = {}
        for p in self.passages:
            for rx in DEFINES:
                for m in rx.finditer(p.text):
                    term = " ".join(m.group(1).split()).lower()
                    self._defs.setdefault(term, p.id)  # first definition wins

    @staticmethod
    def _boilerplate(pages: list[Page]) -> set[str]:
        """Lines repeated on at least half the pages (headers/footers)."""
        from collections import Counter
        counts = Counter(l.strip() for p in pages for l in set(p.text.splitlines()) if l.strip())
        return {l for l, c in counts.items() if len(pages) >= 3 and c >= len(pages) / 2}

    def reset(self):
        self.seen: set[str] = set()       # passages shown in search results (preview only)
        self.read_ids: set[str] = set()   # passages the agent read in full

    # ---------- tools the agent can call ----------
    def ranked_ids(self, query: str, k: int = 5) -> list[str]:
        """Passage ids by relevance. A query like 'Section 7.1' also matches that section number."""
        ids = []
        m = re.search(r"\b(\d{1,2}(?:\.\d{1,2}){0,3})\b", query)
        if m and re.search(r"(?i)section|clause|article|^\s*\d", query):
            ids = [p.id for p in self.passages if p.section.split()[-1:] == [m.group(1)]
                   or p.section == m.group(1)][:k]
        scores = linear_kernel(self._vec.transform([query]), self._matrix).ravel()
        for i in scores.argsort()[::-1]:
            if len(ids) >= k or scores[i] <= 0:
                break
            if self.passages[i].id not in ids:
                ids.append(self.passages[i].id)
        return ids

    def search(self, query: str, k: int = 5, page: int = 1) -> list[dict]:
        """page 2 = results ranked 6-10 (V6: on long contracts the answer was often just past the top 5)."""
        out = []
        page = max(1, min(int(page or 1), 4))
        for pid in self.ranked_ids(query, k * page)[k * (page - 1):]:
            p = self._by_id[pid]
            self.seen.add(p.id)
            out.append({"passage_id": p.id, "section": p.section or "-", "page": p.page,
                        "text": p.text[:700] + (" ..." if len(p.text) > 700 else "")})
        return out

    def read(self, passage_id: str) -> dict:
        p = self._by_id.get(passage_id)
        if not p:
            return {"error": f"No passage {passage_id}"}
        idx = self.passages.index(p)
        self.seen.add(p.id)
        self.read_ids.add(p.id)
        nxt = self.passages[idx + 1] if idx + 1 < len(self.passages) else None
        return {"passage_id": p.id, "section": p.section or "-", "page": p.page, "text": p.text,
                "next_passage_id": nxt.id if nxt else None}

    def follow_reference(self, reference: str) -> dict:
        """'Article 9.3' / 'Section 12.1.4' / 'Exhibit H-8' -> that part of the contract, read in full."""
        m = REF.search(reference or "")
        if not m:
            return {"error": f"'{reference}' is not a section, article, exhibit or schedule reference"}
        kind, label = m.group(1).lower(), m.group(2).rstrip(".")
        if kind in ("section", "article", "clause"):
            num = _num(label)
            ids = self._sections.get(num) or next(
                (v for k, v in self._sections.items() if k.startswith(num + ".")), None)
            if not ids:
                return {"error": f"No {kind} {label} found in the contract"}
            out = self.read(ids[0])
            if len(ids) > 1:
                out["same_section_passages"] = ids[1:6]
            return out
        pid = self._attach.get(f"{kind} {label.lower()}")
        if not pid and "-" in label:  # "Exhibit H-8" = page 8 of Exhibit H
            pid = self._attach.get(f"{kind} {label.lower().split('-')[0]}")
        if not pid:
            return {"error": f"No {kind} {label} heading found in the contract"}
        return self.read(pid)

    def lookup_definition(self, term: str) -> dict:
        """Where a defined term ('"Net Sales" means ...') is defined, read in full. Exact term first, then closest."""
        t = " ".join((term or "").strip(' "“”').split()).lower()
        pid = self._defs.get(t)
        if not pid and self._defs:
            best = max(self._defs, key=lambda d: fuzz.ratio(t, d))
            pid = self._defs[best] if fuzz.ratio(t, best) >= 85 else None
        if not pid:
            return {"error": f"No definition of '{term}' found in the contract"}
        return self.read(pid)

    # ---------- checks used by the verifier (plain code, no LLM) ----------
    def find_quote(self, quote: str) -> tuple[int | None, float]:
        q = normalize(quote)
        if len(q) < 15:
            return None, 0.0
        nums = sorted(self._norm_pages)
        # 1) the quote on a single page (most quotes)
        single = {n: fuzz.partial_ratio(q, self._norm_pages[n]) for n in nums}
        best_page = max(single, key=single.get)
        if single[best_page] >= 88:
            return best_page, single[best_page]
        # 2) a quote that crosses a page break: page joined with the next one
        for a, b in zip(nums, nums[1:]):
            s = fuzz.partial_ratio(q, self._norm_pages[a] + " " + self._norm_pages[b])
            if s > single[best_page]:
                single[best_page] = s if best_page == a else single[best_page]
                best_page, single[a] = a, s
        return best_page, single[best_page]

    def keyword_passages(self, keywords: list[str]) -> list[str]:
        kws = [k.lower() for k in keywords]
        return [p.id for p in self.passages if any(k in p.text.lower() for k in kws)]
