"""Exercise the optional work_item_id / execution_id argv build, taken from the
template.

`cwft-mctl-agents-investigate.yaml`'s `run-investigator` template builds its
argv with `set --` and conditionally appends `--work-item-id` /
`--execution-id` only when the caller supplied a non-empty value (gitops#1279).
The acceptance criterion that matters most is that a submit omitting both
parameters produces the exact argv the template produced before they existed —
a regression here silently changes the command line for every existing caller
(`mctl_trigger_issue`, a hand-submitted Workflow, the DevLoopWorkflow).

The block under test is EXTRACTED from the CWFT rather than restated — a copy
would keep passing after the template changed, which is the failure mode this
file exists to avoid (same reasoning as test_tpl_git_commit_yq.py and
test_rotate_github_token_scope.py). The slice never invokes python — the real
call happens later in the body, after `set +e` — so it is safe to run directly
under /bin/sh.

Run: python3 tests/test_cwft_investigate_work_context_argv.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

CWFT = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml")

START_MARKER = 'if [ -z "$WORKFLOW_ISSUE_URL" ]'
END_MARKER = "printf '\\n'"

ARROW = "→"  # the literal character `printf '→'` writes


def argv_build_source() -> str:
    """The argv-building slice out of run-investigator's container.args[2].

    From the `issue_url` required-fail-fast guard through the trailing
    `printf '\\n'` that ends the echo block, verbatim. A rename of either
    boundary must break this loudly rather than silently checking an empty
    string.
    """
    doc = yaml.safe_load(CWFT.read_text())
    templates = doc["spec"]["templates"]
    run_investigator = next(t for t in templates if t["name"] == "run-investigator")
    source = run_investigator["container"]["args"][2]
    start = source.find(START_MARKER)
    if start == -1:
        raise AssertionError(
            "could not find the issue_url required-guard in run-investigator's "
            "container.args — the template changed shape and this test is now "
            "checking nothing")
    end = source.find(END_MARKER, start)
    if end == -1:
        raise AssertionError(
            "could not find the trailing printf that ends the echo block — "
            "the template changed shape and this test is now checking nothing")
    return source[start:end + len(END_MARKER)]


SLICE = argv_build_source()


def run(issue_url="https://github.com/mctlhq/x/issues/1",
        work_item_id="", execution_id=""):
    """Run the extracted slice under /bin/sh with the three env vars set.

    Returns the CompletedProcess. The slice's only observable stdout is the
    `-> ...` echo — it never invokes python. PATH is inherited so `sh` and
    any command a hostile value might smuggle in (e.g. `touch`, `id`) resolve
    the same way they would in the real pod, which is what makes the
    injection case (T4) a meaningful check rather than a command-not-found.
    """
    env = dict(os.environ)
    env["WORKFLOW_ISSUE_URL"] = issue_url
    env["WORKFLOW_WORK_ITEM_ID"] = work_item_id
    env["WORKFLOW_EXECUTION_ID"] = execution_id
    script = "set -e\n" + SLICE
    return subprocess.run(
        ["sh", "-c", script],
        capture_output=True, text=True, env=env,
    )


failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


# T1. Omit-both case (unset and, separately, both set to "") — the argv must
# be byte-identical to the template's behaviour before these flags existed.
BASE_ARGV = (f"{ARROW} python -m orchestrator.run_issue_investigator "
             "--issue-url https://github.com/mctlhq/x/issues/1\n")

proc = run()
check("omit-both (unset) reproduces today's exact argv",
      proc.returncode == 0 and proc.stdout == BASE_ARGV,
      f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

proc = run(work_item_id="", execution_id="")
check("omit-both (explicit empty string) reproduces today's exact argv",
      proc.returncode == 0 and proc.stdout == BASE_ARGV,
      f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

# T2. Both-set case — both flags appended, in a fixed order.
proc = run(work_item_id="wi-abc", execution_id="ex-123")
want = (f"{ARROW} python -m orchestrator.run_issue_investigator "
        "--issue-url https://github.com/mctlhq/x/issues/1 "
        "--work-item-id wi-abc --execution-id ex-123\n")
check("both-set appends both flags in order",
      proc.returncode == 0 and proc.stdout == want,
      f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

# T3. One-of-two, both directions.
proc = run(work_item_id="wi-abc")
want = (f"{ARROW} python -m orchestrator.run_issue_investigator "
        "--issue-url https://github.com/mctlhq/x/issues/1 "
        "--work-item-id wi-abc\n")
check("work_item_id alone appends only --work-item-id",
      proc.returncode == 0 and proc.stdout == want,
      f"stdout={proc.stdout!r}")

proc = run(execution_id="ex-123")
want = (f"{ARROW} python -m orchestrator.run_issue_investigator "
        "--issue-url https://github.com/mctlhq/x/issues/1 "
        "--execution-id ex-123\n")
check("execution_id alone appends only --execution-id",
      proc.returncode == 0 and proc.stdout == want,
      f"stdout={proc.stdout!r}")

# T4. Injection case — a crafted value must survive as one argv token, never
# execute. Proves the `set --` construction, not just the `if` guards.
with tempfile.TemporaryDirectory() as d:
    sentinel = pathlib.Path(d) / "pwned"
    hostile_work_item = f"; touch {sentinel} ; "
    hostile_execution = 'a" ; id ; "b'
    proc = run(work_item_id=hostile_work_item, execution_id=hostile_execution)
    check("an injecting work_item_id does not execute",
          not sentinel.exists(), f"sentinel created: {sentinel}")
    check("both hostile values survive as single argv tokens",
          proc.returncode == 0
          and f"--work-item-id {hostile_work_item}" in proc.stdout
          and f"--execution-id {hostile_execution}" in proc.stdout,
          f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

# T5. Required-parameter regression — empty issue_url still fails fast even
# with both new identifiers set. The new code must not make an invalid submit
# look runnable.
proc = run(issue_url="", work_item_id="wi-abc", execution_id="ex-123")
check("empty issue_url still exits non-zero with both identifiers set",
      proc.returncode != 0 and "issue_url parameter is required" in proc.stderr,
      f"rc={proc.returncode} stderr={proc.stderr!r}")

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nargv build behaves as documented")
sys.exit(0)
