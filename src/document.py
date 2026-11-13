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
        self.reset()

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

    def search(self, query: str, k: int = 5) -> list[dict]:
        out = []
        for pid in self.ranked_ids(query, k):
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

    # ---------- checks used by the verifier (plain code, no LLM) ----------
    def find_quote(self, quote: str) -> tuple[int | None, float]:
        q = normalize(quote)
        if len(q) < 15:
            return None, 0.0
        best_page, best = None, 0.0
        nums = sorted(self._norm_pages)
        for i, num in enumerate(nums):
            # the page alone, and the page joined with the next one (quotes can cross a page break)
            windows = [self._norm_pages[num]]
            if i + 1 < len(nums):
                windows.append(self._norm_pages[num] + " " + self._norm_pages[nums[i + 1]])
            s = max(fuzz.partial_ratio(q, w) for w in windows)
            if s > best:
                best_page, best = num, s
        return best_page, best

    def keyword_passages(self, keywords: list[str]) -> list[str]:
        kws = [k.lower() for k in keywords]
        return [p.id for p in self.passages if any(k in p.text.lower() for k in kws)]
