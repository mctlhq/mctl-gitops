"""build-image.yaml stamps org.opencontainers.image.revision (mctlhq/mctl-gitops#2528, task 13).

The label must carry the 40-hex commit of the source checkout, resolved from the
checkout and never from the input ref, and an unresolvable revision must refuse the
build instead of producing an empty or wrong label. The step's real script runs
against throwaway git repositories; named mutants of it must turn the suite red.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/build-image.yaml"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:400]}")


def load(text):
    doc = yaml.safe_load(text)
    steps = next(iter(doc["jobs"].values()))["steps"]
    return steps


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}).stdout.strip()


def run_script(script, cwd, env=None):
    out = pathlib.Path(cwd) / "gh_out"
    out.write_text("")
    r = subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, "GITHUB_OUTPUT": str(out), **(env or {})})
    return r.returncode, out.read_text(), r.stdout + r.stderr


def judge(text):
    """Returns [(name, ok, detail)] for a candidate workflow text."""
    res = []
    steps = load(text)
    names = [s.get("name") for s in steps]
    try:
        i_co = names.index("Checkout source repo")
        i_rev = names.index("Resolve the source revision")
        i_build = names.index("Build and push")
    except ValueError as e:
        return [("steps present", False, e)]
    res.append(("revision is resolved after the source checkout and before the build", i_co < i_rev < i_build, names))
    rev_step = steps[i_rev]
    res.append(("step id is source_rev", rev_step.get("id") == "source_rev", rev_step.get("id")))
    labels = steps[i_build]["with"].get("labels", "")
    res.append(("label uses the resolved revision output",
                "org.opencontainers.image.revision=${{ steps.source_rev.outputs.revision }}" in labels, labels))
    res.append(("label never reads the input ref", "inputs.git_ref" not in labels and "github.ref" not in labels, labels))
    script = rev_step["run"]

    with tempfile.TemporaryDirectory() as d:
        repo = pathlib.Path(d) / "src"
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / "f").write_text("1")
        git(repo, "add", "f")
        git(repo, "commit", "-q", "-m", "one")
        first = git(repo, "rev-parse", "HEAD")
        (repo / "f").write_text("2")
        git(repo, "commit", "-q", "-am", "two")
        head = git(repo, "rev-parse", "HEAD")
        # A moving tag and a branch pointing at the OLD commit: the input ref is not the build.
        git(repo, "tag", "4.154.0", first)
        rc, out, log = run_script(script, repo, {"GIT_REF": "4.154.0", "INPUT_GIT_REF": "4.154.0"})
        res.append(("label is the checked-out HEAD, not the ref", rc == 0 and out.strip() == f"revision={head}" and head != first, (rc, out, log)))
        res.append(("revision is 40 lowercase hex", re.fullmatch(r"revision=[0-9a-f]{40}", out.strip()) is not None, out))

        # Detached HEAD at a tag still resolves the commit.
        git(repo, "checkout", "-q", "--detach", "4.154.0")
        rc, out, _ = run_script(script, repo)
        res.append(("detached HEAD resolves its commit", rc == 0 and out.strip() == f"revision={first}", (rc, out)))

        # Not a git checkout: refuse, write nothing.
        plain = pathlib.Path(d) / "plain"
        plain.mkdir()
        rc, out, _ = run_script(script, plain)
        res.append(("no git checkout refuses the build and writes no label", rc != 0 and out.strip() == "", (rc, out)))

        # A repo with no commit (unborn HEAD): refuse as well.
        empty = pathlib.Path(d) / "empty"
        empty.mkdir()
        git(empty, "init", "-q")
        rc, out, _ = run_script(script, empty)
        res.append(("unborn HEAD refuses the build and writes no label", rc != 0 and out.strip() == "", (rc, out)))
        # A git that answers with something that is not a full commit id (short
        # id, ref name, uppercase): refuse, never stamp it.
        fake = pathlib.Path(d) / "fakebin"
        fake.mkdir()
        for bad in ("deadbeef", "refs/tags/4.154.0", head.upper(), head + "0"):
            (fake / "git").write_text(f"#!/bin/bash\necho '{bad}'\n")
            (fake / "git").chmod(0o755)
            rc, out, _ = run_script(script, repo, {"PATH": f"{fake}:{os.environ['PATH']}"})
            res.append((f"a non-40-hex answer ({bad[:12]}) refuses the build", rc != 0 and out.strip() == "", (rc, out)))
    return res


MUTANTS = [
    ("revision taken from the input ref", "rev=$(git rev-parse --verify HEAD^{commit})", 'rev="${GIT_REF:-}"'),
    ("hex shape check dropped", "if ! printf '%s' \"$rev\" | grep -Eq '^[0-9a-f]{40}$'; then", "if false; then"),
    ("label reads the input ref", "org.opencontainers.image.revision=${{ steps.source_rev.outputs.revision }}",
     "org.opencontainers.image.revision=${{ inputs.git_ref }}"),
]


def main():
    text = WF.read_text()
    for name, ok, detail in judge(text):
        check(name, ok, detail)
    for name, old, new in MUTANTS:
        if text.count(old) != 1:
            check(f"mutant anchor: {name}", False, f"found {text.count(old)}")
            continue
        red = [n for n, ok, _ in judge(text.replace(old, new)) if not ok]
        check(f"mutant turns the suite red: {name}", bool(red), "no case failed")
    if failures:
        print("\nFAILURES:")
        print("\n".join(failures))
        sys.exit(1)
    print("\nall build-image revision label checks passed")


main()
