"""Image user: refuse an image that cannot start under runAsNonRoot.

kubelet enforces runAsNonRoot by the uid a container runs as. Without a
runAsUser in the security context that is the image's USER, and kubelet can
only verify a numeric one: `USER app` and root both end in
CreateContainerConfigError, after the deploy has already been committed.
check-image-user.sh renders the base-service chart with a service's values,
reads the effective runAsNonRoot/runAsUser, and judges the image USER before
anything is committed. This runs that script:

  * against fixtures for each branch: runAsNonRoot on or off, uid from the
    security context or from the image, numeric / named / root users, the
    container-over-pod precedence (an explicit container `false` wins), and
    an image read that fails;
  * against a copy of the chart with the default flipped on, so the check
    follows the chart without being edited when the default changes;
  * against this repository's services, which must all pass today;

and checks that deploy-service runs it between the build and the commit.

The registry read itself (fetch-user) needs network and is not exercised here;
every case below passes --image-user, or must not reach the registry at all.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "platform-gitops/argo-workflows/scripts/check-image-user.sh"
CHART = REPO / "platform-gitops/helm-charts/base-service"
WFT = REPO / "platform-gitops/argo-workflows/cluster-templates/wft-deploy-service.yaml"

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def checkout(values=None, chart_default=None):
    """A minimal checkout: the chart (optionally with a changed default) and,
    when `values` is given, services/labs/svc/values.yaml."""
    d = pathlib.Path(tempfile.mkdtemp())
    chart = d / "platform-gitops/helm-charts/base-service"
    shutil.copytree(CHART, chart)
    if chart_default is not None:
        cv = yaml.safe_load((chart / "values.yaml").read_text())
        cv["containerSecurityContext"].update(chart_default)
        (chart / "values.yaml").write_text(yaml.safe_dump(cv))
    if values is not None:
        svc = d / "platform-gitops/services/labs/svc"
        svc.mkdir(parents=True)
        body = {"image": {"repository": "ghcr.io/mctlhq/svc", "tag": "1.0.0"}, **values}
        (svc / "values.yaml").write_text(yaml.safe_dump(body))
    return d


def run(root, user=None, team="labs", name="svc", default_repo="ghcr.io/mctlhq/svc"):
    args = ["sh", str(SCRIPT), "check"]
    if user is not None:
        args += ["--image-user", user]
    args += [str(root), team, name, "1.2.3"]
    if default_repo:
        args.append(default_repo)
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


STRICT = {"containerSecurityContext": {"runAsNonRoot": True}}

# (label, values or None for onboard, image user, want rc, want text)
CASES = [
    # Default chart (runAsNonRoot off): never refuses, warns on root/named.
    ("onboard, default, numeric", None, "10001:10001", 0, "OK:"),
    ("onboard, default, named", None, "app", 0, "WARNING:"),
    ("onboard, default, no USER", None, "", 0, "WARNING:"),
    ("default, uid 0", {}, "0", 0, "WARNING:"),
    # runAsNonRoot on, uid from the image.
    ("strict, numeric", STRICT, "10001:10001", 0, "OK:"),
    ("strict, numeric no group", STRICT, "101", 0, "OK:"),
    ("strict, named", STRICT, "app", 1, "a user name"),
    ("strict, named:group", STRICT, "app:app", 1, "a user name"),
    ("strict, no USER", STRICT, "", 1, "root (USER not set)"),
    ("strict, root", STRICT, "root", 1, "root"),
    ("strict, uid 0", STRICT, "0:0", 1, "root"),
    # Pod-level runAsNonRoot counts too.
    ("pod-level strict, named", {"podSecurityContext": {"runAsNonRoot": True}}, "app", 1, "a user name"),
    # An explicit container false beats a pod-level true (kubelet precedence).
    ("container false over pod true", {"podSecurityContext": {"runAsNonRoot": True},
                                       "containerSecurityContext": {"runAsNonRoot": False}},
     "app", 0, "WARNING:"),
    # runAsUser in the security context decides; the image user is irrelevant.
    ("strict, pod runAsUser", {**STRICT, "podSecurityContext": {"runAsUser": 1000}}, "app", 0, "uid 1000"),
    ("strict, container runAsUser", {"containerSecurityContext": {"runAsNonRoot": True, "runAsUser": 1000}},
     "", 0, "uid 1000"),
    ("strict, runAsUser 0", {"containerSecurityContext": {"runAsNonRoot": True, "runAsUser": 0}},
     "10001", 1, "runAsUser 0"),
]

for label, values, user, want_rc, want_text in CASES:
    root = checkout(values)
    try:
        rc, out = run(root, user)
    finally:
        shutil.rmtree(root)
    check(rc == want_rc, f"{label}: exit {rc}, want {want_rc}\n{out}")
    check(want_text in out, f"{label}: output lacks {want_text!r}\n{out}")

# A runAsUser in the security context never needs the registry: with no
# --image-user and an image no registry serves, the check still passes.
root = checkout({**STRICT, "podSecurityContext": {"runAsUser": 1000}})
try:
    rc, out = run(root)
    check(rc == 0 and "uid 1000" in out, f"runAsUser set must not read the image:\n{out}")
finally:
    shutil.rmtree(root)

# An image read that fails is unknown, not fine: refused under runAsNonRoot,
# reported as UNKNOWN (never OK) without it. The repository is invalid, so
# the read fails before any network access.
for values, want_rc, want_text in ((STRICT, 2, "REFUSED: could not read"), ({}, 0, "UNKNOWN:")):
    root = checkout({**values, "image": {"repository": "not a registry", "tag": "1.0.0"}})
    try:
        rc, out = run(root)
    finally:
        shutil.rmtree(root)
    check(rc == want_rc and want_text in out and "OK:" not in out,
          f"failed image read with {values}: exit {rc}, want {want_rc} and {want_text!r}\n{out}")

# The check follows the chart: flip the default on and an onboard with a
# named user is refused, with no change to the script.
root = checkout(None, chart_default={"runAsNonRoot": True})
try:
    rc, out = run(root, "app")
    check(rc == 1 and "a user name" in out, f"flipped chart default not honoured: exit {rc}\n{out}")
finally:
    shutil.rmtree(root)

# A Deployment added through extraObjects is not the chart's workload: it
# neither blocks the deploy nor gets judged in its place. Its root user would
# be refused if it were picked up.
extra = {"extraObjects": [{"apiVersion": "apps/v1", "kind": "Deployment",
                           "metadata": {"name": "sidecar-app"},
                           "spec": {"selector": {"matchLabels": {"app": "x"}},
                                    "template": {"metadata": {"labels": {"app": "x"}},
                                                 "spec": {"securityContext": {"runAsNonRoot": True, "runAsUser": 0},
                                                          "containers": [{"name": "x", "image": "busybox"}]}}}}]}
for values, want in (({}, "OK:"), ({"blueGreen": {"enabled": True}}, "OK:")):
    root = checkout({**values, **extra})
    try:
        rc, out = run(root, "10001")
    finally:
        shutil.rmtree(root)
    check(rc == 0 and want in out, f"extraObjects Deployment with {values} must be ignored: exit {rc}\n{out}")

# Bad input and an unreadable checkout are refusals to decide, not passes.
root = checkout(None)
try:
    for args, label in ((["labs", "Bad_Name", "1.2.3"], "invalid component"),
                        (["labs", "svc", "1.2.3;x"], "invalid tag"),
                        (["labs", "svc", "1.2.3", ""], "onboard without a repository"),
                        (["labs", "svc", "1.2.3", "ghcr.io/x,image.tag=0"], "repository with a comma")):
        p = subprocess.run(["sh", str(SCRIPT), "check", "--image-user", "1000", str(root), *args],
                           capture_output=True, text=True)
        check(p.returncode == 2, f"{label}: exit {p.returncode}, want 2\n{p.stderr}")
finally:
    shutil.rmtree(root)
p = subprocess.run(["sh", str(SCRIPT), "check", "--image-user", "1000", "/nonexistent", "labs", "svc", "1.2.3", "r/x"],
                   capture_output=True, text=True)
check(p.returncode == 2, f"missing chart: exit {p.returncode}, want 2")

# Every service in this repository passes today (image users are pinned in
# the strict ones' security context; the rest are not refused).
for values in sorted((REPO / "platform-gitops/services").glob("*/*/values.yaml")):
    team, name = values.parts[-3], values.parts[-2]
    p = subprocess.run(["sh", str(SCRIPT), "check", "--image-user", "app", str(REPO), team, name, "1.2.3"],
                       capture_output=True, text=True)
    check(p.returncode == 0,
          f"{team}/{name} refused with a named image user. A service that opts into "
          "runAsNonRoot must pin runAsUser/runAsGroup in its values (numeric, from "
          "the image's real uid) so this offline check, and kubelet, can verify it:\n"
          f"{p.stdout}{p.stderr}")

# Every registry call is bounded and retried: the step gates the commit, so a
# stalled registry must not hang the deploy. Each curl goes through http().
src = SCRIPT.read_text()
calls = [l.strip() for l in src.splitlines() if l.strip().startswith(("curl ", "http "))
         or "$(curl " in l or "$(http " in l]
check(all("curl" not in c or "--max-time" in c for c in calls) and calls,
      f"registry calls must go through http() with timeouts: {calls}")
code = [l for l in src.splitlines() if not l.lstrip().startswith("#")]
check(sum(l.count("curl ") for l in code) == 1 and "--connect-timeout" in src and "--retry" in src,
      "exactly one curl, in http(), with --connect-timeout, --max-time and --retry")

# deploy-service runs the check after the build and before the commit, for
# onboard and deploy only, with the script taken from the checkout.
wft = yaml.safe_load(WFT.read_text())
tasks = {t["name"]: t for tpl in wft["spec"]["templates"] if "dag" in tpl for t in tpl["dag"]["tasks"]}
task = tasks.get("check-image-user")
check(task is not None, "deploy-service has no check-image-user task")
if task:
    check({"validate", "build-image"} <= set(task.get("dependencies", [])),
          f"check-image-user must follow validate and build-image: {task.get('dependencies')}")
    check("update-config" in task.get("when", ""), f"check-image-user must skip update-config: {task.get('when')}")
check("check-image-user" in tasks.get("commit", {}).get("dependencies", []),
      "commit must depend on check-image-user")
body = next((t for t in wft["spec"]["templates"] if t["name"] == "check-image-user"), None)
check(body is not None and "check-image-user.sh check" in body["script"]["source"],
      "the check-image-user template must run check-image-user.sh check")
check(body is not None and body.get("activeDeadlineSeconds"),
      "the check-image-user template must carry an activeDeadlineSeconds")
# The registry budget fits inside that deadline with room for the clone and
# the render, so a slow registry ends in the script's own verdict (UNKNOWN for
# a service whose image user does not matter yet), not in a deadline kill.
# A read makes at most five requests: manifest, token, manifest, index child,
# config blob.
m = re.search(r"--max-time (\d+) --retry (\d+)", src)
check(m is not None, "http() must set --max-time and --retry")
if m and body is not None and body.get("activeDeadlineSeconds"):
    max_time, retries = int(m.group(1)), int(m.group(2))
    per_request = (retries + 1) * max_time + (2 ** retries - 1)
    check(5 * per_request + 60 <= int(body["activeDeadlineSeconds"]),
          f"registry budget 5 x {per_request}s + 60s exceeds the step deadline "
          f"{body['activeDeadlineSeconds']}s")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"check-image-user: {len(CASES)} policy cases, fail-closed reads, chart flip, "
      "every service passes, deploy-service wiring")
