#!/usr/bin/env python3
"""The `validate` aggregator (gitops#2721) is green only when every shard is.

`validate` is the required check. It aggregates the validate-N shard jobs, so
the only thing standing between a red shard and a merge is the one step that
reads `needs`. This runs that real step's script against synthetic `needs`
JSON: green on all-success, red on each way a shard can fail to succeed
(failure, cancelled, skipped, missing, nothing at all).
"""
import json, os, pathlib, subprocess, sys
import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
WF = REPO / ".github/workflows/validate-manifests.yml"

wf = yaml.safe_load(WF.read_text())
job = wf["jobs"]["validate"]
step = job["steps"][0]
script = step["run"]
shards = sorted(k for k in wf["jobs"] if k.startswith("validate-"))
fails = []


def run(needs):
    r = subprocess.run(["bash", "-c", script], env={**os.environ, "NEEDS": json.dumps(needs)},
                       capture_output=True, text=True)
    return r.returncode


def ok(res="success"):
    return {s: {"result": res, "outputs": {}} for s in shards}


def check(cond, msg):
    if not cond:
        fails.append(msg)


check(len(job["steps"]) == 1 and "NEEDS" in step.get("env", {}), "aggregator must be the one step reading NEEDS")
check(len(shards) >= 2, "expected several validate-N shards")
check(run(ok()) == 0, "all shards success must be green")
for bad in ("failure", "cancelled", "skipped"):
    for s in shards:
        n = ok()
        n[s]["result"] = bad
        check(run(n) != 0, f"shard {s} {bad} must turn validate red")
n = ok()
n.pop(shards[0])
check(run(n) != 0, "a missing shard must turn validate red")
check(run({}) != 0, "no needs at all must turn validate red")
check(job.get("if", "").strip() == "always()", "validate must run always()")

for f in fails:
    print("FAIL:", f)
print("validate aggregator:", "RED" if fails else "all checks passed")
sys.exit(1 if fails else 0)
