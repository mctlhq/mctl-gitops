"""Supersede logic of the release-bump PR route, run for real (mctlhq/mctl-gitops#2543).

The block between `semver_lt() {` and `done <<< "$others"` is cut out of the
"Open the release-bump pull request" step of release-deploy.yaml and
gitops-bump.yaml and run under bash with a fake gh. The fake gh answers
`pr list` by running the real --jq filter over canned JSON with jq, so the
author, prefix and tag-shape filters are exercised too. Each named mutation of
the block must turn at least one case red. Plain script:
`python3 tests/test_release_bump_supersede.py`.
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows"
APP = "app/mctl-gitops-pr"
failures = []


def block(fn):
    doc = yaml.safe_load((WF / fn).read_text())
    run = [s for s in doc["jobs"]["publish-pr"]["steps"] if s.get("id") == "open_pr"][0]["run"]
    a = run.index("          semver_lt() {") if "          semver_lt() {" in run else run.index("semver_lt() {")
    b = run.index('done <<< "$others"') + len('done <<< "$others"')
    return run[a:b]


def pr(n, tag, service="mctl-api", author=APP):
    return {"number": n, "headRefName": f"release-bump/{service}-{tag}", "author": {"login": author}}


def run_block(text, listing, *, new_tag, pr_no=50, service="mctl-api", list_ok=True):
    """Returns (rc, closed PR numbers, stderr+stdout)."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "list.json").write_text(json.dumps(listing))
        gh = d / "bin" / "gh"
        gh.parent.mkdir()
        gh.write_text(
            "#!/bin/bash\n"
            'if [[ "$1 $2" == "pr list" ]]; then\n'
            f'  {"" if list_ok else "exit 1 #"}\n'
            '  while [[ $# -gt 0 ]]; do [[ "$1" == "--jq" ]] && { expr="$2"; break; }; shift; done\n'
            f'  jq -r "$expr" < "{d}/list.json"\n'
            'elif [[ "$1 $2" == "pr close" ]]; then\n'
            f'  echo "$3" >> "{d}/closed"\n'
            "else exit 9; fi\n")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        script = f'set -euo pipefail\npr={pr_no}\n{text}\n'
        env = {"PATH": f"{gh.parent}:{os.environ['PATH']}", "REPO": "o/r", "SERVICE": service, "NEW_TAG": new_tag, "HOME": str(d)}
        r = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        closed = (d / "closed").read_text().split() if (d / "closed").exists() else []
        return r.returncode, closed, r.stdout + r.stderr


