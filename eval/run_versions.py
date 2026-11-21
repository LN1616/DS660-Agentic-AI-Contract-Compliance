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


RUN_TIMEOUT = int(os.getenv("VERSIONS_RUN_TIMEOUT", "1800"))  # seconds per step; a hung API call otherwise waits forever
ATTEMPTS = 2


def sh(args, cwd, env=None, timeout=None):
    print("  $", " ".join(map(str, args)), flush=True)
    proc = subprocess.Popen(args, cwd=cwd, env=env)
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":  # the venv launcher starts a child python: kill the whole tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.wait()
        raise
    if rc:
        raise subprocess.CalledProcessError(rc, args)


LONG = os.getenv("VERSIONS_LONG") == "1"  # test 22: the 4 longest CUAD contracts, no injection files
if LONG:
    BASE = Path(os.getenv("VERSIONS_OUT", ROOT / "outputs" / "versions_long"))


def run_commit(commit: str, runs: int):
    systems = os.getenv("VERSIONS_SYSTEMS") or ",".join(COMMITS[commit])
    wt = WT / commit
    if wt.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
    sh(["git", "worktree", "add", "--detach", str(wt), commit], ROOT)
    try:
        shutil.copytree(ROOT / "eval", wt / "eval", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "data", wt / "data", dirs_exist_ok=True)
        shutil.copy(ROOT / ".env", wt / ".env")
        env = {**os.environ, "CUAD_DIR": str(config.CUAD_DIR), "PYTHONIOENCODING": "utf-8", "EVAL_NO_FALLBACK": "1"}
        for k in range(1, runs + 1):
            out = BASE / commit / f"run{k}"
            if (out / "eval_rows.csv").exists() and (LONG or (out / "injection_run.csv").exists()):
                print(f"skip {commit} run{k} (done)")
                continue
            for attempt in range(1, ATTEMPTS + 1):
                if out.exists():  # a partial run would mix its traces into the next attempt
                    shutil.rmtree(out)
                print(f"== {commit} run{k}  systems={systems}  attempt {attempt}", flush=True)
                try:
                    if LONG:
                        sh([sys.executable, "-m", "eval.run_eval", "4", "--long", "--systems", systems, "--out", str(out)],
                           wt, env, RUN_TIMEOUT)
                        break
                    sh([sys.executable, "-m", "eval.run_eval", N_EVAL, "--systems", systems, "--out", str(out)],
                       wt, env, RUN_TIMEOUT)
                    sh([sys.executable, "-m", "eval.injection_test", "run", str(out / "eval_rows.csv"), N_INJ, "AB",
                        systems, str(out)], wt, env, RUN_TIMEOUT)
                    break
                except subprocess.TimeoutExpired:
                    print(f"!! {commit} run{k} timed out after {RUN_TIMEOUT}s (hung API call), retrying", flush=True)
            else:
                raise RuntimeError(f"{commit} run{k} timed out {ATTEMPTS} times")
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for c in (sys.argv[2:] or COMMITS):
        run_commit(c, runs)
