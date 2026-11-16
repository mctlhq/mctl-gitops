"""scripts/release-bump-digest.py (mctlhq/mctl-gitops#2652).

Each case builds a throwaway git repository holding a values file before the
bump, writes the file as the tag-bump step leaves it, runs the digest step on
the changed-files handoff and checks the exit code and the file. Every accepted
result is also fed, as a git diff, to scripts/release-bump-diff-guard.py, which
must accept it: the writer and the guard agree on the one shape a digest takes.
Each named mutation of the script must turn at least one case red.
Plain script: `python3 tests/test_release_bump_digest.py`.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/release-bump-digest.py").read_text()
GUARD = ROOT / "scripts/release-bump-diff-guard.py"
SVC = "platform-gitops/services/labs/foo/values.yaml"
BOOT = "platform-gitops/bootstrap/templates/mctl-platform/foo.yaml"
CWFT = "platform-gitops/argo-workflows/cluster-templates/cwft-foo.yaml"
IMG = "ghcr.io/mctlhq/foo"
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "a" * 64
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def values(tag, digest=None, worker="1.0.0", extra="", ind="  "):
    d = f'{ind}digest: "{digest}"\n' if digest else ""
    return (f"image:\n{ind}repository: {IMG}\n{ind}tag: \"{tag}\"\n{d}{extra}"
            f"worker:\n{ind}repository: {IMG}-worker\n{ind}tag: \"{worker}\"\n")


def DOTTED(tag, digest=None):
    """foo.bar is bumped; fooxbar, which an unescaped '.' would also match, is not."""
    d = f'  digest: "{digest}"\n' if digest else ""
    return (f'other:\n  repository: {IMG}xbar\n  tag: "1.0.0"\n'
            f'image:\n  repository: {IMG}.bar\n  tag: "{tag}"\n{d}')


def git(d, *args):
    return subprocess.run(["git", *args], cwd=d, env=ENV, capture_output=True, text=True)


def run(script_text, before, after, digest, tag="1.1.0", image=IMG, changed=None):
    """before/after: {path: text}. Returns (exit code, {path: text}, guard exit or None)."""
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "s.py").write_text(script_text)
    git(d, "init", "-q")
    for p, t in before.items():
        (d / p).parent.mkdir(parents=True, exist_ok=True)
        (d / p).write_text(t)
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    for p, t in after.items():
        (d / p).write_text(t)
    hand = d / "changed.txt"
    hand.write_text("".join(f"{p}\n" for p in (changed if changed is not None else after)))
    args = [sys.executable, "s.py", "--image", image, "--tag", tag, "--changed-files", str(hand)]
    if digest is not None:
        args += ["--digest", digest]
    r = subprocess.run(args, cwd=d, capture_output=True, text=True)
    files = {p: (d / p).read_text() for p in before}
    guard = None
    if r.returncode == 0:
        diff = git(d, "diff", "--", *before).stdout
        if diff:
            guard = subprocess.run([sys.executable, str(GUARD)], input=diff.encode(), capture_output=True).returncode
    return r.returncode, files, guard


# (name, before, after, digest, expected code, expected {path: text} or None, extra kwargs)
CASES = [
    ("introduces a digest under the bumped tag",
     {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, D1, 0, {SVC: values("1.1.0", D1)}, {}),
    ("replaces the digest that moves with the tag",
     {SVC: values("1.0.0", D1)}, {SVC: values("1.1.0", D1)}, D2, 0, {SVC: values("1.1.0", D2)}, {}),
    ("keeps the tag's indentation",
     {SVC: values("1.0.0", ind="    ")}, {SVC: values("1.1.0", ind="    ")}, D1, 0,
     {SVC: values("1.1.0", D1, ind="    ")}, {}),
    ("no digest and none pinned: untouched",
     {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, None, 0, {SVC: values("1.1.0")}, {}),
    ("empty digest counts as none",
     {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, "", 0, {SVC: values("1.1.0")}, {}),
    ("leaves an unbumped sibling image alone",
     {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, D1, 0, {SVC: values("1.1.0", D1)}, {}),
    ("CWFT outside services: untouched",
     {CWFT: f"image: {IMG}:1.0.0\n"}, {CWFT: f"image: {IMG}:1.1.0\n"}, D1, 0, {CWFT: f"image: {IMG}:1.1.0\n"}, {}),
    ("bootstrap template with the same block shape: untouched",
     {BOOT: values("1.0.0")}, {BOOT: values("1.1.0")}, D1, 0, {BOOT: values("1.1.0")}, {}),
    ("only files in the handoff are edited",
     {SVC: values("1.1.0")}, {SVC: values("1.1.0")}, D1, 0, {SVC: values("1.1.0")}, {"changed": []}),
    ("a dotted image name is matched literally",
     {SVC: DOTTED("1.0.0")}, {SVC: DOTTED("1.1.0")}, D1, 0, {SVC: DOTTED("1.1.0", D1)}, {"image": f"{IMG}.bar"}),

    ("refuses to move the tag under a pinned digest",
     {SVC: values("1.0.0", D1)}, {SVC: values("1.1.0", D1)}, None, 8, None, {}),
    ("refuses a digest elsewhere in the block",
     {SVC: values("1.0.0", extra="  pullPolicy: Always\n").replace("worker:", f'  digest: "{D1}"\nworker:')},
     {SVC: values("1.1.0", extra="  pullPolicy: Always\n").replace("worker:", f'  digest: "{D1}"\nworker:')},
     D2, 9, None, {}),
    ("refuses a block whose tag is not the bumped one",
     {SVC: values("1.0.0")}, {SVC: values("1.0.0")}, D1, 9, None, {}),
    ("refuses a short digest", {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, "sha256:" + "1" * 63, 2, None, {}),
    ("refuses an uppercase digest", {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, "sha256:" + "A" * 64, 2, None, {}),
    ("refuses a digest carrying a newline",
     {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, D1 + "\nprivileged: true", 2, None, {}),
    ("refuses an image name that is not one", {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, D1, 2, None,
     {"image": "ghcr.io/mctlhq/foo\nx"}),
    ("refuses a '..' path", {SVC: values("1.0.0")}, {SVC: values("1.1.0")}, D1, 2, None,
     {"changed": ["platform-gitops/services/../services/labs/foo/values.yaml"]}),
]

MUTANTS = [
    ("no stale-digest refusal", 'if found:\n                fail(8', 'if False:\n                fail(8'),
    ("digest above the tag", "inserts.append((i + 2,", "inserts.append((i + 1,"),
    ("indentation dropped", "new_line = f'{ind}digest:", "new_line = f'  digest:"),
    ("digest not validated", "if digest and not DIGEST_RE.fullmatch(digest):", "if False:"),
    ("services prefix ignored", "if not norm.startswith(SERVICES_PREFIX):\n            continue",
     "if False:\n            continue"),
    ("existing digest duplicated", "out[i + 2] = new_line", "inserts.append((i + 2, new_line))"),
    ("bumped tag not checked", 'if m.group("tag") != tag:', "if False:"),
    ("misplaced digest not checked", "if found and found[0] != i + 2:", "if False:"),
    ("image name unescaped", 'repository:\\s*" + re.escape(image)', 'repository:\\s*" + image'),
    ("image name prefix match", 're.escape(image) + r"$"', "re.escape(image)"),
    ("handoff ignored", "files = [p.strip() for p in fp if p.strip()]",
     "files = [p.strip() for p in fp if p.strip()] or ['platform-gitops/services/labs/foo/values.yaml']"),
    ("image name not validated", 'if not re.fullmatch(r"[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)+", a.image):',
     "if False:"),
    ("'..' allowed", "or \"..\" in path.split(\"/\")", "or False"),
]


def check(script_text):
    bad = []
    for name, before, after, digest, code, want, kw in CASES:
        image = kw.get("image", IMG)
        got, files, guard = run(script_text, before, after, digest, image=image, changed=kw.get("changed"))
        if got != code:
            bad.append(f"{name}: exit {got}, want {code}")
        elif code == 0:
            if want is not None and files != want:
                bad.append(f"{name}: file differs")
            if guard not in (None, 0):
                bad.append(f"{name}: guard refused the result (exit {guard})")
    return bad


def main():
    failures = check(SCRIPT)
    for f in failures:
        print("FAIL", f)
    print(f"{len(CASES) - len(failures)}/{len(CASES)} cases ok")
    survivors = []
    for name, old, new in MUTANTS:
        if SCRIPT.count(old) != 1:
            survivors.append(f"{name}: anchor not found exactly once")
            continue
        if not check(SCRIPT.replace(old, new)):
            survivors.append(name)
    for s in survivors:
        print("MUTANT SURVIVED", s)
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} mutants killed")
    sys.exit(1 if failures or survivors else 0)


if __name__ == "__main__":
    main()
