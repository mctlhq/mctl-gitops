"""Post-sync health gate (gitops#2653): health-gate.sh and its wiring.

deploy-service used to end green as soon as its commit was pushed; a version
that crashed on start still reported success. health-gate.sh decides from
what the platform observes, the same way for every service:

  * Argo CD Synced and Healthy at a revision that contains the commit;
  * every pod of the release running the digest the committed values
    resolve to (the imageID kubelet recorded), one ReplicaSet, all ready;
  * the same pods, ready, with no new restarts, through a stability window;
  * for a public host with a readiness path, a 2xx from it.

Each case runs the real script against a throwaway git repository, with
kubectl, curl and the digest resolver replaced by stubs that serve fixtures.
Every "must fail" case below is the shape of a real failure: the gate is only
a detector if it goes red on them and green on a converged service.

The second half checks the wiring: deploy-service runs the gate after the
commit for every action (skip_health_check does not skip it), and the
workflow exposes the gate's results as its own outputs.
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "platform-gitops/argo-workflows/scripts/health-gate.sh"
CHART_VALUES = REPO / "platform-gitops/helm-charts/base-service/values.yaml"
WFT = REPO / "platform-gitops/argo-workflows/cluster-templates/wft-deploy-service.yaml"
COMMIT_TPL = REPO / "platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml"

D_NEW = "sha256:" + "a" * 64
D_OLD = "sha256:" + "b" * 64

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def rev(cwd, ref="HEAD"):
    return subprocess.run(["git", "-C", str(cwd), "rev-parse", ref], check=True,
                          capture_output=True, text=True).stdout.strip()


STUB_KUBECTL = r"""#!/bin/sh
# Serves $FX/app.json, $FX/pods.json (or pods.<n>.json by call count),
# $FX/deploys.json. A missing fixture or $FX/<kind>.fail fails the call.
FX="$HG_FX"
case "$*" in
  *annotate*) exit 0 ;;
  *"get application"*) kind=app ;;
  *"get pods"*) kind=pods ;;
  *"get deployments"*) kind=deploys ;;
  *) echo "unexpected kubectl $*" >&2; exit 3 ;;
