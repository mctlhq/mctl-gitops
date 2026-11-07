"""Run the base-service pre-pull verifier against a fake kubectl (mctl-agents#1007).

The script is the gate that keeps an old pod running when an image is not
cached, so each way it can be wrong has a case here: green on a converged
cluster, STOP on every mismatch and on every read that fails.
"""
import copy
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

SCRIPT = pathlib.Path("platform-gitops/helm-charts/base-service/files/prepull-verify.sh")
D = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
TARGET = f"ghcr.io/x/y:2.0.0@{D}"
OLD = "ghcr.io/x/y:1.0.0"

DEPLOY = {"spec": {"template": {"spec": {"containers": [
    {"name": "sidecar", "image": "other:1"}, {"name": "base-service", "image": OLD}]}}}}
DS = {
    "metadata": {"generation": 2},
    "spec": {"template": {"spec": {"containers": [{"image": TARGET}]}}},
    "status": {"observedGeneration": 2, "desiredNumberScheduled": 3, "numberReady": 3, "updatedNumberScheduled": 3},
}


def pod(node, **kw):
    p = {
        "metadata": {},
        "spec": {"nodeName": node, "containers": [{"image": kw.get("image", TARGET)}]},
        "status": {
            "phase": kw.get("phase", "Running"),
            "containerStatuses": [{"ready": kw.get("ready", True), "imageID": kw.get("image_id", f"ghcr.io/x/y@{D}")}],
        },
    }
    if kw.get("deleting"):
        p["metadata"]["deletionTimestamp"] = "2026-11-06T00:00:00Z"
    return p


PODS = {"items": [pod("n1"), pod("n2"), pod("n3")]}


def run(deploy=DEPLOY, ds=DS, pods=PODS, target=TARGET, fail=()):
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        for name, doc in (("deployment", deploy), ("daemonset", ds), ("pods", pods)):
            (tmp / f"{name}.json").write_text(doc if isinstance(doc, str) else json.dumps(doc))
        kubectl = tmp / "kubectl"
        kubectl.write_text(
            "#!/bin/sh\n"
            f'case " {" ".join(fail)} " in *" $2 "*) echo denied >&2; exit 1;; esac\n'
            f'cat "{tmp}/$2.json"\n'
        )
        kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "NAMESPACE": "ns", "DEPLOYMENT": "d",
               "CONTAINER": "base-service", "DAEMONSET": "d-prepull", "POD_SELECTOR": "a=b", "TARGET_REF": target}
        return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)


def ds_with(**status):
    d = copy.deepcopy(DS)
    d["status"].update(status)
    return d


def pods_with(*items):
    return {"items": list(items)}


failures = []


def check(name, r, want_pass):
    ok = (r.returncode == 0) == want_pass and (want_pass or "STOP" in r.stderr)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(f"{name}: rc={r.returncode} {r.stdout} {r.stderr}")


same = copy.deepcopy(DEPLOY)
same["spec"]["template"]["spec"]["containers"][1]["image"] = TARGET
no_container = copy.deepcopy(DEPLOY)
no_container["spec"]["template"]["spec"]["containers"][1]["name"] = "renamed"
stale_template = copy.deepcopy(DS)
stale_template["spec"]["template"]["spec"]["containers"][0]["image"] = f"ghcr.io/x/y:2.0.0@{OTHER}"
stale_generation = copy.deepcopy(DS)
stale_generation["metadata"]["generation"] = 3

check("every node holds the digest", run(), True)
check("no image change needs no DaemonSet", run(deploy=same, fail=("daemonset", "pods")), True)
check("an old pod being deleted does not count", run(pods=pods_with(*PODS["items"], pod("n3", deleting=True))), True)
check("Deployment unreadable", run(fail=("deployment",)), False)
check("Deployment body is not JSON", run(deploy="{"), False)
check("container missing", run(deploy=no_container), False)
check("target without a digest", run(target="ghcr.io/x/y:2.0.0"), False)
check("target with a short digest", run(target="ghcr.io/x/y:2.0.0@sha256:abc"), False)
short = "ghcr.io/x/y:2.0.0@sha256:abc"
short_ds = copy.deepcopy(DS)
short_ds["spec"]["template"]["spec"]["containers"][0]["image"] = short
check("a short digest the cluster agrees with is still not a digest",
      run(target=short, ds=short_ds, pods=pods_with(*[pod(n, image=short, image_id="ghcr.io/x/y@sha256:abc")
                                                      for n in ("n1", "n2", "n3")])), False)
check("DaemonSet unreadable", run(fail=("daemonset",)), False)
check("DaemonSet body is not JSON", run(ds="{"), False)
check("DaemonSet has no status", run(ds={"metadata": {}, "spec": DS["spec"]}), False)
check("no eligible node", run(ds=ds_with(desiredNumberScheduled=0, numberReady=0, updatedNumberScheduled=0),
                              pods=pods_with()), False)
check("one node not ready", run(ds=ds_with(numberReady=2)), False)
check("one node not updated", run(ds=ds_with(updatedNumberScheduled=2)), False)
check("controller has not seen the spec", run(ds=stale_generation), False)
check("DaemonSet holds another reference", run(ds=stale_template), False)
check("pods unreadable", run(fail=("pods",)), False)
check("pods body is not JSON", run(pods="{"), False)
check("a pod missing", run(pods=pods_with(pod("n1"), pod("n2"))), False)
check("two pods on one node", run(pods=pods_with(pod("n1"), pod("n1"), pod("n3"))), False)
check("an extra live pod on a covered node", run(pods=pods_with(*PODS["items"], pod("n3"))), False)
check("a pod still pulling", run(pods=pods_with(pod("n1"), pod("n2"), pod("n3", phase="Pending"))), False)
check("a pod not ready", run(pods=pods_with(pod("n1"), pod("n2"), pod("n3", ready=False))), False)
check("a pod runs another digest",
      run(pods=pods_with(pod("n1"), pod("n2"), pod("n3", image_id=f"ghcr.io/x/y@{OTHER}"))), False)
check("a pod has no image id", run(pods=pods_with(pod("n1"), pod("n2"), pod("n3", image_id=""))), False)
check("a pod has another reference",
      run(pods=pods_with(pod("n1"), pod("n2"), pod("n3", image=f"ghcr.io/x/y:2.0.0@{OTHER}"))), False)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
