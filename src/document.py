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


@dataclass
class Passage:
    id: str
    section: str
    page: int
    text: str


def normalize(s: str) -> str:
    s = s.replace("-\n", "").replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


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
        self._norm_pages = {p.number: normalize(p.text) for p in pages}
        self.seen: set[str] = set()   # passages the agent has looked at

    # ---------- tools the agent can call ----------
    def search(self, query: str, k: int = 5) -> list[dict]:
        scores = linear_kernel(self._vec.transform([query]), self._matrix).ravel()
        top = scores.argsort()[::-1][:k]
        out = []
        for i in top:
            if scores[i] <= 0:
                break
            p = self.passages[i]
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
        nxt = self.passages[idx + 1] if idx + 1 < len(self.passages) else None
        return {"passage_id": p.id, "section": p.section or "-", "page": p.page, "text": p.text,
                "next_passage_id": nxt.id if nxt else None}

    # ---------- checks used by the verifier (plain code, no LLM) ----------
    def find_quote(self, quote: str) -> tuple[int | None, float]:
        q = normalize(quote)
        if len(q) < 15:
            return None, 0.0
        best_page, best = None, 0.0
        for num, text in self._norm_pages.items():
            s = fuzz.partial_ratio(q, text)
            if s > best:
                best_page, best = num, s
        return best_page, best

    def keyword_passages(self, keywords: list[str]) -> list[str]:
        kws = [k.lower() for k in keywords]
        return [p.id for p in self.passages if any(k in p.text.lower() for k in kws)]
