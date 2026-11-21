"""Refusals must not trigger implement-fallback (#1053, #1206).

run-implementer's collector decides the step exit code. Real exit codes are
kept for crashes; only "everything handed off is needs-triage / no-commits"
becomes 64, and the fallback step's `when` skips on exactly that code. The
collector script is extracted from the template and run against a real git
repo; the `when` expression is asserted from the parsed template.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml")
doc = yaml.safe_load(TPL.read_text())
TEMPLATES = {t["name"]: t for t in doc["spec"]["templates"]}
SRC = "\n".join(TEMPLATES["run-implementer"]["container"]["args"])
m = re.search(r"<<'COLLECT'\n(.*?)\nCOLLECT", SRC, re.S)
assert m, "could not extract the collector from run-implementer"
COLLECT = m.group(1)

FAILURES = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f" {detail}"))
    if not cond:
        FAILURES.append(name)


NO_COMMITS = ("status: needs-triage\nupdated_at: 'x'\nfailure:\n"
              "  code: no-commits\n  stage: agent\n  message: m\n")
OTHER = "status: needs-triage\nupdated_at: 'x'\nfailure:\n  code: agent-error\n"
IMPL = "status: implemented\nupdated_at: 'x'\n"
REL = "platform-gitops/agents-state/svc/proposals/{}/.status.yaml"


def collect(rc, files):
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d) / "repo"
        root.mkdir()
        git = ["git", "-C", str(root)]
        subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.com"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        (root / "README").write_text("x")
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "seed"], check=True)
        for slug, body in files.items():
            p = root / REL.format(slug)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        script = (COLLECT.replace("/workdir/mctl-gitops", str(root))
                  .replace("/tmp/state-out", str(pathlib.Path(d) / "out")))
        r = subprocess.run([sys.executable, "-I", "-", str(rc)], input=script,
                           capture_output=True, text=True)
        return r.returncode


check("no-commits refusal, rc=1 -> 64", collect(1, {"a": NO_COMMITS}) == 64)
check("two no-commits refusals -> 64",
      collect(1, {"a": NO_COMMITS, "b": NO_COMMITS}) == 64)
check("no-commits mixed with another failure -> real rc",
      collect(1, {"a": NO_COMMITS, "b": OTHER}) == 1)
check("no-commits mixed with an implemented proposal -> real rc",
      collect(1, {"a": NO_COMMITS, "b": IMPL}) == 1)
check("other failure code -> real rc", collect(1, {"a": OTHER}) == 1)
check("crash with nothing handed off -> real rc", collect(137, {}) == 137)
check("rc=0 stays 0 even with a no-commits file", collect(0, {"a": NO_COMMITS}) == 0)

when = next(s for st in TEMPLATES["implement-proposals"]["steps"] for s in st
            if s["name"] == "implement-fallback")["when"]
check("fallback when keeps the != Succeeded guard",
      "steps['implement'].status != 'Succeeded'" in when, when)
check("fallback when skips on exit codes 45 and 64",
      "in ['45', '64']" in when, when)
check("fallback when defaults a missing exit code (pod-level Error still falls back)",
      "exitCode ?? '0'" in when, when)

# assert-attempt names the real cause instead of blaming quota.
ASSERT = TEMPLATES["assert-attempt"]["script"]["source"]
step = next(s for st in TEMPLATES["implement-proposals"]["steps"] for s in st
            if s["name"] == "assert-produced")
check("assert-produced passes the primary exit code",
      any(p["name"] == "primary_exit" for p in step["arguments"]["parameters"]))


def assert_attempt(primary, fallback, exit_code):
    import os
    env = dict(os.environ, PARAM_PRIMARY=primary, PARAM_FALLBACK=fallback,
               PARAM_PRIMARY_EXIT=exit_code)
    return subprocess.run(["sh", "-c", ASSERT], capture_output=True, text=True, env=env)


r = assert_attempt("Failed", "Omitted", "45")
check("exit 45 -> fails, names the missing approval, not quota",
      r.returncode == 1 and "missing approval" in r.stderr and "usage limit" not in r.stderr, r.stderr)
r = assert_attempt("Failed", "Omitted", "64")
check("exit 64 -> fails, names the no-commits refusal, not quota",
      r.returncode == 1 and "no commits" in r.stderr and "usage limit" not in r.stderr, r.stderr)
r = assert_attempt("Failed", "Failed", "1")
check("other failure -> fails with the quota hint", r.returncode == 1 and "usage limit" in r.stderr, r.stderr)
r = assert_attempt("Failed", "Succeeded", "1")
check("fallback succeeded -> exit 0", r.returncode == 0, r.stderr)
r = assert_attempt("Succeeded", "Omitted", "")
check("primary succeeded -> exit 0", r.returncode == 0, r.stderr)

if FAILURES:
    sys.exit(1)
print("all checks passed")
