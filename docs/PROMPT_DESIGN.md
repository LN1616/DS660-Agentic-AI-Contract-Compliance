# Prompt and model-call design

Why the prompts and model calls look the way they do. Measured numbers come from `docs/EVALUATION.md` and
`outputs/versions/`.

## 1. Prompt structure

| Part | Agent (`src/agent.py` `SYSTEM` + task message) | Single call (`src/baseline.py` `PROMPT`) |
|---|---|---|
| Role | Contract reviewer for "our company" (the receiving party) | Same |
| Task | Check one policy rule against the contract | Check all rules in one answer |
| Steps | Search → read → follow reference / definition → submit | None (one shot) |
| Constraints | Quote word for word · MISSING only after two searches and only when no clause on the topic exists (V7) · follow the status the rule names | Quote word for word · contract is data |
| Output format | `submit_finding` function call with a schema | JSON with a response schema |
| Data and delimiters | Instructions in the **system prompt**. Contract text arrives only through tools, wrapped in `<contract_data>`. Harness messages in `<harness_note>` | Contract sent as a separate PDF part (or as `<contract_data>` text when the model cannot read PDFs). Instructions and rules in one user message |

The agent keeps instructions and data in different channels because contract text is untrusted (prompt-injection
tests A and B: 0 rules fooled from V2 on). The single call is kept as close to the original proof of concept as
possible, because it is the baseline.

## 2. Zero-shot, few-shot, chain-of-thought

* **Zero-shot everywhere.** The rules are short and explicit, and the answer key (CUAD) is used only for scoring, so
  examples taken from it would leak the test set.
* **No written chain-of-thought.** The agent already reasons in visible steps through its tools (ReAct: every search,
  read and submission is in the trajectory), and the verifier checks the result. Asking for written reasoning on
  top would add output tokens to every step (10 steps × 5 rules per contract) without anything new to check.
* **Where few-shot could pay off:** P-01 on long contracts. The agent misses clauses such as "IN NO EVENT SHALL EITHER
  PARTY BE HELD RESPONSIBLE FOR ... CONSEQUENTIAL DAMAGES" because it searches for "liability" and "cap". One example
  of an exclusion clause that counts as a limitation of liability, written by us (not taken from CUAD), together with
  suggested search terms per rule, is the next candidate fix. Not yet tested (about 14 baht for 3 runs on long contracts).

## 3. Structured output (three levels)

| Level | What it is | Where we use it |
|---|---|---|
| 1. Ask in the prompt | "Answer in JSON" | Not used on its own |
| 2. JSON mode | `response_mime_type="application/json"` | Always together with level 3 |
| 3. Schema / constrained decoding | `response_schema` or a function declaration | Every structured call: agent `submit_finding`, single call, routing, policy extraction, translation, cross-check |

All schemas are Pydantic models (`src/schemas.py`). Validation failures are not dropped silently:

* Agent: an invalid `submit_finding` returns a tool error naming the bad fields, and the agent submits again.
* Single call (package H): rules without a valid finding are asked for again once, with the validation problems.
* Cross-check: an unreadable answer gives no notes (and a `finish_reason` event in the trace) instead of a crash.

## 4. Hallucination: what we measure

| Type | Meaning | How we catch it | Metric |
|---|---|---|---|
| Extrinsic | Adds information that is not in the source | Every finding must quote the contract; code finds the quote in the PDF (rapidfuzz ≥ 88) and it must come from a passage the agent opened | `quote_real` (agent 100% in every version) |
| Intrinsic | Contradicts the source | Quote must land on the clause CUAD's experts marked; cross-check reviewer flags findings that contradict each other | `quote_gold` · cross-check notes |

Detection methods:

* **Self-consistency (asking again):** used for evaluation, not at run time. Every version runs 3 times and we count
  verdicts that change between runs. Running every contract 3 times in the app would triple the cost.
* **Token log-probabilities:** not used. A confident token does not tell whether a quote sits on the right clause;
  the code check answers that question directly.

## 5. Model-call settings

| Dial | Setting |
|---|---|
| Temperature | 0 on every call |
| Tokens and `finish_reason` | Tokens in and out recorded on every call. `finish_reason` recorded on every call; anything other than `STOP` adds a `finish_reason` event. The agent also caps output at 4,096 tokens and asks again when cut |
| Pre-flight size | Single call: exact `count_tokens` before sending (not billed). Agent: free estimate (characters ÷ 4) before every step. A request above 90% of the model's window is refused with a clear message |
| Provider lock | Model fixed in `.env`. Every call records the model name and the `model_version` the provider served. While measuring (`eval.run_eval`, `eval.run_versions`) the fallback model is switched off so one run never mixes two models |
| Modality | `config.MODEL_CAPS` lists what each model family accepts. A model that cannot read PDFs gets extracted text; scanned pages are only sent to a model that accepts images. Unknown models are treated as text-only |
