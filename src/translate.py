"""Display translation of a saved run's AI-written text (summary, issue, action).

The original text stays the record: legal decisions, send-backs and the Excel export use it.
Translations are cached with the run, keyed by a hash of the source text, so each item is
translated once and a re-checked finding is translated again automatically.
"""
import hashlib

from google.genai import types
from pydantic import BaseModel

from . import config
from .trace import Trace

LANGUAGES = {"th": "Thai", "en": "English"}


class Item(BaseModel):
    key: str
    text: str


class Items(BaseModel):
    items: list[Item]


def digest(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


def translate(texts: dict[str, str], target: str, trace: Trace) -> dict[str, str]:
    """texts: {key: source text}. Returns {key: translation} in one structured call."""
    if not texts:
        return {}
    payload = "\n".join(f"<item key=\"{k}\">\n{v}\n</item>" for k, v in texts.items())
    prompt = (f"Translate each item into {LANGUAGES[target]} for a contract review report. "
              f"Use formal written {LANGUAGES[target]}. Keep the meaning exact. Keep numbers, amounts, "
              "section numbers, party names, status words (COMPLIANT, DEVIATED, VIOLATED, MISSING) and "
              "redaction marks like [***] unchanged. Keep markdown lists and bold. "
              "Return every key exactly once.\n\n" + payload)
    resp = trace.call(lambda: config.client().models.generate_content(
        model=config.MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                           response_schema=Items)), label=f"translate to {target}")
    parsed = resp.parsed if isinstance(resp.parsed, Items) else Items.model_validate_json(resp.text)
    return {i.key: i.text for i in parsed.items if i.key in texts}
