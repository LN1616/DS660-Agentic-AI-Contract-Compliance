"""Harness logging: every LLM call's tokens, latency, model and estimated cost."""
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config

RETRYABLE = (429, 500, 503, "timeout", "network")


def error_code(e: Exception):
    """429 / 500 / 503 from the API, "timeout" for a hung call, "network" for a dropped connection."""
    code = getattr(e, "code", None)
    if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
        return "timeout"  # hung connection cut by config.CALL_TIMEOUT_MS: retry like an overload
    if type(e).__module__.split(".")[0].rstrip("0123456789") in ("httpx", "httpcore"):
        return "network"  # dropped connection (seen with 5 rules calling at once)
    return code


class Trace:
    _last_call = 0.0  # shared across runs in one process, for pacing
    _pace = threading.Lock()

    def __init__(self, run_name: str):
        self.run_name = run_name
        self.records: list[dict] = []

    def call(self, fn, label: str, retries: int = 4, model: str | None = None):
        """Run one LLM call. Paces calls (MIN_CALL_GAP seconds apart, free-tier friendly) and retries on
        overload, rate limit, timeout and dropped connections, with backoff plus random jitter so rules
        running in parallel do not all retry at the same moment."""
        with Trace._pace:  # rules checked in parallel share one pace: call STARTS stay MIN_CALL_GAP apart
            gap = config.MIN_CALL_GAP - (time.time() - Trace._last_call)
            if gap > 0:
                time.sleep(gap)
            Trace._last_call = time.time()
        t0 = time.time()
        for attempt in range(retries + 1):
            try:
                resp = fn()
                break
            except Exception as e:
                code = error_code(e)
                if code not in RETRYABLE or attempt == retries:
                    raise
                wait = round(min(60, 5 * 2 ** attempt) * random.uniform(0.75, 1.25), 1)
                self.records.append({"type": "retry", "label": label, "code": code, "wait_sec": wait, "model": model})
                print(f"    [{label}] Gemini busy ({code}), retrying in {wait}s ...", flush=True)
                time.sleep(wait)
        u = getattr(resp, "usage_metadata", None)
        tin = (getattr(u, "prompt_token_count", 0) or 0) if u else 0
        tout = ((getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
        self.records.append({"type": "llm", "label": label, "sec": round(time.time() - t0, 2),
                             "tokens_in": tin, "tokens_out": tout, "model": model or config.MODEL})
        return resp

    def call_model(self, make, label: str):
        """make(model_name) -> one API call. Tries config.MODEL; when it keeps failing with a retryable error
        and config.FALLBACK_MODEL is set, the same request goes to the fallback model (EP08 graceful failure).
        Every call records which model answered, so results can be reported per model."""
        models = [config.MODEL]
        if config.FALLBACK_MODEL and config.FALLBACK_MODEL != config.MODEL:
            models.append(config.FALLBACK_MODEL)
        for i, m in enumerate(models):
            last = i == len(models) - 1
            retries = 4 if len(models) == 1 else (config.RETRIES_BEFORE_FALLBACK if not last else 3)
            try:
                return self.call(lambda: make(m), label, retries=retries, model=m)
            except Exception as e:
                if last or error_code(e) not in RETRYABLE:
                    raise
                self.records.append({"type": "fallback", "label": label, "from": m, "to": models[i + 1],
                                     "code": error_code(e)})
                print(f"    [{label}] {m} still failing, switching to {models[i + 1]}", flush=True)

    def event(self, kind: str, **data):
        self.records.append({"type": kind, **data})

    @property
    def totals(self) -> dict:
        llm = [r for r in self.records if r["type"] == "llm"]
        tin = sum(r["tokens_in"] for r in llm)
        tout = sum(r["tokens_out"] for r in llm)
        cost = tin / 1e6 * config.PRICE_IN_PER_M + tout / 1e6 * config.PRICE_OUT_PER_M
        return {"llm_calls": len(llm), "tokens_in": tin, "tokens_out": tout,
                "llm_seconds": round(sum(r["sec"] for r in llm), 1), "cost_usd": round(cost, 4),
                "fallback_calls": sum(1 for r in llm if r.get("model", config.MODEL) != config.MODEL)}

    def save(self) -> Path:
        config.TRACE_DIR.mkdir(exist_ok=True)
        path = config.TRACE_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{self.run_name}.json"
        path.write_text(json.dumps({"run": self.run_name, "totals": self.totals, "records": self.records},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return path
