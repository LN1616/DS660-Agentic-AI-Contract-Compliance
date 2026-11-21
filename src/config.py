"""Settings and the shared Gemini client."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL = os.getenv("MODEL", "gemini-3.8-flash")
VISION_MODEL = os.getenv("VISION_MODEL", MODEL)
PRICE_IN_PER_M = float(os.getenv("PRICE_IN_PER_M", "0.30"))
PRICE_OUT_PER_M = float(os.getenv("PRICE_OUT_PER_M", "2.50"))

MAX_STEPS = int(os.getenv("MAX_STEPS", "10"))      # LLM calls allowed per policy rule (contracts up to LONG_FROM_PAGES)
# Call budget scaled by contract length: +1 call per PAGES_PER_EXTRA_STEP pages beyond LONG_FROM_PAGES, at most MAX_STEPS_LONG
LONG_FROM_PAGES = int(os.getenv("LONG_FROM_PAGES", "30"))
PAGES_PER_EXTRA_STEP = int(os.getenv("PAGES_PER_EXTRA_STEP", "7"))
# Off by default (= MAX_STEPS): tested 21 Nov at 16, budget hits 10/16 -> 4/16 but presence 9 -> 8/16, cost +36%,
# and wrong answers passed the verifier instead of being flagged. Set e.g. 16 to switch it on.
MAX_STEPS_LONG = int(os.getenv("MAX_STEPS_LONG", "10"))
MAX_REJECTIONS = int(os.getenv("MAX_REJECTIONS", "2"))  # verifier send-backs per rule
PARALLEL_RULES = int(os.getenv("PARALLEL_RULES", "5"))  # rules checked at the same time (1 = one after another)
CALL_TIMEOUT_MS = int(os.getenv("CALL_TIMEOUT_MS", "120000"))  # one AI call; a dropped connection otherwise hangs
MIN_CALL_GAP = float(os.getenv("MIN_CALL_GAP", "4.5"))  # seconds between AI calls (free tier ~15 requests/min)
# V5 harness
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")  # used when MODEL still fails after RETRIES_BEFORE_FALLBACK; "" = off
RETRIES_BEFORE_FALLBACK = int(os.getenv("RETRIES_BEFORE_FALLBACK", "2"))
CONTEXT_BUDGET_CHARS = int(os.getenv("CONTEXT_BUDGET_CHARS", "16000"))  # ~4,000 tokens of conversation per rule
CHECKPOINT_DIR = Path(os.getenv("CHECKPOINT_DIR", ROOT / "outputs" / "checkpoints"))

# Release switches (22 Nov): the app runs the measured V5 harness. V6 long-contract tools (follow_reference,
# lookup_definition, search page 2), the V6 cross-check reviewer and the V7 MISSING wording are kept but OFF:
# 3 runs on every version showed the same accuracy at higher cost (V6 0.86, V7 0.88 vs V5 0.68 baht per contract).
V6_TOOLS = os.getenv("V6_TOOLS") == "1"
CROSS_CHECK = os.getenv("CROSS_CHECK") == "1"
V7_MISSING_PROMPT = os.getenv("V7_MISSING_PROMPT") == "1"


def release_name() -> str:
    """Shown in the app: V5 + H by default, plus any measured extra that is switched on."""
    extra = [name for on, name in ((V6_TOOLS, "V6 tools"), (CROSS_CHECK, "cross-check"), (V7_MISSING_PROMPT, "V7 prompt")) if on]
    return "V5 + H" + ("".join(f" + {e}" for e in extra))

# Package H (EP01 builder's dials). While measuring, a fallback model would mix two models into one run (EP01 "lock
# the provider"): eval.run_versions sets EVAL_NO_FALLBACK=1. The app keeps the fallback.
EVAL_NO_FALLBACK = os.getenv("EVAL_NO_FALLBACK") == "1"
# What each model family accepts and how big its input window is (EP01 "check modality before sending").
# First matching prefix wins. An unknown model is treated as text-only with a small window, so a model swap
# (package F) fails safe: the single call sends extracted text instead of the PDF, scanned pages are skipped with a note.
MODEL_CAPS = [
    ("gemini-", {"inputs": {"text", "pdf", "image"}, "context": 1_048_576}),
    ("gemma-", {"inputs": {"text", "image"}, "context": 128_000}),
]
UNKNOWN_MODEL_CAPS = {"inputs": {"text"}, "context": 32_000}
PREFLIGHT_MAX_SHARE = float(os.getenv("PREFLIGHT_MAX_SHARE", "0.9"))  # refuse a request above 90% of the window


def model_caps(model: str) -> dict:
    for prefix, caps in MODEL_CAPS:
        if model.lower().startswith(prefix):
            return caps
    return UNKNOWN_MODEL_CAPS


def accepts(model: str, kind: str) -> bool:
    """kind: 'text' | 'pdf' | 'image'."""
    return kind in model_caps(model)["inputs"]

CUAD_DIR = Path(os.getenv("CUAD_DIR", ROOT.parent / "CUAD_v1" / "CUAD_v1"))
PLAYBOOK_PATH = ROOT / "data" / "policy_playbook.yaml"
OUTPUT_DIR = ROOT / "outputs"
TRACE_DIR = ROOT / "traces"

_client = None


def client():
    """Create the Gemini client once. Fails with a clear message if no key is set."""
    global _client
    if _client is None:
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and paste a key "
                "from https://aistudio.google.com/apikey"
            )
        from google import genai
        from google.genai import types
        _client = genai.Client(http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS))
    return _client


def load_playbook(path: Path = PLAYBOOK_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["rules"]
