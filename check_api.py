"""Check that the Gemini API key in .env works. Sends one tiny request.

Usage:  python check_api.py
"""
import os
import sys

from src import config


def main():
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or key == "your_key_here":
        sys.exit("FAIL  .env has no real key yet. Replace your_key_here with the key from AI Studio.")
    print(f"Key found in .env (ends with ...{key[-4:]}). Model: {config.MODEL}")
    try:
        resp = config.client().models.generate_content(model=config.MODEL, contents="Reply with the single word: ready")
    except Exception as e:
        msg = str(e)
        hint = ("Key is wrong or was deleted. Copy it again from AI Studio." if "API_KEY_INVALID" in msg or "API key not valid" in msg
                else "Free-tier limit reached. Wait 1 minute and try again." if "429" in msg or "RESOURCE_EXHAUSTED" in msg
                else f"Model '{config.MODEL}' not available. Change MODEL in .env (see AI Studio model list)." if "404" in msg
                else "No internet or Google is blocked on this network." if "Connect" in msg or "getaddrinfo" in msg
                else "See the error above.")
        sys.exit(f"FAIL  {type(e).__name__}: {msg[:300]}\nHINT  {hint}")
    u = resp.usage_metadata
    print(f"OK    Gemini replied: {resp.text.strip()!r}  (tokens in {u.prompt_token_count}, out {u.candidates_token_count})")
    print("      Connection works. Next: python run_review.py --cuad FUSION")


if __name__ == "__main__":
    main()
