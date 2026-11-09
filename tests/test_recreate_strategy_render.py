"""Render test for the Recreate flip of an existing Deployment (B4 P-1, 2026-11-09).

mctl-gitops#2394 set `strategy: {type: Recreate, rollingUpdate: null}` on the control
worker. The live Deployment carries the API server's defaulted rollingUpdate block,
owned by no field manager, so server-side apply neither removes it nor honours a null,
and the apply is rejected ("rollingUpdate: Forbidden"). Two things are fixed in the
render and asserted here:
  1. under Recreate no rendered Deployment has a rollingUpdate key, null or not;
  2. the control worker's Deployment is applied with Replace=true (kubectl replace).
Green on the real tree, red on each deliberate mutation of a copied chart.
Plain script: `python3 tests/test_recreate_strategy_render.py` (needs helm, pyyaml).
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / "platform-gitops/helm-charts/base-service"
SVC = ROOT / "platform-gitops/services/admins/mctl-agents-worker/values.yaml"
failures = []


def flag(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(f"{name}: {detail}")


def deployments(chart, values_file, *sets):
    cmd = ["helm", "template", "x", str(chart), "-f", str(values_file)]
    for s in sets:
        cmd += ["--set-json", s]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr
    return [d for d in yaml.safe_load_all(r.stdout) if d and d.get("kind") == "Deployment"], ""


def problems(chart):
    out = []
    docs, err = deployments(chart, SVC)
    if docs is None or len(docs) != 1:
        return [f"worker render failed or not one Deployment: {err}"]
    d = docs[0]
    strat = d["spec"].get("strategy") or {}
    if strat.get("type") != "Recreate":
        out.append(f"worker strategy is {strat!r}, not Recreate")
    if "rollingUpdate" in strat:
        out.append(f"Recreate renders a rollingUpdate key: {strat!r}")
    ann = (d["metadata"].get("annotations") or {})
    if ann.get("argocd.argoproj.io/sync-options") != "Replace=true":
        out.append(f"worker Deployment lacks Replace=true: {ann!r}")
    # a stray null from any values file must not reach the output either
    docs, err = deployments(chart, SVC, 'strategy={"type":"Recreate","rollingUpdate":{"maxSurge":1}}')
    if docs is None or "rollingUpdate" in (docs[0]["spec"].get("strategy") or {}):
        out.append(f"non-null rollingUpdate under Recreate survives the render: {err}")
    # RollingUpdate keeps its parameters
    docs, err = deployments(chart, SVC, 'strategy={"type":"RollingUpdate","rollingUpdate":{"maxSurge":2}}')
    if docs is None or (docs[0]["spec"]["strategy"].get("rollingUpdate") or {}).get("maxSurge") != 2:
        out.append(f"RollingUpdate parameters lost: {err}")
    return out


def mutate(name, edit):
    with tempfile.TemporaryDirectory() as t:
        c = pathlib.Path(t) / "base-service"
        shutil.copytree(BASE, c)
        f = c / "templates/deployment.yaml"
        s = f.read_text()
        n = edit(s)
        if n == s:
            flag(f"mutation {name} changed the file", False, "no-op mutation")
            return
        f.write_text(n)
        flag(f"red on mutation: {name}", bool(problems(c)), "mutation not detected")


p = problems(BASE)
flag("real tree: worker renders Recreate without rollingUpdate, applied with Replace=true", not p, "; ".join(p))
mutate("keep rollingUpdate under Recreate", lambda s: s.replace('toYaml (omit . "rollingUpdate")', "toYaml ."))
mutate("drop the Replace annotation", lambda s: s.replace("argocd.argoproj.io/sync-options: Replace=true", "x/y: z"))
if failures:
    print("\n".join(failures))
    sys.exit(1)
