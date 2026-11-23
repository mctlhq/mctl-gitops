"""release-gate.py diff: a push is judged by the content it changed.

Policy is read from the parent commit. Converged input is green, deliberate
mutations are red, and a read that fails is unknown (exit 7), never green.
Also runs the workflow's diff step the way GitHub runs it.
"""
import os
import pathlib
import re
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


def repo_with(mutate=None, script=SCRIPT, pre=None):
    """Parent commit = the real gate + gated files (+ pre); head = parent + mutate."""
    d = pathlib.Path(tempfile.mkdtemp())
    git(d, "init", "-q")
    gate = yaml.safe_load((ROOT / GATE).read_text())
    files = [GATE] + [p for g in gate["gates"] for p in g["paths"]] + [h["file"] for h in gate["version_holds"]]
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, d / f)
    if pre:
        pre(d, gate["gates"][0]["paths"])
    git(d, "add", "-A")
    git(d, "commit", "-qm", "parent")
    base = git(d, "rev-parse", "HEAD")
    if mutate:
        mutate(d, gate["gates"][0]["paths"])
    git(d, "add", "-A")
    git(d, "commit", "-qm", "head", "--allow-empty")
    return d, base, git(d, "rev-parse", "HEAD")


def diff(d, base, head, script=SCRIPT):
    r = subprocess.run([sys.executable, str(script), "--root", str(d), "diff", "--base", base, "--head", head],
                       capture_output=True, text=True)
    return r.returncode, r.stderr


def retag(tmp, paths, tag="9.9.9"):
    for p in paths:  # the whole group moves together, as a real bump does
        v = tmp / p
        old = yaml.safe_load(v.read_text())["image"]["tag"]
        v.write_text(v.read_text().replace(f'tag: "{old}"', f'tag: "{tag}"'))


NEW_REF_TAG = "1.118.0"
NEW_DIGEST = "sha256:" + "c" * 64
NEW_REF = f"ghcr.io/mctlhq/mctl-agents:{NEW_REF_TAG}@{NEW_DIGEST}"


def set_ref(tmp, paths, ref=NEW_REF):
    v = tmp / paths[0]
    txt = re.sub(r'(\n  ref: )"[^"]*"', lambda m: f'{m.group(1)}"{ref}"', v.read_text(), count=1)
    assert ref in txt
    v.write_text(txt)


def set_image(tmp, paths, tag=NEW_REF_TAG, digest=NEW_DIGEST):
    """Move the whole group to tag; the pre-pulled control file also gets image.digest."""
    retag(tmp, paths, tag)
    if digest:
        v = tmp / paths[0]
        txt = v.read_text().replace(f'  tag: "{tag}"\n', f'  tag: "{tag}"\n  digest: "{digest}"\n', 1)
        assert digest in txt
        v.write_text(txt)


def collapsed(tmp, paths):  # both halves in one commit
    set_ref(tmp, paths)
    set_image(tmp, paths)


def digest_only(tmp, paths):
    v = tmp / paths[0]
    v.write_text(v.read_text().replace('  tag: "1.117.0"\n', f'  tag: "1.117.0"\n  digest: "{NEW_DIGEST}"\n', 1))


def pin_in_place(tmp, paths):
    """Legacy shape (tag, no digest) -> settled shape for the SAME image: image.digest := the digest of prepull.ref."""
    v = tmp / paths[0]
    ref_digest = yaml.safe_load(v.read_text())["prepull"]["ref"].split("@", 1)[1]
    txt = v.read_text().replace('  tag: "1.117.0"\n', f'  tag: "1.117.0"\n  digest: "{ref_digest}"\n', 1)
    assert ref_digest in txt.split("prepull:")[0]
    v.write_text(txt)


def step2_wrong_digest(tmp, paths):
    set_image(tmp, paths, digest="sha256:" + "d" * 64)


def step2_to_another_image(tmp, paths):  # a valid "staged" tree for verify, but not the staged ref
    set_image(tmp, paths, tag="1.119.0", digest="sha256:" + "d" * 64)