esac
[ -e "$FX/$kind.fail" ] && { echo "error: forbidden" >&2; exit 1; }
if [ "$kind" = pods ] && [ -e "$FX/pods.1.json" ]; then
  n=$(cat "$FX/pods.count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FX/pods.count"
  f="$FX/pods.$n.json"; [ -e "$f" ] || f=$(ls "$FX"/pods.*.json | sort -t. -k2 -n | tail -1)
  cat "$f"; exit 0
fi
[ -e "$FX/$kind.json" ] || { echo "error: not found" >&2; exit 1; }
cat "$FX/$kind.json"
"""

STUB_CURL = r"""#!/bin/sh
# Prints $FX/http_code as curl's -w output; "000" means no answer.
code=$(cat "$HG_FX/http_code" 2>/dev/null || echo 200)
echo "$*" >> "$HG_FX/curl.log"
printf '%s' "$code"
[ "$code" = 000 ] && exit 7
exit 0
"""

STUB_RESOLVE = r"""#!/bin/sh
echo "$1" >> "$HG_FX/resolve.log"
[ -e "$HG_FX/resolve.fail" ] && { echo "registry answered HTTP 503" >&2; exit 2; }
cat "$HG_FX/resolve"
"""


def write_exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class Case:
    """A gitops checkout with one service, a deploy commit, and fixtures."""

    def __init__(self, values, team="labs", name="svc"):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.team, self.name = team, name
        self.repo = self.d / "repo"
        chart = self.repo / "platform-gitops/helm-charts/base-service"
        chart.mkdir(parents=True)
        shutil.copy(CHART_VALUES, chart / "values.yaml")
        git(self.d, "init", "-q", str(self.repo))
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = rev(self.repo)
        svc = self.repo / f"platform-gitops/services/{team}/{name}"
        svc.mkdir(parents=True)
        body = {"image": {"repository": "ghcr.io/mctlhq/svc", "tag": "1.2.3"}, **values}
        (svc / "values.yaml").write_text(yaml.safe_dump(body))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "deploy")
        self.commit = rev(self.repo)
        # A later commit on main: Argo CD is usually ahead of the deploy.
        (self.repo / "later").write_text("x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "later")
        self.head = rev(self.repo)

        self.fx = self.d / "fx"
        self.fx.mkdir()
        self.bin = self.d / "bin"
        self.bin.mkdir()
        write_exec(self.bin / "kubectl", STUB_KUBECTL)
        write_exec(self.bin / "curl", STUB_CURL)
        write_exec(self.d / "resolve.sh", STUB_RESOLVE)
        self.out = self.d / "out"
        self.resolve(D_NEW)
        self.app()
        self.pods([pod("p1")])
        self.deploys(1)

    def resolve(self, digest):
        (self.fx / "resolve").write_text(digest + "\n")

    def app(self, sync="Synced", health="Healthy", revisions=None):
        revisions = [self.head, self.head] if revisions is None else revisions
        (self.fx / "app.json").write_text(json.dumps(
            {"status": {"sync": {"status": sync, "revisions": revisions},
                        "health": {"status": health}}}))

    def pods(self, items, seq=None):
        if seq is None:
            (self.fx / "pods.json").write_text(json.dumps({"items": items}))
        else:
            for i, its in enumerate(seq, 1):
                (self.fx / f"pods.{i}.json").write_text(json.dumps({"items": its}))

    def deploys(self, replicas):
        (self.fx / "deploys.json").write_text(json.dumps(
            {"items": [{"spec": {"replicas": replicas}}]}))

    def fail(self, kind):
        (self.fx / f"{kind}.fail").write_text("")

    def run(self, commit=None, timeout=3, stable=1):
        env = dict(os.environ)
        env.update({
            "PATH": f"{self.bin}:{env['PATH']}",
            "HG_FX": str(self.fx),
            "HG_RESOLVE": f"sh {self.d / 'resolve.sh'}",
            "HG_OUT_DIR": str(self.out),
            "HG_TIMEOUT": str(timeout),
            "HG_INTERVAL": "1",
            "HG_STABLE": str(stable),
        })
        p = subprocess.run(
            ["sh", str(SCRIPT), str(self.repo), self.team, self.name, commit or self.commit],
            capture_output=True, text=True, env=env, timeout=60)
        res = {}
        if self.out.exists():
            for f in self.out.iterdir():
                res[f.name] = f.read_text().strip()
        return p.returncode, res, p.stdout + p.stderr


def pod(name, digest=D_NEW, ready=True, restarts=0, hash_="h1", owner="ReplicaSet",
        phase="Running", terminating=False):
    meta = {"name": name, "labels": {"pod-template-hash": hash_},
            "ownerReferences": [{"kind": owner}]}
    if terminating:
        meta["deletionTimestamp"] = "2026-11-16T00:00:00Z"
    return {"metadata": meta, "status": {"phase": phase, "containerStatuses": [
        {"name": "base-service", "imageID": f"ghcr.io/mctlhq/svc@{digest}",
         "ready": ready, "restartCount": restarts},
        # A sidecar on another image must not count.
        {"name": "sidecar", "imageID": f"ghcr.io/mctlhq/mc@{D_OLD}", "ready": True,
         "restartCount": 9},
    ]}}


WEB = {"ingress": {"enabled": True, "host": "svc.example.test"}}
WORKER = {"probes": {"liveness": None, "readiness": None}}


def expect(name, case, rc, health, reason_has=None, **kw):
    got_rc, res, log = case.run(**kw)
    check(got_rc == rc, f"{name}: exit {got_rc}, want {rc}\n{log}")
    check(res.get("health") == health, f"{name}: health {res.get('health')!r}, want {health!r}\n{log}")
    if reason_has:
        check(reason_has in res.get("reason", ""),
              f"{name}: reason {res.get('reason')!r} lacks {reason_has!r}")
    return res, log


# ── Green on a converged service ─────────────────────────────────────────────
c = Case(WEB)
res, log = expect("web healthy", c, 0, "healthy", "answers 2xx")
check(res.get("health_url") == "https://svc.example.test", f"web healthy: health_url {res.get('health_url')!r}")
check(res.get("image_digest") == D_NEW, f"web healthy: image_digest {res.get('image_digest')!r}")
check(res.get("argo_revision") == c.head, f"web healthy: argo_revision {res.get('argo_revision')!r}")
check("https://svc.example.test/readyz" in (c.fx / "curl.log").read_text(),
      "web healthy: did not probe the chart's default readiness path")
check("ghcr.io/mctlhq/svc:1.2.3" in (c.fx / "resolve.log").read_text(),
      "web healthy: did not resolve the committed repository:tag")

c = Case({**WEB, "probes": {"readiness": {"path": "/health"}}})
expect("custom readiness path", c, 0, "healthy")
check("https://svc.example.test/health" in (c.fx / "curl.log").read_text(),
      "custom readiness path: probed the wrong path")

c = Case(WORKER)
res, _ = expect("worker healthy", c, 0, "healthy", "no restarts")
check(not (c.fx / "curl.log").exists(), "worker healthy: probed HTTP for a service with no host")
check(res.get("health_url") == "", "worker healthy: a worker has no health_url")

# A host but no readiness probe (skip_health_check): nothing to ask over HTTP.
c = Case({**WEB, **WORKER})
expect("host without readiness probe", c, 0, "healthy")
check(not (c.fx / "curl.log").exists(), "host without readiness probe: probed HTTP anyway")

c = Case({**WORKER, "image": {"repository": "ghcr.io/mctlhq/svc", "tag": "1.2.3", "digest": D_NEW}})
c.fail("resolve")
expect("pinned digest needs no registry", c, 0, "healthy")

# Old pods that are terminating, evicted, or a Job's are history.
c = Case(WORKER)
c.pods([pod("p1"), pod("old", digest=D_OLD, hash_="h0", terminating=True),
        pod("evicted", digest=D_OLD, hash_="h0", phase="Failed"),
        pod("job", digest=D_OLD, owner="Job", hash_="-")])
expect("history ignored", c, 0, "healthy")

c = Case({**WEB})
(c.fx / "http_code").write_text("401")
expect("auth wall reported, not hidden", c, 0, "healthy", "HTTP not verified")

# Ready only shortly before the deadline: the stability window still runs out.
c = Case(WORKER)
c.pods(None, seq=[[pod("p1", ready=False)], [pod("p1")]])
expect("ready near the deadline", c, 0, "healthy", timeout=3, stable=4)

# blueGreen Rollout pods carry rollouts-pod-template-hash.
c = Case(WORKER)
new = pod("new"); new["metadata"]["labels"] = {"rollouts-pod-template-hash": "r1"}
old = pod("old"); old["metadata"]["labels"] = {"rollouts-pod-template-hash": "r0"}
c.pods([new, old])
expect("rollout across two rollout hashes", c, 1, "unhealthy", "ReplicaSets")

# The chart prefers ingress.hosts over ingress.host.
c = Case({"ingress": {"enabled": True, "host": "old.example.test", "hosts": ["new.example.test"]}})
res, _ = expect("hosts over host", c, 0, "healthy")
check(res.get("health_url") == "https://new.example.test", f"hosts over host: {res.get('health_url')!r}")

# Under a path prefix the public URL would ask something else: not verified.
c = Case({"ingress": {"enabled": True, "host": "svc.example.test", "path": "/api"}})
expect("ingress path prefix", c, 0, "healthy", "HTTP not verified")
check(not (c.fx / "curl.log").exists(), "ingress path prefix: probed HTTP anyway")

# ── Red on each failure shape ───────────────────────────────────────────────
c = Case(WORKER)
c.pods([pod("p1", digest=D_OLD)])
expect("old digest", c, 1, "unhealthy", "do not run")

c = Case(WORKER)
c.pods([pod("p1", ready=False, restarts=4)])
expect("crash loop / not ready", c, 1, "unhealthy", "not ready")

c = Case(WORKER)
c.pods([pod("new"), pod("old", digest=D_NEW, hash_="h0")])
expect("rollout not finished", c, 1, "unhealthy", "ReplicaSets")

# Ready at every look, but restarting in between: never stable.
c = Case(WORKER)
c.pods(None, seq=[[pod("p1", restarts=i)] for i in range(10)])
expect("restarts during the window", c, 1, "unhealthy", "restarted or were replaced", timeout=4, stable=2)

c = Case(WEB)
(c.fx / "http_code").write_text("503")
expect("url 5xx", c, 1, "unhealthy", "HTTP 503")

c = Case(WEB)
(c.fx / "http_code").write_text("000")
expect("url no answer", c, 1, "unhealthy", "did not answer")

c = Case(WORKER)
c.app(revisions=[c.base, c.base])
expect("argo behind the commit", c, 1, "unhealthy", "does not contain")

c = Case(WORKER)
c.app(sync="OutOfSync")
expect("argo out of sync", c, 1, "unhealthy", "OutOfSync")

c = Case(WORKER)
c.app(health="Degraded")
expect("argo degraded", c, 1, "unhealthy", "Degraded")

c = Case(WORKER)
c.pods([])
expect("no pods but replicas wanted", c, 1, "unhealthy", "no running pods")

# ── Could not observe is unknown, never healthy ─────────────────────────────
c = Case(WORKER)
c.fail("app")
expect("argo unreadable", c, 1, "unknown", "cannot read Application")

c = Case(WORKER)
c.fail("pods")
expect("pods unreadable", c, 1, "unknown", "cannot list pods")

c = Case(WORKER)
c.fail("resolve")
expect("registry unreadable", c, 1, "unknown", "cannot resolve")

c = Case(WORKER)
c.app(revisions=[])
expect("argo without revision", c, 1, "unknown", "no sync revision")

c = Case(WORKER)
c.pods([])
c.fail("deploys")
expect("zero pods, deployments unreadable", c, 1, "unhealthy", "no running pods")

# ── Scaled to zero on purpose: idle, said as such ───────────────────────────
c = Case(WORKER)
c.pods([])
c.deploys(0)
expect("scaled to zero", c, 0, "idle", "scaled to zero")

c = Case({**WORKER, "autoscaling": {"enabled": True}})
c.pods([])
c.deploys(0)
expect("autoscaled to zero is not idle", c, 1, "unhealthy")

# ── Bad input ────────────────────────────────────────────────────────────────
c = Case(WORKER)
rc, _, _ = c.run(commit="HEAD; rm -rf /")
check(rc == 2, f"bad commit: exit {rc}, want 2")
rc, _, _ = c.run(commit="f" * 40)
check(rc == 2, f"unknown commit: exit {rc}, want 2")

# ── Wiring ───────────────────────────────────────────────────────────────────
wft = yaml.safe_load(WFT.read_text())
templates = {t["name"]: t for t in wft["spec"]["templates"]}
pipeline = templates["deploy-pipeline"]
tasks = {t["name"]: t for t in pipeline["dag"]["tasks"]}
gate = tasks.get("health-gate")
check(gate is not None, "deploy-service has no health-gate task")
if gate:
    deps = set(gate.get("dependencies", []))
    check({"commit", "refresh-apps-appset", "patch-autoscaling"} <= deps,
          f"health-gate must run after commit, refresh and autoscaling; depends on {sorted(deps)}")
    check("when" not in gate, "health-gate must not be conditional (skip_health_check does not skip it)")
    args = {p["name"]: p["value"] for p in gate["arguments"]["parameters"]}
    check(args.get("commit_sha") == "{{tasks.commit.outputs.parameters.commit_sha}}",
          "health-gate must wait for the commit deploy-service pushed")
outs = {p["name"]: p["valueFrom"]["parameter"] for p in pipeline.get("outputs", {}).get("parameters", [])}
for name in ("health", "health_url", "argo_revision", "image_digest"):
    check(outs.get(name) == f"{{{{tasks.health-gate.outputs.parameters.{name}}}}}",
          f"deploy-pipeline must output {name} from health-gate")
src = templates.get("health-gate", {}).get("script", {}).get("source", "")
check("health-gate.sh" in src, "health-gate template must run health-gate.sh")
check("{{" not in src, "health-gate script source must take parameters through env (gitops#992)")

commit_tpl = yaml.safe_load(COMMIT_TPL.read_text())
cs = next(t for t in commit_tpl["spec"]["templates"] if t["name"] == "commit-service")
check(any(p["name"] == "commit_sha" for p in cs.get("outputs", {}).get("parameters", [])),
      "commit-service must output commit_sha")
body = cs["script"]["source"]
push = body.index('if git push origin HEAD:main; then')
check(body.index("git rev-parse HEAD > /tmp/commit_sha", push) < body.index("break", push),
      "commit-service must record the pushed HEAD before leaving the push loop")

if failures:
    print(f"{len(failures)} failure(s):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("health gate: all checks passed")