def cases(text):
    out = []

    def case(name, got, want):
        out.append((name, got == want, f"got {got}, want {want}"))

    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0")], new_tag="1.3.0")
    case("an older bump of the same service is closed, own PR is kept", (rc, closed), (0, ["41"]))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(60, "1.4.0")], new_tag="1.3.0")
    case("a NEWER open bump closes this one and fails the run", (rc, closed), (1, ["50"]))
    rc, closed, _ = run_block(text, [pr(50, "1.10.0"), pr(41, "1.9.0")], new_tag="1.10.0")
    case("ordering is numeric, 1.9.0 < 1.10.0", (rc, closed), (0, ["41"]))
    rc, closed, _ = run_block(text, [pr(50, "1.9.0"), pr(41, "1.10.0")], new_tag="1.9.0")
    case("ordering is numeric, 1.10.0 is newer than 1.9.0", (rc, closed), (1, ["50"]))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0", author="mashkovd")], new_tag="1.3.0")
    case("a bump by another author is never closed", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0", author="mctl-gitops-pr[bot]")], new_tag="1.3.0")
    case("the App's REST login (mctl-gitops-pr[bot]) is recognised", (rc, closed), (0, ["41"]))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0", author="evil-mctl-gitops-pr[bot]")], new_tag="1.3.0")
    case("a look-alike bot login is never closed", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0", author="app/other-app")], new_tag="1.3.0")
    case("a bump by another App is never closed", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0", service="foo"), pr(41, "1.0.0", service="foo-2")], new_tag="1.3.0", service="foo")
    case("another service named <service>-<digit> is never closed", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0", service="foo"), pr(41, "9.0.0", service="foo-2")], new_tag="1.3.0", service="foo")
    case("another service's newer bump does not fail this run", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "abc"), pr(41, "1.2.0")], new_tag="abc")
    case("a tag that cannot be ordered closes nothing", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0-rc1")], new_tag="1.3.0")
    case("an open bump with a non-semver suffix is left alone", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0")], new_tag="1.3.0")
    case("no other bump: nothing closed", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.3.0-x")], new_tag="1.3.0")
    case("equal-looking but different suffix is left alone", (rc, closed), (0, []))
    rc, closed, _ = run_block(text, [pr(50, "1.10.0"), pr(41, "1.08.0")], new_tag="1.10.0")
    case("a zero-padded component is read as decimal", (rc, closed), (0, ["41"]))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0")], new_tag="1.3.0", list_ok=False)
    case("a failed listing fails the job and closes nothing", (rc != 0, closed), (True, []))
    rc, closed, _ = run_block(text, [pr(50, "1.3.0"), pr(41, "1.2.0"), pr(42, "1.2.5"), pr(43, "1.1.0")], new_tag="1.3.0")
    case("every older bump is closed", (rc, sorted(closed)), (0, ["41", "42", "43"]))
    return out


IND = "    "  # indentation of the elif body after YAML strips the block scalar
MUTANTS = [
    ("older/newer inverted", "(( 10#${a[i]} < 10#${b[i]} )) && return 0", "(( 10#${a[i]} > 10#${b[i]} )) && return 0"),
    ("lexical-ish compare drops the numeric base", "10#${a[i]} < 10#${b[i]}", "${a[i]} < ${b[i]}"),
    ("minor and patch ignored", "for i in 0 1 2; do", "for i in 0; do"),
    ("newer open bump no longer fails the run", [('is not newer"\n' + IND + 'exit 1', 'is not newer"\n' + IND + 'true')]),
    ("author filter dropped", 'select(.author.login | test("^(app/)?mctl-gitops-pr(\\\\[bot\\\\])?$")) | ', ""),
    ("REST [bot] login no longer recognised", '(\\\\[bot\\\\])?$', '$'),
    ("tag-shape filter dropped and unorderable closes", [(' and ($h[($p | length):] | test("^[0-9]+\\\\.[0-9]+\\\\.[0-9]+$"))', ""), ('if [[ "$rc" == 0 ]]; then', 'if [[ "$rc" != 1 ]]; then')]),
    ("own PR may be closed", '[[ -n "$n" && "$n" != "$pr" ]] || continue', '[[ -n "$n" ]] || continue'),
    ("unorderable tag closes anyway", 'if [[ "$rc" == 0 ]]; then', 'if [[ "$rc" != 1 ]]; then'),
    ("listing failure swallowed", [("others=$(gh pr list", 'gh() { command gh "$@" || true; }; others=$(gh pr list')]),
]


def judge(text):
    return cases(text)


def main():
    texts = {fn: block(fn) for fn in ("release-deploy.yaml", "gitops-bump.yaml")}
    for fn, text in texts.items():
        for name, ok, detail in judge(text):
            print(("ok   " if ok else "FAIL ") + f"{fn}: {name}")
            if not ok:
                failures.append(f"{fn}: {name}: {detail}")
    for fn, text in texts.items():
        for name, *spec in MUTANTS:
            pairs = spec[0] if len(spec) == 1 else [(spec[0], spec[1])]
            mutated, bad = text, False
            for old, new in pairs:
                if mutated.count(old) != 1:
                    failures.append(f"{fn}: mutant anchor {name}: found {mutated.count(old)}")
                    print(f"FAIL {fn}: mutant anchor {name}")
                    bad = True
                    break
                mutated = mutated.replace(old, new)
            if bad:
                continue
            red = [n for n, ok, _ in judge(mutated) if not ok]
            print(("ok   " if red else "FAIL ") + f"{fn}: mutant killed: {name}")
            if not red:
                failures.append(f"{fn}: mutant survives: {name}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)
    print("all release-bump supersede checks passed")


main()
