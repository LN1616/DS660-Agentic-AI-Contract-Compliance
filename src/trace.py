"""Harness logging: every LLM call's tokens, latency and estimated cost."""
import json
import time
from datetime import datetime
from pathlib import Path

from . import config


class Trace:
    def __init__(self, run_name: str):
        self.run_name = run_name
        self.records: list[dict] = []

    def call(self, fn, label: str, retries: int = 4):
        """Run one LLM call. Retries on overload (503) and rate limit (429) with backoff."""
        t0 = time.time()
        for attempt in range(retries + 1):
            try:
                resp = fn()
                break
            except Exception as e:
                code = getattr(e, "code", None)
                if code not in (429, 500, 503) or attempt == retries:
                    raise
                wait = min(60, 5 * 2 ** attempt)
                self.records.append({"type": "retry", "label": label, "code": code, "wait_sec": wait})
                print(f"    [{label}] Gemini busy ({code}), retrying in {wait}s ...", flush=True)
                time.sleep(wait)
        u = getattr(resp, "usage_metadata", None)
        tin = (getattr(u, "prompt_token_count", 0) or 0) if u else 0
        tout = ((getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
        self.records.append({"type": "llm", "label": label, "sec": round(time.time() - t0, 2),
                             "tokens_in": tin, "tokens_out": tout})
        return resp

    def event(self, kind: str, **data):
        self.records.append({"type": kind, **data})

    @property
    def totals(self) -> dict:
        llm = [r for r in self.records if r["type"] == "llm"]
        tin = sum(r["tokens_in"] for r in llm)
        tout = sum(r["tokens_out"] for r in llm)
        cost = tin / 1e6 * config.PRICE_IN_PER_M + tout / 1e6 * config.PRICE_OUT_PER_M
        return {"llm_calls": len(llm), "tokens_in": tin, "tokens_out": tout,
                "llm_seconds": round(sum(r["sec"] for r in llm), 1), "cost_usd": round(cost, 4)}

    def save(self) -> Path:
        config.TRACE_DIR.mkdir(exist_ok=True)
        path = config.TRACE_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{self.run_name}.json"
        path.write_text(json.dumps({"run": self.run_name, "totals": self.totals, "records": self.records},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return path
