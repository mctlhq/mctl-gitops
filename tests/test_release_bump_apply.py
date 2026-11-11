"""scripts/release-bump-apply.sh against real git (mctlhq/mctl-gitops#2543).

Builds a throwaway repository, makes bump patches from one base, and applies
them one after the other the way two close releases of one image do. Each named
mutation of the script must turn at least one case red. Plain script:
`python3 tests/test_release_bump_apply.py`.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/release-bump-apply.sh").read_text()
GUARD = (ROOT / "scripts/release-bump-diff-guard.py").read_text()
FILE = "platform-gitops/services/labs/foo/values.yaml"
failures = []


def sh(cwd, *args, check=True, input=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, input=input)
    if check and r.returncode:
        raise RuntimeError(f"{args}: {r.stderr}")
    return r


def content(tag, other="keep", worker="1.0.0"):
    return (f'server:\n  repository: ghcr.io/mctlhq/foo\n  tag: "{tag}"\n'
            f'worker:\n  repository: ghcr.io/mctlhq/foo-worker\n  tag: "{worker}"\nconfig:\n  other: {other}\n')


def setup(script_text):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "scripts").mkdir()
    (d / "scripts/release-bump-apply.sh").write_text(script_text)
    (d / "scripts/release-bump-diff-guard.py").write_text(GUARD)
    (d / FILE).parent.mkdir(parents=True)
    (d / FILE).write_text(content("1.1.0"))
    sh(d, "git", "init", "-q", "-b", "main")
    sh(d, "git", "add", "-A")
    sh(d, "git", "commit", "-q", "-m", "base")
    return d


def make_patch(d, tag, name, worker="1.0.0"):
    """A bump commit on top of the current HEAD, written as a patch, then dropped."""
    base = sh(d, "git", "rev-parse", "HEAD").stdout.strip()
    (d / FILE).write_text(content(tag, worker=worker))
    sh(d, "git", "add", FILE)
    sh(d, "git", "commit", "-q", "-m", f"bump {tag}")
    p = d / f"{name}.patch"
    p.write_text(sh(d, "git", "format-patch", "-1", "--stdout").stdout)
    sh(d, "git", "reset", "-q", "--hard", base)
    return p


def apply(d, patch):
    r = sh(d, "bash", "scripts/release-bump-apply.sh", str(patch), check=False)
    return r.returncode, r.stdout + r.stderr


def tag_of(d):
    return (d / FILE).read_text().split('tag: "')[1].split('"')[0]


def worker_of(d):
    return (d / FILE).read_text().split('tag: "')[2].split('"')[0]


def cases(script_text):
    out = []

    def case(name, got, want):
        out.append((name, got == want, f"got {got}, want {want}"))

    # 1. clean apply
    d = setup(script_text)
    p = make_patch(d, "1.2.0", "a")
    rc, _ = apply(d, p)
    case("a clean patch applies", (rc, tag_of(d)), (0, "1.2.0"))

    # 2. two close releases built from the same base: the second conflicts, the newer wins
    d = setup(script_text)
    a, b = make_patch(d, "1.2.0", "a"), make_patch(d, "1.3.0", "b")
    rc1, _ = apply(d, a)
    rc2, log = apply(d, b)
    case("two bumps from one base land in order, newer tag wins", (rc1, rc2, tag_of(d)), (0, 0, "1.3.0"))
    case("the resolved result is a clean commit over main",
         (sh(d, "git", "status", "--porcelain", "--untracked-files=no").stdout.strip(), sh(d, "git", "rev-list", "--count", "HEAD").stdout.strip()), ("", "3"))

    # 3. an older release that lost the race must fail and leave main's tag alone
    d = setup(script_text)
    a, b = make_patch(d, "1.2.0", "a"), make_patch(d, "1.3.0", "b")
    apply(d, b)
    head = sh(d, "git", "rev-parse", "HEAD").stdout.strip()
    rc, _ = apply(d, a)
    case("an older release that lost the race is refused", rc != 0, True)
    sh(d, "git", "am", "--abort", check=False)
    sh(d, "git", "reset", "-q", "--hard", head)
    case("main still carries the newer tag", tag_of(d), "1.3.0")

    # 4. an unrelated line changed on main: taking the patch side would revert it, so refuse
    d = setup(script_text)
    a = make_patch(d, "1.2.0", "a")
    (d / FILE).write_text(content("1.1.5", other="changed-on-main"))
    sh(d, "git", "commit", "-qam", "main moved")
    rc, log = apply(d, a)
    case("a conflict that would revert an unrelated line is refused", rc != 0, True)

    # 4b. the neighbouring image line was moved on main; the patch side would put it back
    #     (a FORWARD move for that line, so only the same-lines check can see it)
    d = setup(script_text)
    a = make_patch(d, "1.2.0", "a")
    (d / FILE).write_text(content("1.1.5", worker="0.9.0"))
    sh(d, "git", "commit", "-qam", "main moved the worker")
    rc, log = apply(d, a)
    case("a conflict that would revert a neighbouring image line is refused", rc != 0, True)

    # 4c. tags that cannot be ordered are not resolved
    d = setup(script_text)
    (d / FILE).write_text(content("main-aaa"))
    sh(d, "git", "commit", "-qam", "sha tag")
    a = make_patch(d, "main-bbb", "a")
    (d / FILE).write_text(content("main-ccc"))
    sh(d, "git", "commit", "-qam", "main moved")
    rc, log = apply(d, a)
    case("a conflict between tags that cannot be ordered is refused", rc != 0, True)

    # 5. a patch that does not apply at all is a failure, not a silent skip
    d = setup(script_text)
    bad = d / "bad.patch"
    bad.write_text("not a patch\n")
    rc, _ = apply(d, bad)
    case("a garbage patch fails", rc != 0, True)
    return out


MUTANTS = [
    ("conflict resolved to main's side", "git checkout --theirs", "git checkout --ours"),
    ("guard skipped after resolution", "git diff \"$(git rev-parse HEAD~1)\" HEAD | python3 scripts/release-bump-diff-guard.py --strict-order --same-lines-as \"$patch\" ||", "true ||"),
    ("guard failure ignored", "  exit 1\n}\n", "  true\n}\n"),
    ("am failure treated as success", "if git am --3way \"$patch\"; then\n  exit 0\nfi", "git am --3way \"$patch\" || true\nexit 0"),
    ("neighbouring line may be reverted", ' --strict-order --same-lines-as "$patch"', " --strict-order"),
    ("unorderable tags resolved", "--strict-order --same-lines-as", "--same-lines-as"),
    ("conflict continue skipped", "GIT_EDITOR=true git am --continue", "true"),
]


def main():
    base = cases(SCRIPT)
    for name, ok, detail in base:
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            failures.append(f"{name}: {detail}")
    for name, old, new in MUTANTS:
        if SCRIPT.count(old) != 1:
            failures.append(f"mutant anchor {name}: found {SCRIPT.count(old)}")
            print(f"FAIL mutant anchor {name}")
            continue
        red = [n for n, ok, _ in cases(SCRIPT.replace(old, new)) if not ok]
        print(("ok   " if red else "FAIL ") + f"mutant killed: {name}")
        if not red:
            failures.append(f"mutant survives: {name}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)
    print("all release-bump apply checks passed")


main()