def step2_and_ref(tmp, paths):
    set_image(tmp, paths)
    set_ref(tmp, paths, f"ghcr.io/mctlhq/mctl-agents:1.119.0@sha256:{'e' * 64}")


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
# the two sanctioned steps of a pre-pulled deploy (F1): each is green, the pair in order is green
d, b, h = repo_with(set_ref)
check("deploy step 1 (only prepull.ref moves) is green", diff(d, b, h)[0] == 0, str(diff(d, b, h)))
d, b, h = repo_with(set_image, pre=set_ref)
check("deploy step 2 (tag + digest settle on the staged ref) is green", diff(d, b, h)[0] == 0, str(diff(d, b, h)))
d, b, h = repo_with(pin_in_place)
check("pinning the current tag to its staged digest (digest alone, equal to prepull.ref) is green",
      diff(d, b, h)[0] == 0, str(diff(d, b, h)))
d, b, h = repo_with(comment_only_policy)
check("a comment-only policy edit is green (compared by content)", diff(d, b, h)[0] == 0, str(diff(d, b, h)))

# mutated: red (6)
for name, m in [("a non-tag key changed", other_key), ("the policy content changed", policy_lowered),
                ("a gated file removed", removed), ("a gated file that no longer parses", broken_head_file),
                ("a partial group bump", partial), ("a tag below the parent floor", below_parent_floor)]:
    d, b, h = repo_with(m)
    rc, err = diff(d, b, h)
    check(f"red: {name}", rc == 6, f"{rc} {err}")

# F1: everything that is not one of those two steps is red
d, b, h = repo_with(lambda t, p: retag(t, p, "99.0.0"))
rc, err = diff(d, b, h)
check("red: a tag-only bump of the pre-pulled file", rc == 6 and "not one step" in err, f"{rc} {err}")
for name, m, pre in [("both halves in one commit", collapsed, None), ("a digest alone that is not the staged digest", digest_only, None),
                     ("step 2 with a digest other than the staged one", step2_wrong_digest, set_ref),
                     ("step 2 to an image other than the staged one", step2_to_another_image, set_ref),
                     ("step 2 that also moves prepull.ref", step2_and_ref, set_ref),
                     ("step 2 without staging first", set_image, None)]:
    d, b, h = repo_with(m, pre=pre)
    rc, err = diff(d, b, h)
    check(f"red: {name}", rc == 6, f"{rc} {err}")

# F1 mutation evidence: with each rule of the step classifier broken, one of the
# cases above must flip. Each mutant is a copy of the script with one edit.
SRC = SCRIPT.read_text()
STEP_MUTANTS = {
    # name: (old, new, scenario that must flip, wanted rc under the mutant for a "caught" verdict is the opposite)
    "classifier accepts every change": ("    if not (ct or cd or cr):\n        return None", "    return None", collapsed, None, 6),
    "step 1 not understood (strips only image.tag)": ("if _without_deploy_keys(old) != _without_deploy_keys(new):", "if _without_tag(old) != _without_tag(new):", set_ref, None, 0),
    "step 2 not understood": ("    if cd and not cr:", "    if False:", set_image, set_ref, 0),
    "pin in place not understood (needs the tag to move too)": ("    if cd and not cr:", "    if ct and cd and not cr:", pin_in_place, None, 0),
    "step 2 need not settle on the staged ref": ("        if m and m.group(1) == str(nt) and m.group(2) == str(nd):\n            return None", "        if m:\n            return None", step2_to_another_image, set_ref, 6),
}
for name, (old, new, scen, pre, want_green_rc) in STEP_MUTANTS.items():
    check(f"mutant anchor exists: {name}", SRC.count(old) == 1, f"count={SRC.count(old)}")
    with tempfile.TemporaryDirectory() as t:
        m = pathlib.Path(t) / "release-gate.py"
        m.write_text(SRC.replace(old, new))
        d, b, h = repo_with(scen, pre=pre)
        real = diff(d, b, h)[0]
        mut = diff(d, b, h, m)[0]
        check(f"mutant killed: {name}", real != mut, f"real={real} mutant={mut}")

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
