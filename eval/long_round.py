"""Score the long-contract round (test 22 H1 + test 23 new tools + cross-check notes) from saved files. No API.

Reads <out>/eval_rows.csv and <out>/eval_reports/*.json written by
    python -m eval.run_eval 4 --long --out outputs/long_round/run1
Per system: presence correct (vs CUAD), quote really in the PDF, quote on the CUAD expert span, time, cost.
Agent only: how often each V6 tool was used, findings that are right (presence + quote on CUAD span) AND used a
new tool (test 23), cross-check notes.
Usage:  python -m eval.long_round [out_dir]
"""
import glob
import json
import sys
from pathlib import Path

import pandas as pd

from eval.compare_versions import THB_PER_USD, gold_match

NEW_TOOLS = ("follow_reference", "lookup_definition")


def main(out: Path):
    rows = pd.read_csv(out / "eval_rows.csv")
    res = {}
    for system, mode in (("B2 single call", "B2"), ("A1 agent", "A1")):
        z = rows[rows.system == system]
        if z.empty:
            continue
        n = z.contract.nunique()
        hit, tot = gold_match(out, mode)
        res[system] = {
            "contracts": n,
            "presence": f"{int(z.presence_correct.dropna().astype(bool).sum())}/{int(z.presence_correct.notna().sum())}",
            "quote_real": round(float(z.quote_real.dropna().mean()), 3) if z.quote_real.notna().any() else None,
            "quote_gold": f"{hit}/{tot}",
            "sec_per_contract": round(z.sec.sum() / n, 1),
            "baht_per_contract": round(z.cost_usd.sum() / n * THB_PER_USD, 2),
        }
    use = {t: 0 for t in (*NEW_TOOLS, "search page 2")}
    helped, notes = [], []
    gold_rows = rows[(rows.system == "A1 agent")]
    for fp in glob.glob(str(out / "eval_reports" / "A1_*.json")):
        rep = json.load(open(fp, encoding="utf-8"))
        notes += [(rep["contract_title"][:30], n["finding_ids"], n["problem"]) for n in rep.get("cross_checks", [])]
        for r in rep["findings"]:
            traj = r.get("trajectory") or []
            used = {e["tool"] for e in traj if e.get("tool") in NEW_TOOLS}
            for t in used:
                use[t] += sum(e.get("tool") == t for e in traj)
            use["search page 2"] += sum(e.get("tool") == "search_contract" and "[page" in str(e.get("arg")) for e in traj)
            if used or any("[page" in str(e.get("arg")) for e in traj):
                row = gold_rows[(gold_rows.contract == rep["contract_title"][:40]) & (gold_rows.rule == r["finding"]["policy_id"])]
                ok = bool(len(row)) and str(row.presence_correct.iloc[0]) == "True"
                helped.append((rep["contract_title"][:30], r["finding"]["policy_id"], sorted(used), ok))
    # rules that used every allowed call (budget from the trace's step_budget event, else MAX_STEPS)
    allowed = {}
    for fp in glob.glob(str(out / "traces" / "*_eval_A1_*.json")):
        recs = json.load(open(fp, encoding="utf-8")).get("records", [])
        hit = [r.get("max_steps") for r in recs if r.get("type") == "step_budget" or r.get("event") == "step_budget"]
        if hit:
            allowed[Path(fp).name] = hit[0]
    cap = max(allowed.values(), default=None)
    z = rows[rows.system == "A1 agent"]
    if not z.empty:
        lim = cap or 10
        g = z[z.presence_correct.notna()]  # rules graded for presence
        res["A1 agent"]["used_whole_budget"] = (f"{int((g.steps >= lim).sum())}/{len(g)} graded · "
                                                f"{int((z.steps >= lim).sum())}/{len(z)} all (budget {lim})")
    print(pd.DataFrame(res).to_string())
    print(f"\nV6 tool use (calls): {use}")
    print(f"findings that used a new tool: {len(helped)} · presence correct among them: {sum(h[3] for h in helped)}")
    for h in helped:
        print(f"   {h[0]} {h[1]} tools {h[2]} presence correct {h[3]}")
    print(f"cross-check notes: {len(notes)}")
    for c, ids, p in notes:
        print(f"   {c} {ids}: {p[:200]}")
    (out / "long_round_summary.json").write_text(json.dumps(
        {"systems": res, "tool_use": use, "helped": helped, "cross_checks": notes}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/long_round/run1"))
