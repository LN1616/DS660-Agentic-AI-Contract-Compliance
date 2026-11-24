# Contract Compliance Agent

An AI agent that reviews a supplier contract against a company procurement policy and reports, for each policy rule, whether the contract is COMPLIANT, DEVIATED, VIOLATED or MISSING the clause. Every quoted clause is checked against the source PDF before it reaches the report.

## How it works

```
PDF ─► ingest (text / table / scan) ─► passages + search index
                                             │
        for each policy rule:                ▼
        Gemini ──search_contract / read_passage──► tool results ──┐
          ▲                                                       │
          └──────── submit_finding ─► VERIFIER (plain code) ──────┘
                                       quote really in the PDF?
                                       read keyword passages before MISSING?
                                       fail → reason sent back (max 2)
                                       pass → finding
```

| Part | File | Role |
|---|---|---|
| Ingestion | `src/ingest.py` | pdfplumber for text and tables, vision model for scanned pages |
| Document tools | `src/document.py` | splits the contract into passages, TF-IDF search, quote matching |
| Agent + harness | `src/agent.py` | tool loop per rule, step budget, verifier, send-back |
| Baseline | `src/baseline.py` | the original single-call version, for comparison |
| Schema | `src/schemas.py` | Pydantic output contract |
| Trace | `src/trace.py` | tokens, latency and cost of every call → `traces/` |
| Policy | `data/policy_playbook.yaml` | 5 rules, each mapped to a CUAD category |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # then paste your key from https://aistudio.google.com/apikey
```

The CUAD dataset is expected at `../CUAD_v1/CUAD_v1/` (set `CUAD_DIR` in `.env` to change it).

## Setup for teammates (Windows)

1. Accept the GitHub invitation, then in a terminal:
   ```bash
   cd D:\
   git clone https://github.com/LN1616/DS660-Agentic-AI-Contract-Compliance.git
   cd DS660-Agentic-AI-Contract-Compliance
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
   Clone into a short path such as `D:\` (Streamlit fails to install in very long folder paths).
2. Create your own free key at https://aistudio.google.com/apikey and paste it into `.env` (`GEMINI_API_KEY=...`). Never commit or share the key.
3. Optional: put the CUAD folder (`CUAD_v1/CUAD_v1/` with `full_contract_pdf/` and `master_clauses.csv`) anywhere and set `CUAD_DIR=` in `.env`. Without it the app still works with uploaded PDFs; the evaluation scripts need it.
4. Check and run:
   ```bash
   python check_api.py
   streamlit run app.py
   ```

## Run

```bash
python -m eval.offline_check            # no API key needed: retrieval + verifier sanity on 6 CUAD contracts
python -m eval.test_harness_offline     # no API key needed: agent loop with a scripted fake model

python run_review.py --cuad FUSION              # agent on one CUAD contract
python run_review.py --cuad FUSION --baseline   # single-call baseline, same contract
python -m eval.run_eval 6                       # baseline vs agent on 6 contracts → outputs/eval_summary.csv
```

### Comparing harness versions

Every version (single call SC1–SC2, agent V1–V7) is re-run from its own commit under one fixed test, 3 times, and scored by the same code. Protocol, metric definitions and the rule for calling a difference real: [docs/EVALUATION.md](docs/EVALUATION.md). Results and each version's harness steps: [docs/version_results.md](docs/version_results.md).

```bash
python -m eval.run_versions 3      # each commit in eval/versions.py, 3 runs → outputs/versions/<commit>/run<k>/
python -m eval.compare_versions    # mean and min–max per version → docs/version_results.md
```
Long contracts (the 4 longest CUAD contracts, 75–154 pages):

```bash
VERSIONS_LONG=1 VERSIONS_SYSTEMS=A1 python -m eval.run_versions 3 <commit>   # → outputs/versions_long/<commit>/run<k>/
```

Offline tests (no API key): `eval.test_harness_offline`, `eval.test_parallel_offline`, `eval.test_failure_offline`,
`eval.test_v6_offline`, `eval.test_package_h_offline`.

## Interface

```bash
pip install streamlit
streamlit run app.py          # opens http://localhost:8501
```

Pick a CUAD sample or upload a PDF, choose the policy rules, choose Agent or Baseline, then press the analyse button. The page shows the agent's progress, risk counts, an executive summary in Thai, a filterable findings table, the verifier result and quoted text for each rule, legal approval for high-risk items, and an Excel download.

On Windows, if `pip install streamlit` fails with "filename too long", create the virtual environment in a short path (for example `D:\venvs\cca`).

## Release: which harness runs

The app runs the **V5 harness** plus the package-H checks. After every version was measured 3 times on the same
tests, V6 and V7 were no more accurate than V5 and cost more, so their features stay in the code behind switches
that are off by default (set to `1` in `.env` to turn on):

| Switch | Turns on | Measured (3 runs) |
|---|---|---|
| `V6_TOOLS` | `follow_reference`, `lookup_definition`, search page 2 | short set 22.3/24 vs V5 21.0 (within spread), 0.86 vs 0.68 baht per contract |
| `CROSS_CHECK` | one extra call that lists contradictions between findings | caught 9/10 planted contradictions on saved reports |
| `V7_MISSING_PROMPT` | stricter wording of when a clause counts as MISSING | 21.3/24, fixed one long-contract cell and broke one short-contract cell |

Prompt and model-call design (zero-shot, structured output, hallucination checks, model-call settings): [docs/PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md).

## Results (3 runs per version, gemini-3.5-flash-lite)

| | Single call (SC2) | Agent (V5, release) |
|---|---|---|
| Clause present / absent correct, 6 short CUAD contracts (of 24) | 21.0 (21–21) | 21.0 (20–22) |
| Same, 4 long CUAD contracts, 75–154 pages (of 16) | 10.7 (10–11) | 9.7 (9–10)¹ |
| Quotes found in the PDF, long contracts | 89% | 100%¹ |
| Fooled by a fake legal notice planted in the contract (of 15) | 3.3 | 0 |
| Seconds / baht per short contract | 14 s · 0.18 | 32 s · 0.68 |

¹ long-contract agent numbers are V6 (V5 tools + long-contract tools); V5 itself was not run on the long set.
No version is clearly more accurate than another (run ranges overlap). What the agent adds is evidence that can be
checked (every quote is verified against the PDF), resistance to instructions hidden in the contract, and wrong
answers flagged for a person instead of passed silently. Full tables: [docs/version_results.md](docs/version_results.md).

| Check | Result |
|---|---|
| Retrieval: CUAD gold clause in top-5 of one search (21 rule × contract pairs) | 95% (76% before fixing heading detection) |
| Verifier finds CUAD gold quotes in PDF text | 95% (39/41) |
