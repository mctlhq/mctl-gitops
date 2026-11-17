"""preview-deploy health gate (preview-health-gate in wft-preview-deploy.yaml).

A preview used to end green as soon as `helm --wait` returned, and its
DeployRecord never showed health, so mctl-api could never promote it
(mctlhq/mctl-api#1049, live check 2026-11-17). The gate asks again from outside
the release. Each case runs the real script from the template with kubectl and
curl replaced by stubs that serve fixtures; every "must fail" case is the shape
of a real failure, and every MUTANT removes one check and must turn a case red.

Also checks the wiring: the gate runs after the deploy and the workflow exposes
its verdict (health, health_url) as outputs.
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

import yaml
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parent.parent
WFT = REPO / "platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml"
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def doc():
    return yaml.safe_load(WFT.read_text())


def template(d, name):
    return next(t for t in d["spec"]["templates"] if t["name"] == name)


def gate_script(d=None):
    return template(d or doc(), "preview-health-gate")["script"]["source"]


def pod(name="p1", phase="Running", ready=True, digest=DIGEST, restarts=0, path="/healthz", terminating=False):
    spec = {"containers": [{"name": "c", "readinessProbe": {"httpGet": {"path": path, "port": 8080}} if path else {}}]}
    meta = {"name": name}
    if terminating:
        meta["deletionTimestamp"] = "2026-11-17T00:00:00Z"
    return {"metadata": meta, "spec": spec, "status": {
        "phase": phase,
        "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        "containerStatuses": [{"imageID": f"ghcr.io/mctlhq/x@{digest}", "restartCount": restarts}],
    }}


def run(script, pods, http="200", digest=DIGEST, restart_after=None, kubectl_fails=False, **env):
    """Run the gate; return (exit code, health file, health_url file)."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        bin_ = d / "bin"
        bin_.mkdir()
        calls = d / "calls"
        calls.write_text("0")
        (d / "fixture-pods.json").write_text(json.dumps({"items": pods}))
        (d / "fixture-pods2.json").write_text(json.dumps({"items": [pod(restarts=1)]}))
        stubs = {
            "kubectl": (
                "#!/bin/sh\n"
                + (f"cat {d}/fixture-pods.json; echo boom >&2; exit 1\n" if kubectl_fails else
                   f'n=$(cat {calls}); n=$((n+1)); echo $n > {calls}\n'
                   + (f'if [ "$n" -gt {restart_after} ]; then cat {d}/fixture-pods2.json; else cat {d}/fixture-pods.json; fi\n'
                      if restart_after is not None else f"cat {d}/fixture-pods.json\n"))),
            "curl": f"#!/bin/sh\nprintf '%s' '{http}'\n",
            "sleep": "#!/bin/sh\nexit 0\n",
        }
        for n, body in stubs.items():
            (bin_ / n).write_text(body)
            (bin_ / n).chmod(0o755)
        out = d / "health-gate"
        # The script writes scratch files under /tmp; each run gets its own so
        # concurrent cases do not share them.
        script = script.replace("/tmp/", f"{d}/")
        e = {"PATH": f"{bin_}:{os.environ['PATH']}", "PHG_TIMEOUT": "0", "PHG_WINDOW": "0",
             "PARAM_TEAM_NAME": "admins", "PARAM_COMPONENT_NAME": "docs-canary", "PARAM_PREVIEW_ID": "pakpgl",
             "PARAM_PREVIEW_URL": "https://docs-canary-pakpgl.mctl.ai", "PARAM_IMAGE_DIGEST": digest}
        e.update(env)
        r = subprocess.run(["sh", "-c", script], env=e, capture_output=True, text=True, cwd=d)
        h = (out / "health").read_text().strip() if (out / "health").exists() else None
        u = (out / "health_url").read_text().strip() if (out / "health_url").exists() else None
        return r.returncode, h, u


