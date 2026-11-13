"""Settings and the shared Gemini client."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL = os.getenv("MODEL", "gemini-2.5-flash")
VISION_MODEL = os.getenv("VISION_MODEL", MODEL)
PRICE_IN_PER_M = float(os.getenv("PRICE_IN_PER_M", "0.30"))
PRICE_OUT_PER_M = float(os.getenv("PRICE_OUT_PER_M", "2.50"))

MAX_STEPS = int(os.getenv("MAX_STEPS", "6"))      # LLM calls allowed per policy rule
MAX_REJECTIONS = int(os.getenv("MAX_REJECTIONS", "2"))  # verifier send-backs per rule

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
        _client = genai.Client()
    return _client


def load_playbook(path: Path = PLAYBOOK_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["rules"]
