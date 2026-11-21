"""Re-run saved harness versions under one fixed test, several times each (protocol: docs/EVALUATION.md).

For each commit in eval.versions.COMMITS:
  1. check the commit out into a temporary git worktree (the system under test = that commit's src/);
  2. copy in TODAY's eval/ and data/ (same test code, same rules, same scoring for every version);
  3. per run k: clean review of the 6 test contracts -> injection test (variants A and B) on 3 of them,
     scored against the clean run of the same k;
  4. keep everything under outputs/versions/<commit>/run<k>/ (rows, full reports, traces); remove the worktree.
A run folder that already has both result files is skipped, so an interrupted batch can be started again.

Usage:  python -m eval.run_versions [runs=3] [commit ...]
Then:   python -m eval.compare_versions
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from src import config
from eval.versions import COMMITS

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.getenv("VERSIONS_OUT", ROOT / "outputs" / "versions"))
N_EVAL, N_INJ = os.getenv("VERSIONS_N", "6"), os.getenv("VERSIONS_N_INJ", "3")  # smaller only for a smoke test
WT = ROOT.parent / "_version_worktrees"   # outside the repo


def sh(args, cwd, env=None):
    print("  $", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, env=env, check=True)


def run_commit(commit: str, runs: int):
    systems = ",".join(COMMITS[commit])
    wt = WT / commit
    if wt.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
    sh(["git", "worktree", "add", "--detach", str(wt), commit], ROOT)
    try:
        shutil.copytree(ROOT / "eval", wt / "eval", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "data", wt / "data", dirs_exist_ok=True)
        shutil.copy(ROOT / ".env", wt / ".env")
        env = {**os.environ, "CUAD_DIR": str(config.CUAD_DIR), "PYTHONIOENCODING": "utf-8"}
        for k in range(1, runs + 1):
            out = BASE / commit / f"run{k}"
            if (out / "eval_rows.csv").exists() and (out / "injection_run.csv").exists():
                print(f"skip {commit} run{k} (done)")
                continue
            print(f"== {commit} run{k}  systems={systems}", flush=True)
            sh([sys.executable, "-m", "eval.run_eval", N_EVAL, "--systems", systems, "--out", str(out)], wt, env)
            sh([sys.executable, "-m", "eval.injection_test", "run", str(out / "eval_rows.csv"), N_INJ, "AB", systems,
                str(out)], wt, env)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for c in (sys.argv[2:] or COMMITS):
        run_commit(c, runs)
