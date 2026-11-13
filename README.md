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

## Run

```bash
python -m eval.offline_check            # no API key needed: retrieval + verifier sanity on 6 CUAD contracts
python -m eval.test_harness_offline     # no API key needed: agent loop with a scripted fake model

python run_review.py --cuad FUSION              # agent on one CUAD contract
python run_review.py --cuad FUSION --baseline   # single-call baseline, same contract
python -m eval.run_eval 6                       # baseline vs agent on 6 contracts → outputs/eval_summary.csv
```

## Interface

```bash
pip install streamlit
streamlit run app.py          # opens http://localhost:8501
```

Pick a CUAD sample or upload a PDF, choose the policy rules, choose Agent or Baseline, then press the analyse button. The page shows the agent's progress, risk counts, an executive summary in Thai, a filterable findings table, the verifier result and quoted text for each rule, legal approval for high-risk items, and an Excel download.

On Windows, if `pip install streamlit` fails with "filename too long", create the virtual environment in a short path (for example `D:\venvs\cca`).

## Results so far

| Check | Result |
|---|---|
| Retrieval: CUAD gold clause in top-5 of one search (21 rule × contract pairs) | 95% (76% before fixing heading detection) |
| Verifier finds CUAD gold quotes in PDF text | 95% (39/41) |
| Baseline vs agent | run `eval.run_eval` |