def cases(script):
    """(name, got, want): got is True when the gate behaved as it should."""
    def ok(rc, h, u, healthy):
        if healthy:
            return rc == 0 and h == "healthy" and u == "https://docs-canary-pakpgl.mctl.ai"
        return rc != 0 and h != "healthy" and not u

    out = []
    out.append(("converged preview is healthy", lambda: ok(*run(script, [pod()]), True), True))
    out.append(("two ready pods are healthy", lambda: ok(*run(script, [pod("a"), pod("b")]), True), True))
    out.append(("no HTTP readiness probe: verdict rests on the pods", lambda: ok(*run(script, [pod(path="")], http="503"), True), True))
    out.append(("empty digest skips only the digest comparison", lambda: ok(*run(script, [pod(digest=OTHER)], digest=""), True), True))
    out.append(("no pods fails", lambda: ok(*run(script, []), False), True))
    out.append(("a pod not Ready fails", lambda: ok(*run(script, [pod(ready=False)]), False), True))
    out.append(("one of two pods not Ready fails", lambda: ok(*run(script, [pod("a"), pod("b", ready=False)]), False), True))
    out.append(("a Pending pod fails", lambda: ok(*run(script, [pod(phase="Pending")]), False), True))
    out.append(("a terminating pod fails", lambda: ok(*run(script, [pod(terminating=True)]), False), True))
    out.append(("a pod on another digest fails", lambda: ok(*run(script, [pod(digest=OTHER)]), False), True))
    out.append(("a restart in the window fails", lambda: ok(*run(script, [pod()], restart_after=1), False), True))
    out.append(("a 503 on the readiness path fails", lambda: ok(*run(script, [pod()], http="503"), False), True))
    out.append(("no answer (000) fails", lambda: ok(*run(script, [pod()], http="000"), False), True))
    out.append(("kubectl failing is not healthy", lambda: ok(*run(script, [pod()], kubectl_fails=True), False), True))
    out.append(("a malformed digest is refused", lambda: ok(*run(script, [pod()], digest="sha256:zz"), False), True))
    out.append(("a bad preview id is refused", lambda: ok(*run(script, [pod()], PARAM_PREVIEW_ID="A;rm"), False), True))
    out.append(("a non-https url is refused", lambda: ok(*run(script, [pod()], PARAM_PREVIEW_URL="http://x"), False), True))
    return out


def failures_of(script):
    with ThreadPoolExecutor(16) as ex:
        got = list(ex.map(lambda c: c[1](), cases(script)))
    return [c[0] for c, g in zip(cases(script), got) if g != c[2]]


MUTANTS = {
    "digest comparison dropped": ('elif ($d != "") and', 'elif false and'),
    "Ready check dropped": ('"a pod is not Ready"', '"ok"'),
    "Running check dropped": ('elif ([.items[] | select(.status.phase != "Running")] | length) > 0 then "a pod is not Running"', 'elif false then "x"'),
    "terminating check dropped": ('elif ([.items[] | select(.metadata.deletionTimestamp != null)] | length) > 0 then "a pod is terminating"', 'elif false then "x"'),
    "no-pods check dropped": ('if (.items | length) == 0 then "no pods"', 'if false then "x"'),
    "restart check dropped": ('[ "$(restarts)" = "$before" ] || die', 'true || die'),
    "HTTP check dropped": ('case "$code" in 2??) break ;; esac', 'break'),
    "kubectl failure ignored": ('|| { echo "kubectl failed: $(tail -1 /tmp/kubectl.err)"; return 1; }', '|| true'),
    "failure written as healthy": ('echo unhealthy > "$OUT/health"; exit 1', 'echo healthy > "$OUT/health"; exit 1'),
    "success not written": ('echo healthy > "$OUT/health"\necho "$URL" >', 'true\necho "$URL" >'),
}


def main():
    d = doc()
    script = gate_script(d)
    bad = failures_of(script)
    survivors = []
    for name, (old, new) in MUTANTS.items():
        if script.count(old) != 1:
            survivors.append(f"{name}: anchor found {script.count(old)} times")
        elif not failures_of(script.replace(old, new)):
            survivors.append(name)

    wiring = []
    pipe = template(d, "preview-pipeline")
    tasks = {t["name"]: t for t in pipe["dag"]["tasks"]}
    gate = tasks.get("health-gate")
    if not gate or gate["template"] != "preview-health-gate":
        wiring.append("no health-gate task running preview-health-gate")
    elif "deploy-preview" not in gate.get("dependencies", []):
        wiring.append("health-gate does not wait for deploy-preview")
    outs = {o["name"]: o["valueFrom"].get("parameter", "") for o in pipe["outputs"]["parameters"]}
    for k in ("health", "health_url"):
        if "tasks.health-gate.outputs.parameters." + k not in outs.get(k, ""):
            wiring.append(f"workflow output {k} is not the gate's")
    if "image_digest" not in outs:
        wiring.append("workflow lost its image_digest output")

    for n in bad:
        print("FAIL", n)
    for w in wiring:
        print("WIRING", w)
    for s in survivors:
        print("MUTANT SURVIVED", s)
    n = len(cases(script))
    print(f"{n - len(bad)}/{n} cases, {len(MUTANTS) - len(survivors)}/{len(MUTANTS)} mutants killed")
    return 1 if bad or wiring or survivors else 0


if __name__ == "__main__":
    sys.exit(main())
