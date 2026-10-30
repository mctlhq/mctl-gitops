"""Run the shepherd's merge marker, verify gate and Telegram gate for real.

post-deploy-verify used to run on every shepherd tick: sleep 300s, then fail
the workflow on any Argo CD Application that went Degraded after the workflow
started. Nothing tied that to a merge, so on 2026-10-23 about 60 ticks that
had only addressed review comments failed in nine hours, each blaming a
flapping argocd/labs-mctl-telegram. The fix has three parts, each a script in
the template, and each is extracted and executed here rather than restated:

1. commit-and-push's record_transitions writes `merged` (yes/no) and
   `transitions.txt` from the staged .status.yaml diff.
2. post-deploy-verify skips only when merged=no AND the shepherd attempt
   reported succeeded; anything else, including absent files, verifies as
   before. A skipped run still writes degraded_unfiltered.txt, which onExit
   uses to decide whether resolving the incident fingerprint is safe.
3. notify-telegram reports a Succeeded run only when it carries a terminal
   transition (merged / rejected / review-stuck).

kubectl, curl, apk and sleep are replaced by stubs on PATH; git, jq, awk and
sed are the real tools.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml")
doc = yaml.safe_load(TPL.read_text())
TEMPLATES = {t["name"]: t for t in doc["spec"]["templates"]}
COMMIT = TEMPLATES["commit-and-push"]["script"]["source"]
VERIFY = TEMPLATES["post-deploy-verify"]["script"]["source"]
NOTIFY = TEMPLATES["notify-telegram"]["script"]["source"]

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name} {detail}")
        FAILURES.append(name)


def dedent(block, width):
    return "\n".join(ln[width:] if ln.startswith(" " * width) else ln
                     for ln in block.split("\n"))


def stubs(tmp, kubectl_json=None):
    """A bin dir with kubectl/curl/apk/sleep stubs, prepended to PATH."""
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "sleep").write_text('#!/bin/sh\necho "SLEPT $1" >> "$STUB_LOG"\n')
    (bindir / "apk").write_text("#!/bin/sh\nexit 0\n")
    # curl: record the -d body of every call, print an http code.
    (bindir / "curl").write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do\n'
        '  if [ "$1" = "-d" ]; then printf "%s\\n" "$2" >> "$CURL_LOG"; fi\n'
        '  shift\ndone\necho "http=200"\n')
    if kubectl_json is not None:
        (tmp / "apps.json").write_text(json.dumps(kubectl_json))
        (bindir / "kubectl").write_text(f'#!/bin/sh\ncat "{tmp}/apps.json"\n')
    for p in bindir.iterdir():
        p.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["STUB_LOG"] = str(tmp / "stub.log")
    env["CURL_LOG"] = str(tmp / "curl.log")
    return env


def relocate(script, tmp):
    """Point the script's fixed /tmp/onexit and /onexit paths into tmp."""
    return (script.replace("/tmp/onexit", f"{tmp}/out")
                  .replace("/onexit/", f"{tmp}/in/"))


# ---------------------------------------------------------------- part 1
m = re.search(r"^( *record_transitions\(\) \{\n.*?\n *\}\n *record_transitions)$",
              COMMIT, re.S | re.M)
assert m, "could not extract record_transitions from commit-and-push"
RECORD = dedent(m.group(1), 10)
m = re.search(r"^( *PATH_STATUS=.*?EXCL_ADOPTED=[^\n]*)$", COMMIT, re.S | re.M)
assert m, "could not extract the pathspec definitions from commit-and-push"
DEFS = dedent(m.group(1), 10)

A = "platform-gitops/agents-state/mctl-docs/proposals/issue-1-a/.status.yaml"
B = "platform-gitops/agents-state/mctl-api/proposals/issue-2-b/.status.yaml"


