"""The git push in wft-rollback-service and wft-deploy-service's patch-autoscaling
step retries on a concurrent writer and FAILS after the last attempt (gitops#999).

Both steps used to `git push` once. Two workflows cloning the same commit made
the second push non-fast-forward and the step crashed. The retry loop added
here also removed the `set -e` abort that a bare `git pull --rebase` used to
provide, so the exhaustion check is the part this test pins hardest: a loop
that runs out of attempts must exit non-zero, never fall through as if pushed.

The retry block is taken from each template (from `PUSHED=false` to the
exhaustion check) and run against shims for git and the release gate guard.
"""
import pathlib
import subprocess
import sys
import tempfile

import yaml

D = pathlib.Path("platform-gitops/argo-workflows/cluster-templates")
SITES = [
    ("wft-rollback-service.yaml", "rollback-service-values"),
    ("wft-deploy-service.yaml", "patch-autoscaling-values"),
]
START = "PUSHED=false\n"
END = 'echo "git push failed after 5 attempts" >&2\n  exit 1\nfi\n'

# The shim records every call; GIT_PUSH_FAILS first pushes fail, and a failing
# rebase is selected by REBASE_FAILS=1.
GIT = r"""#!/bin/sh
echo "$*" >> "$CALLS"
case "$1" in
  push)
    n=$(grep -c '^push' "$CALLS")
    [ "$n" -le "${GIT_PUSH_FAILS:-0}" ] && exit 1
    exit 0 ;;
  pull) [ "${REBASE_FAILS:-0}" = 1 ] && exit 1; exit 0 ;;
  rebase) exit 0 ;;
esac
exit 0
"""
GUARD = '#!/bin/sh\necho "guard $*" >> "$CALLS"\n[ "${GUARD_REFUSES:-0}" = 1 ] && exit 1\nexit 0\n'

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def block_of(fname):
    doc = yaml.safe_load((D / fname).read_text())
    src = None
    for t in doc["spec"]["templates"]:
        script = t.get("script", {}).get("source", "")
        if START in script and "git push" in script:
            src = script
    assert src is not None, f"{fname}: no retry block found"
    a = src.index(START)
    b = src.index(END, a) + len(END)
    return src[a:b]


def run(block, **env):
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        shims = root / "shims"
        shims.mkdir()
        (shims / "git").write_text(GIT)
        (shims / "git").chmod(0o755)
        guard = root / "platform-gitops/argo-workflows/scripts/release-gate-guard.sh"
        guard.parent.mkdir(parents=True)
        guard.write_text(GUARD)
        calls = root / "calls.log"
        calls.write_text("")
        full = {"PATH": f"{shims}:/usr/bin:/bin", "CALLS": str(calls), "HOME": str(root)}
        full.update({k: str(v) for k, v in env.items()})
        proc = subprocess.run(["sh", "-c", "set -euo pipefail\n" + block], env=full, cwd=root,
                              capture_output=True, text=True)
        lines = calls.read_text().splitlines()
        count = lambda p: sum(1 for ln in lines if ln.startswith(p))
        return proc, count("push"), count("pull"), count("rebase --abort"), count("guard")


for fname, _ in SITES:
    blk = block_of(fname)
    tag = fname

    proc, push, pull, _, _ = run(blk)
    check(f"{tag}: a clean push is one push and no rebase", proc.returncode == 0 and push == 1 and pull == 0,
          f"{proc.returncode} {push} {pull} {proc.stderr}")

    proc, push, pull, _, guard = run(blk, GIT_PUSH_FAILS=2)
    check(f"{tag}: two rejected pushes are retried, then succeed",
          proc.returncode == 0 and push == 3 and pull == 2, f"{proc.returncode} {push} {pull} {proc.stderr}")
    check(f"{tag}: the outgoing guard runs again on the rebased commits", guard == 3, guard)

    proc, push, pull, _, _ = run(blk, GIT_PUSH_FAILS=99)
    check(f"{tag}: exhaustion fails loudly after 5 attempts",
          proc.returncode != 0 and push == 5 and "failed after 5 attempts" in proc.stderr,
          f"{proc.returncode} {push} {proc.stderr}")

    proc, push, pull, aborts, _ = run(blk, GIT_PUSH_FAILS=99, REBASE_FAILS=1)
    check(f"{tag}: a failing rebase is aborted, not fatal mid-loop, and exhaustion still fails",
          proc.returncode != 0 and push == 5 and aborts == 5, f"{proc.returncode} {push} {aborts} {proc.stderr}")

    proc, push, _, _, _ = run(blk, GUARD_REFUSES=1)
    check(f"{tag}: a guard refusal stops before any push", proc.returncode != 0 and push == 0,
          f"{proc.returncode} {push}")

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
