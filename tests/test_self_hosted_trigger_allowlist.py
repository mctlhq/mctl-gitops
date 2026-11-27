"""Self-hosted runners only on trusted events (mctlhq/mctl-gitops#2993, ADR 0004).

mctl-gitops is public. A self-hosted job reachable from a pull_request-style
event would give pull-request code a shell on hardware we own. ADR 0004 allows
self-hosted jobs only on an ALLOWLIST of events: `push` restricted to `main`
and `workflow_dispatch`. Any other trigger (pull_request, pull_request_target,
pull_request_review, issue_comment, workflow_run, merge_group, schedule, push
to other branches or tags, ...) is refused. This is an allowlist on purpose:
a denylist of three events let every event it did not name through.

Could-not-observe is never observed-absent:
- a `runs-on` the test cannot resolve to GitHub-hosted labels (an expression
  that is not a literal matrix list, a runner `group`) counts as self-hosted;
- a reusable workflow in another repository cannot be read here, so it must be
  listed in EXTERNAL_REUSABLE with a reviewed justification, or the test fails.

Plain script, run by validate-manifests.yml:
`python3 tests/test_self_hosted_trigger_allowlist.py`.
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows"

HOSTED = re.compile(r"^(ubuntu|macos|windows)-[a-z0-9.-]+$")
ALLOWED_EVENTS = {"push", "workflow_dispatch"}
ALLOWED_PUSH_BRANCHES = ["main"]

# Reusable workflows outside this repository, keyed by path without the @ref.
# Each entry was read on mctlhq/.github main. "hosted" means every job runs on
# GitHub-hosted labels, from any caller. A "fork-guarded" entry runs on a
# self-hosted runner and is allowed ONLY from the caller files listed in
# `callers`, each with exactly the listed caller events and `uses` ref: any
# other caller, event or ref fails, so the exception cannot spread.
EXTERNAL_REUSABLE = {
    "mctlhq/.github/.github/workflows/agent-trailer.yml": {"verdict": "hosted"},
    "mctlhq/.github/.github/workflows/claude-review.yml": {"verdict": "hosted"},
    # Runs on [self-hosted, agy-reviewer]. Its job `if:` requires, for the
    # non-formal path, `github.event.pull_request.head.repo.full_name ==
    # github.repository`, so pull requests from forks never reach the runner;
    # only branches pushed by collaborators with write access do. The guard
    # reads `github.event.pull_request`, which only a pull_request caller
    # provides, hence the single allowed event. Residual risk: the callee is
    # referenced by `@main`, so a change to that guard in mctlhq/.github is not
    # visible to this offline test; it is reviewed in that repository.
    "mctlhq/.github/.github/workflows/agy-review.yml": {
        "verdict": "fork-guarded",
        "callers": {"agy-review.yml": {"events": {"pull_request"}, "ref": "main"}},
    },
}


def events(doc):
    # PyYAML reads the bare key `on` as boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {e: None for e in on}
    if isinstance(on, dict):
        return on
    raise AssertionError(f"unreadable `on:` {on!r}")


def labels(job):
    """GitHub-hosted labels of a job, or None when it is (or may be) self-hosted."""
    runs_on = job.get("runs-on")
    if isinstance(runs_on, dict):  # {group: ..., labels: ...} is a runner group
        return None
    values = runs_on if isinstance(runs_on, list) else [runs_on]
    out = []
    for value in values:
        if not isinstance(value, str):
            return None
        m = re.fullmatch(r"\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}", value)
        if m:
            matrix = (job.get("strategy") or {}).get("matrix")
            if not isinstance(matrix, dict):  # an expression matrix is unresolvable
                return None
            key = m.group(1)
            literal = matrix.get(key, [])
            include = matrix.get("include", [])
            if not isinstance(literal, list) or not isinstance(include, list):
                return None
            # `include` entries may add new values for the key.
            for entry in include:
                if not isinstance(entry, dict):
                    return None
                if key in entry:
                    literal = literal + [entry[key]]
            if not literal or not all(isinstance(v, str) for v in literal):
                return None
            out.extend(literal)
        elif "${{" in value:
            return None
        else:
            out.append(value)
    return out if out and all(HOSTED.match(v) for v in out) else None


def trusted_only(evts):
    """Empty list when every event is on the allowlist, else the reasons."""
    bad = []
    for name, cfg in evts.items():
        if name not in ALLOWED_EVENTS:
            bad.append(f"event `{name}` is not on the allowlist")
        elif name == "push":
            cfg = cfg or {}
            if cfg.get("branches") != ALLOWED_PUSH_BRANCHES or set(cfg) - {"branches", "paths", "paths-ignore"}:
                bad.append(f"push must be restricted to branches {ALLOWED_PUSH_BRANCHES} only, got {cfg!r}")
    return bad


def violations(workflows):
    """workflows: {filename: parsed doc}. Returns a list of violation strings."""
    out = []

    def check_jobs(fname, doc, evts, via=""):
        for jid, job in (doc.get("jobs") or {}).items():
            where = f"{fname}:{jid}{via}"
            uses = job.get("uses")
            if uses:
                if uses.startswith("./"):
                    callee = pathlib.PurePosixPath(uses).name
                    if callee not in workflows:
                        out.append(f"{where}: local reusable {uses} not found")
                        continue
                    check_jobs(callee, workflows[callee], evts, via=f" (called from {fname}:{jid})")
                    continue
                key, _, ref = uses.partition("@")
                entry = EXTERNAL_REUSABLE.get(key)
                if entry is None:
                    out.append(f"{where}: external reusable {key} is not reviewed in EXTERNAL_REUSABLE")
                elif entry.get("verdict") == "hosted":
                    pass
                elif entry.get("verdict") == "fork-guarded":
                    allowed = (entry.get("callers") or {}).get(fname)
                    if allowed is None:
                        out.append(f"{where}: fork-guarded {key} may not be called from {fname}")
                    elif set(evts) != allowed["events"]:
                        out.append(f"{where}: fork-guarded {key} called on {sorted(evts)}, allowed only {sorted(allowed['events'])}")
                    elif ref != allowed["ref"]:
                        out.append(f"{where}: fork-guarded {key} called at @{ref}, reviewed at @{allowed['ref']}")
                else:
                    out.append(f"{where}: external reusable {key} has verdict {entry.get('verdict')!r}")
                continue
            if labels(job) is None:
                for reason in trusted_only(evts):
                    out.append(f"{where}: self-hosted (or unresolvable) runs-on {job.get('runs-on')!r}: {reason}")

    for fname, doc in workflows.items():
        evts = events(doc)
        if set(evts) == {"workflow_call"}:
            continue  # checked with the caller's events when it is called
        check_jobs(fname, doc, evts)
    return out


def load_repo():
    return {p.name: yaml.safe_load(p.read_text()) for p in sorted(WF.glob("*.y*ml"))}


def wf(on, runs_on, **job):
    return {"on": on, "jobs": {"j": {"runs-on": runs_on, **job}}}


def test_repo_is_clean():
    found = violations(load_repo())
    assert not found, "\n".join(found)


def test_rejects():
    # Each of these must be refused; a test that can only pass is not a test.
    bad = {
        "pull_request": wf({"pull_request": None}, ["self-hosted", "x"]),
        "pull_request_review": wf({"pull_request_review": None}, "self-hosted"),
        "workflow_run": wf({"workflow_run": {"workflows": ["a"]}}, "self-hosted"),
        "merge_group": wf({"merge_group": None}, "self-hosted"),
        "schedule": wf({"schedule": [{"cron": "0 0 * * *"}]}, "self-hosted"),
        "push any branch": wf({"push": None}, "self-hosted"),
        "push other branch": wf({"push": {"branches": ["main", "dev"]}}, "self-hosted"),
        "push tags": wf({"push": {"branches": ["main"], "tags": ["*"]}}, "self-hosted"),
        "bare on string": wf("pull_request", "self-hosted"),
        "runner group": wf({"pull_request": None}, {"group": "Default"}),
        "unresolved expression": wf({"pull_request": None}, "${{ inputs.runner }}"),
        "matrix not literal": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"os": "${{ fromJSON(x) }}"}}),
        "matrix with self-hosted": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"os": ["ubuntu-latest", "self-hosted"]}}),
        "unreviewed external": {"on": {"workflow_dispatch": None}, "jobs": {"j": {"uses": "someone/else/.github/workflows/x.yml@main"}}},
        "matrix include adds self-hosted": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"os": ["ubuntu-latest"], "include": [{"os": "self-hosted"}]}}),
        "matrix only via include": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"include": [{"os": "self-hosted"}]}}),
        "matrix include expression": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"os": ["ubuntu-latest"], "include": "${{ fromJSON(x) }}"}}),
        "matrix is an expression": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": "${{ fromJSON(x) }}"}),
    }
    for name, doc in bad.items():
        assert violations({"w.yml": doc}), f"accepted but must reject: {name}"
    # A local reusable workflow inherits the caller's events.
    caller = {"on": {"pull_request": None}, "jobs": {"c": {"uses": "./.github/workflows/callee.yml"}}}
    callee = {"on": {"workflow_call": None}, "jobs": {"x": {"runs-on": "self-hosted"}}}
    assert violations({"caller.yml": caller, "callee.yml": callee}), "self-hosted callee under pull_request accepted"
    # The fork-guarded agy exception stays narrow: other caller file, extra or
    # different event, or another ref are all refused.
    agy = "mctlhq/.github/.github/workflows/agy-review.yml"
    narrow = {
        "other caller file": ("other.yml", {"pull_request": None}, "main"),
        "issue_comment caller": ("agy-review.yml", {"issue_comment": None}, "main"),
        "pull_request_target caller": ("agy-review.yml", {"pull_request_target": None}, "main"),
        "extra event": ("agy-review.yml", {"pull_request": None, "workflow_run": {"workflows": ["a"]}}, "main"),
        "other ref": ("agy-review.yml", {"pull_request": None}, "feature"),
    }
    for name, (fname, on, ref) in narrow.items():
        doc = {"on": on, "jobs": {"j": {"uses": f"{agy}@{ref}"}}}
        assert violations({fname: doc}), f"fork-guarded exception widened: {name}"


def test_accepts():
    good = {
        "dispatch": wf({"workflow_dispatch": None}, ["self-hosted", "x"]),
        "push main": wf({"push": {"branches": ["main"], "paths": ["a/**"]}}, "self-hosted"),
        "hosted on pr": wf({"pull_request": None}, "ubuntu-latest"),
        "hosted matrix on pr": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"os": ["ubuntu-latest", "macos-latest"]}}),
        "reviewed external": {"on": {"pull_request": None}, "jobs": {"j": {"uses": "mctlhq/.github/.github/workflows/claude-review.yml@abc"}}},
        "hosted matrix with include": wf({"pull_request": None}, "${{ matrix.os }}", strategy={"matrix": {"os": ["ubuntu-latest"], "include": [{"os": "macos-latest", "x": 1}, {"x": 2}]}}),
    }
    agy_ok = {"on": {"pull_request": {"types": ["opened"]}}, "jobs": {"j": {"uses": "mctlhq/.github/.github/workflows/agy-review.yml@main"}}}
    assert not violations({"agy-review.yml": agy_ok}), "the reviewed agy caller must be accepted"
    for name, doc in good.items():
        found = violations({"w.yml": doc})
        assert not found, f"rejected but must accept: {name}: {found}"


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
