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
  * against a copy of the chart with the default turned off, so the check
    follows the chart rather than a copy of its default;
  * against this repository's services, which must all pass today;
  * for the uid it hands to onboard (--uid-out), and through commit-service's
    own pin block, so an onboarded service passes that sweep with no manual
    edit (gitops#2149);

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
COMMIT_TPL = REPO / "platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml"
SERVICE_TEMPLATES = REPO / "platform-gitops/argo-workflows/service-templates"

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
# A service that opted out of the chart's runAsNonRoot default.
OPT_OUT = {"containerSecurityContext": {"runAsNonRoot": False}}

# (label, values or None for onboard, image user, want rc, want text)
CASES = [
    # The chart default is runAsNonRoot: an onboard (chart defaults only) and
    # a service that states nothing are both strict.
    ("onboard, default, numeric", None, "10001:10001", 0, "OK:"),
    ("onboard, default, named", None, "app", 1, "a user name"),
    ("onboard, default, no USER", None, "", 1, "root (USER not set)"),
    ("default, uid 0", {}, "0", 1, "root"),
    # Opted out: never refuses, warns on root/named.
    ("opt-out, numeric", OPT_OUT, "10001:10001", 0, "OK:"),
    ("opt-out, named", OPT_OUT, "app", 0, "WARNING:"),
    ("opt-out, no USER", OPT_OUT, "", 0, "WARNING:"),
    ("opt-out, uid 0", OPT_OUT, "0", 0, "WARNING:"),
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
for values, want_rc, want_text in ((STRICT, 2, "REFUSED: could not read"),
                                   ({}, 2, "REFUSED: could not read"),
                                   (OPT_OUT, 0, "UNKNOWN:")):
    root = checkout({**values, "image": {"repository": "not a registry", "tag": "1.0.0"}})
    try:
        rc, out = run(root)
    finally:
        shutil.rmtree(root)
    check(rc == want_rc and want_text in out and "OK:" not in out,
          f"failed image read with {values}: exit {rc}, want {want_rc} and {want_text!r}\n{out}")

# The check follows the chart, not a copy of its default: turn the default
# off and an onboard with a named user is only warned about, with no change
# to the script. (With the default on it is refused, in CASES above.)
root = checkout(None, chart_default={"runAsNonRoot": False})
try:
    rc, out = run(root, "app")
    check(rc == 0 and "WARNING:" in out, f"chart default off not honoured: exit {rc}\n{out}")
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

# --uid-out: the pin onboard commits. Written only when the verdict came from
# a numeric image USER; emptied for every other verdict, so a stale pin from
# an earlier run can never be committed.
UID_OUT_CASES = [
    # (label, values, image user, want file)
    ("onboard, uid:gid", None, "10001:10001", "10001:10001"),
    ("onboard, uid only", None, "101", "101"),
    ("onboard, leading zeros are decimal", None, "0101:007", "101:7"),
    ("onboard, named group", None, "10001:app", "10001"),
    ("onboard, named user", None, "app", ""),
    ("onboard, no USER", None, "", ""),
    ("security context decides", {"containerSecurityContext": {"runAsNonRoot": True, "runAsUser": 1000}},
     "10001", ""),
]
for label, values, user, want in UID_OUT_CASES:
    root = checkout(values)
    out_file = root / "image-user"
    out_file.write_text("stale:1")
    try:
        p = subprocess.run(["sh", str(SCRIPT), "check", "--image-user", user, "--uid-out", str(out_file),
                            str(root), "labs", "svc", "1.2.3", "ghcr.io/mctlhq/svc"],
                           capture_output=True, text=True)
        got = out_file.read_text().strip()
    finally:
        shutil.rmtree(root)
    check(got == want, f"--uid-out {label}: wrote {got!r}, want {want!r}\n{p.stdout}{p.stderr}")

# commit-service's onboard pin block, run verbatim with real yq over each
# service template the way onboard renders it: with the uid from --uid-out the
# values pass the repo-wide sweep above (offline, named image user); without
# it they are refused, so this is a detector both ways. A pin the template
# already carries is kept.
commit_src = next(t for t in yaml.safe_load(COMMIT_TPL.read_text())["spec"]["templates"]
                  if t["name"] == "commit-service")["script"]["source"]
m = re.search(r"\n( *)# Pin the image's numeric USER.*?\n(\1if \[ -n \"\$IMAGE_USER\" \]; then\n.*?\n\1fi)\n",
              commit_src, re.S)
check(m is not None, "commit-service has no image_user pin block")
onboard = re.search(r'if \[ "\$ACTION" = "onboard" \]; then\n(.*?)\n *elif \[ "\$ACTION" = "deploy" \]', commit_src, re.S)
check(onboard is not None and m is not None and m.group(2) in onboard.group(1),
      "the pin block must sit in the onboard branch only: deploy must not touch a hand-set pin")
check(commit_src.count("PIN_UID") == commit_src.count("PIN_UID", m.start(), m.end()) if m else False,
      "PIN_UID is used outside the onboard pin block")
if m and shutil.which("yq"):
    pin_block = "\n".join(l[len(m.group(1)):] for l in m.group(2).splitlines())

    def onboard_values(tpl, image_user, preset=None):
        d = pathlib.Path(tempfile.mkdtemp())
        shutil.copytree(CHART, d / "platform-gitops/helm-charts/base-service")
        svc = d / "platform-gitops/services/labs/svc"
        svc.mkdir(parents=True)
        body = tpl.read_text()
        for k, v in (("__TEAM_NAME__", "labs"), ("__SERVICE_NAME__", "svc"), ("__IMAGE_TAG__", "1.0.0"),
                     ("__PORT__", "8080"), ("__HOST__", "svc.example.com")):
            body = body.replace(k, v)
        (svc / "values.yaml").write_text(body)
        if preset is not None:
            subprocess.run(["yq", "eval", "-i", f".containerSecurityContext.runAsUser = {preset}",
                            str(svc / "values.yaml")], check=True)
        p = subprocess.run(["sh", "-c", 'set -e\nDIR="$1"\nIMAGE_USER="$2"\n' + pin_block, "sh",
                            str(svc), image_user], capture_output=True, text=True)
        check(p.returncode == 0, f"pin block failed for {tpl.parent.name}: {p.stderr}")
        return d, yaml.safe_load((svc / "values.yaml").read_text())

    def sweep(root):
        return subprocess.run(["sh", str(SCRIPT), "check", "--image-user", "app", str(root), "labs", "svc",
                               "1.2.3"], capture_output=True, text=True)

    templates = sorted(SERVICE_TEMPLATES.glob("*/values.yaml.tpl"))
    check(templates, "no service templates found")
    for tpl in templates:
        for image_user, want_csc, want_rc in (("10001:10001", {"runAsUser": 10001, "runAsGroup": 10001}, 0),
                                               ("101", {"runAsUser": 101}, 0),
                                               ("", {}, None)):
            root, values = onboard_values(tpl, image_user)
            try:
                csc = values.get("containerSecurityContext") or {}
                got = {k: csc[k] for k in ("runAsUser", "runAsGroup") if k in csc}
                check(got == want_csc, f"{tpl.parent.name} onboard with {image_user!r}: pinned {got}, want {want_csc}")
                p = sweep(root)
                if want_rc is not None:
                    check(p.returncode == want_rc,
                          f"{tpl.parent.name} onboarded with {image_user!r} fails the sweep:\n{p.stdout}{p.stderr}")
                else:
                    check(p.returncode != 0,
                          f"{tpl.parent.name} with no pin passes the sweep; the case above proves nothing")
            finally:
                shutil.rmtree(root)
        root, values = onboard_values(tpl, "10001:10001", preset=1000)
        try:
            check(values["containerSecurityContext"]["runAsUser"] == 1000,
                  f"{tpl.parent.name}: the onboard pin overwrote a runAsUser the template carries")
        finally:
            shutil.rmtree(root)
elif m:
    failures.append("yq not on PATH: the onboard pin block was not exercised")

# commit-service refuses an image_user that is not a uid with an optional
# numeric gid, before anything reaches yq.
v = re.search(r'\n( *)(if \[ -n "\$IMAGE_USER" \]; then\n *reject_multiline "image_user".*?\n\1fi)\n', commit_src, re.S)
r = re.search(r"^ *(reject_multiline\(\) \{\n.*?\n *\})$", commit_src, re.S | re.M)
check(v is not None and r is not None, "commit-service has no image_user validation")
if v and r:
    for value, ok in (("10001", True), ("10001:10001", True), ("0", False), ("10001:", False),
                      ("app", False), ("10001:app", False), ("1 | .image.tag = 1", False), ("10001\n2", False)):
        p = subprocess.run(["sh", "-c", r.group(1) + "\n" + v.group(2), "sh"], env={"IMAGE_USER": value, "PATH": "/usr/bin:/bin"},
                           capture_output=True, text=True)
        check((p.returncode == 0) == ok, f"image_user {value!r}: exit {p.returncode}, want {'accept' if ok else 'refuse'}")

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
    # commit reads its output, and a task skipped by `when` has none to
    # resolve; update-config is skipped inside the step instead.
    check("when" not in task, f"check-image-user must not be skipped by `when`: {task.get('when')}")
check("check-image-user" in tasks.get("commit", {}).get("dependencies", []),
      "commit must depend on check-image-user")
commit_args = {a["name"]: a["value"] for a in tasks.get("commit", {}).get("arguments", {}).get("parameters", [])}
check(commit_args.get("image_user") == "{{tasks.check-image-user.outputs.parameters.image_user}}",
      f"commit must receive check-image-user's image_user: {commit_args.get('image_user')}")
body = next((t for t in wft["spec"]["templates"] if t["name"] == "check-image-user"), None)
check(body is not None and "check-image-user.sh check" in body["script"]["source"],
      "the check-image-user template must run check-image-user.sh check")
if body is not None:
    src_body = body["script"]["source"]
    outs = {o["name"]: o for o in body.get("outputs", {}).get("parameters", [])}
    out_path = outs.get("image_user", {}).get("valueFrom", {}).get("path")
    check(out_path is not None and f"--uid-out {out_path}" in src_body,
          f"check-image-user must write its image_user output with --uid-out: {out_path}")
    check(outs.get("image_user", {}).get("valueFrom", {}).get("default") == "",
          "the image_user output needs an empty default")
    skip = src_body.find('"$PARAM_ACTION" = "update-config"')
    check(0 <= skip < src_body.find("check-image-user.sh check")
          and f": > {out_path}" in src_body[:skip],
          "check-image-user must empty its output and exit for update-config before checking")
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
