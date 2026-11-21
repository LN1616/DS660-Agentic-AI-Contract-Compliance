"""Test 24 · V6 cross-check reviewer on SAVED reports (no agent re-run). Real API: 1 call per report, ~0.05 baht each.

Planted: copy a real V5 report and make one finding claim the contract has NO clause on a topic that another
finding quotes (the classic contradiction between two separately-made findings). Normal: the same reports untouched.
Pass when: planted caught >= 8/10 with the planted pair cited · false alarms on normal reports <= 1/10.
Any note on a normal report is printed so a person can judge whether it is a false alarm or a real disagreement.
Usage:  python -m eval.cross_check_test [n=10]
"""
import glob
import json
import sys

from src import agent, config
from src.schemas import ReviewedFinding
from src.trace import Trace
from eval.versions import VERSIONS

PLANT_TH = "สัญญาฉบับนี้ไม่มีข้อกำหนดใดเกี่ยวกับ{topic}เลย จึงถือว่าขาดข้อนี้"


def reports(n: int):
    """Real V5 reports, each with at least one quoted finding and one other finding to plant into."""
    out = []
    for fp in sorted(glob.glob(str(config.OUTPUT_DIR / "versions" / VERSIONS["V5"]["commit"] / "run*" / "eval_reports" / "A1_*.json"))):
        rep = json.load(open(fp, encoding="utf-8"))
        fs = [ReviewedFinding.model_validate(r) for r in rep["findings"]]
        quoted = [r for r in fs if r.finding.extracted_text.strip() and r.finding.compliance_status != "MISSING"]
        if quoted and len(fs) >= 2:
            out.append((fp, fs, quoted[0]))
    return out[:n]


def plant(fs, source):
    """Another finding now says the contract has no clause on the source finding's topic."""
    target = next(r for r in fs if r.finding.policy_id != source.finding.policy_id)
    copy = [r.model_copy(deep=True) for r in fs]
    t = next(r for r in copy if r.finding.policy_id == target.finding.policy_id)
    t.finding.issue_description += " " + PLANT_TH.format(topic=source.finding.clause_category)
    return copy, {source.finding.policy_id, target.finding.policy_id}


def main(n: int):
    config.MIN_CALL_GAP = float(config.MIN_CALL_GAP)
    trace = Trace("cross_check_test")
    rows = reports(n)
    caught = alarms = 0
    for fp, fs, src in rows:
        planted, pair = plant(fs, src)
        notes = agent.cross_check(planted, trace, "th")
        hit = any(pair <= set(nt.finding_ids) for nt in notes)
        caught += hit
        normal = agent.cross_check(fs, trace, "th")
        alarms += bool(normal)
        name = fp.split("eval_reports")[0][-6:-1] + " " + fp.rsplit("A1_", 1)[1][:24]
        print(f"{name}: planted {sorted(pair)} caught {hit} · normal report notes {len(normal)}")
        for nt in normal:
            print(f"    normal note {nt.finding_ids}: {nt.problem[:160]}")
    t = trace.totals
    print(f"\nplanted contradictions caught : {caught}/{len(rows)}  (pass >= {int(0.8 * len(rows))})")
    print(f"normal reports with a note    : {alarms}/{len(rows)}  (pass <= {max(1, len(rows) // 10)}) · read the notes above")
    print(f"cost: {t['llm_calls']} calls · {t['cost_usd'] * 33:.2f} baht (US${t['cost_usd']:.4f})")
    trace.save()
    out = config.OUTPUT_DIR / "cross_check_test.json"
    out.write_text(json.dumps({"caught": caught, "alarms": alarms, "n": len(rows), "cost": t}, ensure_ascii=False, indent=1),
                   encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
