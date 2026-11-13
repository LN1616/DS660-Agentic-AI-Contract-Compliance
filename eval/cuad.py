"""Helpers to use CUAD as ground truth."""
import ast
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src import config


@lru_cache(maxsize=1)
def master() -> pd.DataFrame:
    return pd.read_csv(config.CUAD_DIR / "master_clauses.csv")


@lru_cache(maxsize=1)
def _pdf_index() -> dict:
    """Full CUAD folder if present, plus the 6 bundled samples in data/samples (used on Streamlit Cloud)."""
    dirs = [config.ROOT / "data" / "samples", config.CUAD_DIR / "full_contract_pdf"]
    return {p.stem.lower(): p for d in dirs if d.exists() for p in d.rglob("*") if p.suffix.lower() == ".pdf"}


def available(filenames: list[str]) -> list[str]:
    return [f for f in filenames if f.rsplit(".", 1)[0].lower() in _pdf_index()]


def pdf_path(filename: str) -> Path:
    stem = filename.rsplit(".", 1)[0].lower()
    return _pdf_index()[stem]


def gold_spans(filename: str, category: str) -> list[str]:
    row = master()[master()["Filename"] == filename].iloc[0]
    raw = row[category]
    try:
        spans = ast.literal_eval(raw) if isinstance(raw, str) else []
    except (ValueError, SyntaxError):
        spans = [raw]
    return [s for s in spans if isinstance(s, str) and s.strip()]


def expected_status(filename: str, rule: dict) -> str:
    """What CUAD lets us check: clause present or absent.
    Absent -> the rule's if_absent status. Present -> 'PRESENT' (any non-absent status)."""
    return "PRESENT" if gold_spans(filename, rule["cuad_category"]) else rule["if_absent"]