def record(changes):
    """Seed A and B at review-fixing, write `changes`, stage, record."""
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        repo = tmp / "repo"
        repo.mkdir()
        (tmp / "out").mkdir()
        git = ["git", "-C", str(repo)]
        subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.com"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        for rel in (A, B):
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("status: review-fixing\nupdated_at: '1'\n")
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "seed"], check=True)
        for rel, body in changes.items():
            (repo / rel).write_text(body)
        subprocess.run(git + ["add", "-A"], check=True)
        script = "set -e\n%s\n%s\n" % (DEFS, relocate(RECORD, tmp))
        r = subprocess.run(["sh", "-c", script], cwd=repo,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return ((tmp / "out/merged").read_text(),
                (tmp / "out/transitions.txt").read_text().split("\n")[:-1])


merged, tr = record({A: "status: merged\nupdated_at: '2'\n"})
check("flip to merged -> merged=yes", merged == "yes", merged)
check("flip to merged -> one transition", tr == [f"merged {A}"], tr)

merged, tr = record({A: "status: 'merged'\nupdated_at: '2'\n"})
check("quoted merged still counts", merged == "yes" and tr == [f"merged {A}"], (merged, tr))

merged, tr = record({A: "status: implemented\nupdated_at: '2'\n"})
check("non-terminal flip -> merged=no", merged == "no", merged)
check("non-terminal flip -> no transition", tr == [], tr)

merged, tr = record({A: "status: review-fixing\nupdated_at: '2'\n"})
check("status unchanged -> merged=no, no transition", (merged, tr) == ("no", []), (merged, tr))

merged, tr = record({A: "status: rejected\nupdated_at: '2'\n",
                     B: "status: review-stuck\nupdated_at: '2'\n"})
check("rejected + review-stuck -> merged=no", merged == "no", merged)
check("rejected + review-stuck -> both reported",
      sorted(tr) == sorted([f"rejected {A}", f"review-stuck {B}"]), tr)

merged, tr = record({A: "status: review-stuck\nupdated_at: '2'\n",
                     B: "status: merged\nupdated_at: '2'\n"})
check("one merged among two -> merged=yes", merged == "yes", merged)

# ---------------------------------------------------------------- part 2
NOW = "2026-10-23T10:00:00Z"
APPS = {"items": [
    {"metadata": {"namespace": "argocd", "name": "labs-mctl-telegram"},
     "status": {"health": {"status": "Degraded",
                           "lastTransitionTime": "2026-10-23T10:02:00Z"}}},
    {"metadata": {"namespace": "argocd", "name": "fine"},
     "status": {"health": {"status": "Healthy"}}},
]}


def verify(merged=None, shepherd=None):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        env = stubs(tmp, APPS)
        env["STARTED_AT"] = NOW
        (tmp / "out").mkdir()
        if merged is not None:
            (tmp / "in/commit").mkdir(parents=True)
            (tmp / "in/commit/merged").write_text(merged)
        if shepherd is not None:
            (tmp / "in/shepherd").mkdir(parents=True)
            (tmp / "in/shepherd/shepherd_status").write_text(shepherd)
        r = subprocess.run(["bash", "-c", relocate(VERIFY, tmp)], env=env,
                           capture_output=True, text=True)
        slept = (tmp / "stub.log").read_text() if (tmp / "stub.log").exists() else ""
        return (r.returncode,
                (tmp / "out/verify_status").read_text(),
                (tmp / "out/degraded_unfiltered.txt").read_text(),
                "SLEPT 300" in slept)


rc, status, unfiltered, slept = verify("no", "succeeded")
check("no merge + succeeded -> skipped, exit 0", (rc, status) == (0, "skipped"), (rc, status))
check("skipped -> no 300s sleep", not slept)
check("skipped -> unfiltered snapshot still written",
      unfiltered.strip() == "argocd/labs-mctl-telegram", repr(unfiltered))

for args, label in ((("yes", "succeeded"), "merged=yes"),
                    (("unknown", "succeeded"), "merged=unknown"),
                    (("no", "failed"), "shepherd failed"),
                    ((None, None), "no artifacts")):
    rc, status, _, slept = verify(*args)
    check(f"{label} -> verifies and flags the Degraded app",
          (rc, status, slept) == (1, "degraded", True), (rc, status, slept))

# ---------------------------------------------------------------- part 3


def notify(status, transitions):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        env = stubs(tmp)
        env.update(TG_BOT_TOKEN="x", TG_CHAT_ID="1", WORKFLOW_STATUS=status,
                   WORKFLOW_SERVICE="", WORKFLOW_SLUG="", WORKFLOW_DRY_RUN="false",
                   WORKFLOW_NAME="wf", WORKFLOW_DURATION="1",
                   WORKFLOW_TEMPLATE_KIND="shepherd")
        env.pop("MCTL_TOKEN", None)
        (tmp / "in/commit").mkdir(parents=True)
        (tmp / "in/commit/activity").write_text("yes")
        (tmp / "in/commit/transitions.txt").write_text(
            "".join(t + "\n" for t in transitions))
        r = subprocess.run(["sh", "-c", relocate(NOTIFY, tmp)], env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        log = tmp / "curl.log"
        bodies = [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []
        return [b["text"] for b in bodies if "chat_id" in b]


sent = notify("Succeeded", [])
check("Succeeded with activity but no terminal transition -> silent", sent == [], sent)

sent = notify("Succeeded", [f"merged {A}", f"review-stuck {B}"])
check("Succeeded with transitions -> one message", len(sent) == 1, sent)
check("message names service/slug per transition",
      len(sent) == 1 and "merged: mctl-docs/issue-1-a" in sent[0]
      and "review-stuck: mctl-api/issue-2-b" in sent[0], sent)

sent = notify("Failed", [])
check("Failed -> always notifies", len(sent) == 1, sent)

if not shutil.which("jq"):
    print("note: jq not found; parts 2 and 3 need it", file=sys.stderr)
if FAILURES:
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1)
print("\nall checks passed")
