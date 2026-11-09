"""release-gate.py diff: a push is judged by the content it changed.

Policy is read from the parent commit. Converged input is green, deliberate
mutations are red, and a read that fails is unknown (exit 7), never green.
Also runs the workflow's diff step the way GitHub runs it.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/release-gate.py"
GATE = "platform-gitops/release-gates.yaml"
WF = yaml.safe_load((ROOT / ".github/workflows/release-gate-watch.yml").read_text())
STEP = [s for s in WF["jobs"]["verify"]["steps"] if s.get("id") == "diff"][0]
failures = []
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, env=GIT_ENV, check=True).stdout.strip()


def repo_with(mutate=None, script=SCRIPT):
    """Parent commit = the real gate + gated files; head = parent + mutate."""
    d = pathlib.Path(tempfile.mkdtemp())
    git(d, "init", "-q")
    gate = yaml.safe_load((ROOT / GATE).read_text())
    files = [GATE] + [p for g in gate["gates"] for p in g["paths"]]
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, d / f)
    git(d, "add", "-A")
    git(d, "commit", "-qm", "parent")
    base = git(d, "rev-parse", "HEAD")
    if mutate:
        mutate(d, gate["gates"][0]["paths"])
    git(d, "add", "-A")
    git(d, "commit", "-qm", "head", "--allow-empty")
    return d, base, git(d, "rev-parse", "HEAD")


def diff(d, base, head):
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(d), "diff", "--base", base, "--head", head],
                       capture_output=True, text=True)
    return r.returncode, r.stderr


def retag(tmp, paths, tag="9.9.9"):
    for p in paths:  # the whole group moves together, as a real bump does
        v = tmp / p
        old = yaml.safe_load(v.read_text())["image"]["tag"]
        v.write_text(v.read_text().replace(f'tag: "{old}"', f'tag: "{tag}"'))


def other_key(tmp, paths):
    retag(tmp, paths)
    (tmp / paths[0]).write_text((tmp / paths[0]).read_text() + "\nextraKey: changed\n")


def policy_lowered(tmp, paths):
    g = tmp / GATE
    doc = yaml.safe_load(g.read_text())
    doc["gates"][0]["min_tag"] = "0.0.1"
    g.write_text(yaml.safe_dump(doc))
    (tmp / paths[0]).write_text((tmp / paths[0]).read_text().replace("image:", "image:", 1))


def below_parent_floor(tmp, paths):
    retag(tmp, paths, "0.0.1")


def removed(tmp, paths):
    (tmp / paths[1]).unlink()


def broken_head_file(tmp, paths):
    (tmp / paths[0]).write_text(": : :\n\t[")


def partial(tmp, paths):
    retag(tmp, paths[:1])


def comment_only_policy(tmp, paths):
    g = tmp / GATE
    g.write_text(g.read_text() + "\n# a comment\n")


# converged
d, b, h = repo_with()
check("an unchanged tree is green", diff(d, b, h)[0] == 0)
d, b, h = repo_with(lambda t, p: retag(t, p, "99.0.0"))
check("a whole-group tag bump is green", diff(d, b, h)[0] == 0, str(diff(d, b, h)))
d, b, h = repo_with(comment_only_policy)
check("a comment-only policy edit is green (compared by content)", diff(d, b, h)[0] == 0, str(diff(d, b, h)))

# mutated: red (6)
for name, m in [("a non-tag key changed", other_key), ("the policy content changed", policy_lowered),
                ("a gated file removed", removed), ("a gated file that no longer parses", broken_head_file),
                ("a partial group bump", partial), ("a tag below the parent floor", below_parent_floor)]:
    d, b, h = repo_with(m)
    rc, err = diff(d, b, h)
    check(f"red: {name}", rc == 6, f"{rc} {err}")

# the policy is the parent's: a head that rewrites the policy to accept itself is still red
def self_approving(tmp, paths):
    below_parent_floor(tmp, paths)
    g = tmp / GATE
    doc = yaml.safe_load(g.read_text())
    doc["gates"][0]["min_tag"] = "0.0.1"
    g.write_text(yaml.safe_dump(doc))


d, b, h = repo_with(self_approving)
rc, err = diff(d, b, h)
check("red: the head cannot loosen the policy it is judged by", rc == 6, f"{rc} {err}")

# read failures: unknown (7), never green
d, b, h = repo_with()
check("unknown: unreadable head revision", diff(d, b, "0" * 40)[0] == 7)
check("unknown: unreadable base revision", diff(d, "0" * 40, h)[0] == 7)
check("unknown: not a git repository", diff(pathlib.Path(tempfile.mkdtemp()), b, h)[0] == 7)
d, b, h = repo_with()
(d / ".git/objects").rename(d / ".git/objects.gone")
check("unknown: object store unreadable", diff(d, b, h)[0] == 7)


def parent_policy_gone(tmp, paths):
    pass


d = pathlib.Path(tempfile.mkdtemp())
git(d, "init", "-q")
(d / "x").write_text("x")
git(d, "add", "-A")
git(d, "commit", "-qm", "no policy")
sha = git(d, "rev-parse", "HEAD")
check("unknown: the parent has no policy to judge against", diff(d, sha, sha)[0] == 7)

# the workflow step, run as bash -e; the state it writes is what the alerts key on
RUN = STEP["run"]


def step(d, base, head, script=RUN):
    out = d / "gh_output"
    out.write_text("")
    # step runs from the checkout; use the real script against that repo
    sh = d / "step.sh"
    sh.write_text(script.replace("scripts/release-gate.py", f"{SCRIPT} --root {d}"))
    r = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", str(sh)], cwd=d, capture_output=True,
                       text=True, env={**os.environ, "BEFORE": base, "SHA": head, "GITHUB_OUTPUT": str(out)})
    return r.returncode, out.read_text()


d, b, h = repo_with()
rc, out = step(d, b, h)
check("step: converged push is green with no state", rc == 0 and "state=" not in out, f"{rc} {out}")
d, b, h = repo_with(other_key)
rc, out = step(d, b, h)
check("step: changed content writes state=violated", rc == 6 and "state=violated" in out, f"{rc} {out}")
rc, out = step(d, b, "0" * 40)
check("step: a failed read writes state=unknown and is red", rc == 7 and "state=unknown" in out, f"{rc} {out}")
rc, out = step(d, b, h, RUN.replace("|| rc=$?", "\nrc=$?"))
check("mutant caught: a bare call loses the state under bash -e", "state=violated" not in out, out)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f[:300])
    sys.exit(1)
print("all checks passed")
