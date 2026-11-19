"""scripts/rollback-image-ref.py and its wiring in wft-rollback-service.

A rollback that rewrites the tag alone leaves a pinned digest, and so the new
image, running under the old tag's name (the chart renders repository:tag@digest).
Each case builds a throwaway git repository whose history is the sequence of
releases of one values file, runs the script and checks the exit code and the
file. Cases cover both image reference formats: tag only (22 services today)
and tag plus digest (10 today). Every accepted result is also fed, as the
reverse git diff (a rollback is a bump read backwards; the guard refuses a tag
moving backwards), to scripts/release-bump-diff-guard.py, which accepts a tag
move that keeps its digest line: the writer and the guard agree on the shape. Each named
mutation of the script must turn at least one case red.
Plain script: `python3 tests/test_rollback_image_ref.py`.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/rollback-image-ref.py").read_text()
GUARD = ROOT / "scripts/release-bump-diff-guard.py"
TEMPLATE = ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-rollback-service.yaml"
SVC = "platform-gitops/services/labs/foo/values.yaml"
IMG = "ghcr.io/mctlhq/foo"
D1, D2, D3 = ("sha256:" + c * 64 for c in "123")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def values(tag, digest=None, extra="", q='"'):
    d = f'  digest: "{digest}"\n' if digest else ""
    return f"replicaCount: 1\nimage:\n  repository: {IMG}\n  tag: {q}{tag}{q}\n{d}{extra}service:\n  port: 8080\n"


def git(d, *a):
    return subprocess.run(["git", *a], cwd=d, env=ENV, capture_output=True, text=True)


def repo(releases, current=None):
    """releases: oldest first, each a values text. Returns the repo path (HEAD = last)."""
    d = pathlib.Path(tempfile.mkdtemp())
    git(d, "init", "-q")
    (d / SVC).parent.mkdir(parents=True, exist_ok=True)
    for n, text in enumerate(releases):
        (d / SVC).write_text(text)
        git(d, "add", "-A")
        git(d, "commit", "-qm", f"release {n}")
    if current is not None:
        (d / SVC).write_text(current)
    return d


def run(script_text, d, *args, path=SVC):
    (d / "s.py").write_text(script_text)
    r = subprocess.run([sys.executable, "s.py", "--values", path, *args], cwd=d, env=ENV,
                       capture_output=True, text=True)
    return r.returncode, (d / SVC).read_text() if (d / SVC).exists() else None, r.stderr + r.stdout


def guard_accepts(d):
    # The guard refuses a tag that moves backwards, which is what a rollback is.
    # A rollback is a bump read in reverse: commit the rolled-back file, then diff
    # HEAD against the commit it replaced. That is the forward bump whose shape
    # (tag and digest moving together) the guard must accept.
    git(d, "add", SVC)
    if git(d, "diff", "--cached", "--quiet").returncode == 0:
        return True  # nothing changed: already at the target
    git(d, "commit", "-qm", "rollback")
    diff = git(d, "diff", "HEAD", "HEAD~1", "--", SVC).stdout
    return subprocess.run([sys.executable, str(GUARD)], input=diff, text=True,
                          capture_output=True).returncode == 0


def check(name, got, want, fails):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


def cases(script_text):
    fails = []

    def case(name, releases, args, code, expect_text=None, current=None, guard=True):
        d = repo(releases, current)
        before = (d / SVC).read_text()
        rc, after, out = run(script_text, d, *args)
        check(name + " exit", rc, code, fails)
        if code == 0 and expect_text is not None:
            check(name + " file", after, expect_text, fails)
        if code != 0:
            check(name + " file untouched", after, before, fails)
        if code == 0 and guard and not guard_accepts(d):
            fails.append(name + ": result refused by release-bump-diff-guard")

    # --- old format: tag only, no digest anywhere ---
    case("tag-only back", [values("1.0.0"), values("1.1.0"), values("1.2.0")], ["--tag", "1.1.0"], 0, values("1.1.0"))
    case("tag-only unknown tag still moves", [values("1.0.0"), values("1.1.0")], ["--tag", "0.9.0"], 0, values("0.9.0"))
    case("tag-only already there", [values("1.0.0"), values("1.1.0")], ["--tag", "1.1.0"], 0, values("1.1.0"))
    case("tag-only unquoted keeps its style", [values("1.0.0", q=""), values("1.1.0", q="")], ["--tag", "1.0.0"], 0, values("1.0.0", q=""))
    case("tag-only with explicit digest pins it", [values("1.0.0"), values("1.1.0")], ["--tag", "1.0.0", "--digest", D1], 0, values("1.0.0", D1), guard=False)

    # --- new format: tag plus digest ---
    pinned = [values("1.0.0", D1), values("1.1.0", D2), values("1.2.0", D3)]
    case("pinned back, digest from history", pinned, ["--tag", "1.1.0"], 0, values("1.1.0", D2))
    case("pinned back two releases", pinned, ["--tag", "1.0.0"], 0, values("1.0.0", D1))
    case("pinned back with matching digest", pinned, ["--tag", "1.1.0", "--digest", D2], 0, values("1.1.0", D2))
    case("pinned already there", pinned, ["--tag", "1.2.0"], 0, values("1.2.0", D3))
    case("pinned: tag alone is never enough (unknown tag)", pinned, ["--tag", "0.9.0"], 8)
    case("pinned: unknown tag with explicit digest", pinned, ["--tag", "0.9.0", "--digest", D1], 0, values("0.9.0", D1))
    case("pinned: digest that disagrees with history", pinned, ["--tag", "1.1.0", "--digest", D3], 8)
    case("pinned: target released before pinning existed", [values("1.0.0"), values("1.1.0", D2), values("1.2.0", D3)],
         ["--tag", "1.0.0"], 8)
    case("pinned: pre-pin target with explicit digest", [values("1.0.0"), values("1.1.0", D2), values("1.2.0", D3)],
         ["--tag", "1.0.0", "--digest", D1], 0, values("1.0.0", D1))
    case("pinned: tag bound to two digests in history",
         [values("1.0.0", D1), values("1.1.0", D2), values("1.0.0", D3), values("1.2.0", D3)], ["--tag", "1.0.0"], 8)
    case("pinned: same tag twice with same digest is fine",
         [values("1.0.0", D1), values("1.1.0", D2), values("1.0.0", D1), values("1.2.0", D3)], ["--tag", "1.0.0"], 0, values("1.0.0", D1))
    case("pinned: tag-only entry then pinned entry of the same tag uses the digest",
         [values("1.0.0"), values("1.0.0", D1), values("1.1.0", D2)], ["--tag", "1.0.0"], 0, values("1.0.0", D1))
    case("other keys untouched", [values("1.0.0", D1, extra="env:\n  A: b\n"), values("1.1.0", D2, extra="env:\n  A: b\n")],
         ["--tag", "1.0.0"], 0, values("1.0.0", D1, extra="env:\n  A: b\n"))
    # An uncommitted working copy ahead of history is what the workflow never sees, but the
    # digest must come from history, not from the file being replaced.
    case("working copy digest is not reused", [values("1.0.0", D1), values("1.1.0", D2)], ["--tag", "1.0.0"], 0, values("1.0.0", D1))

    # --- shapes that cannot be edited safely: exit 9, file unchanged ---
    two = values("1.1.0", D2) + f"worker:\n  repository: {IMG}-w\n  tag: \"1.1.0\"\n"
    case("two image blocks", [values("1.0.0", D1), two], ["--tag", "1.0.0"], 9)
    case("no image block", ["replicaCount: 1\nservice:\n  port: 1\n"], ["--tag", "1.0.0"], 9)
    far = f"image:\n  repository: {IMG}\n  tag: \"1.1.0\"\n  pullPolicy: Always\n  digest: \"{D2}\"\n"
    case("digest not directly under tag", [far], ["--tag", "1.0.0", "--digest", D1], 9)
    dup = f"image:\n  repository: {IMG}\n  tag: \"1.1.0\"\n  digest: \"{D2}\"\n  digest: \"{D3}\"\n"
    case("two digest keys", [dup], ["--tag", "1.0.0", "--digest", D1], 9)
    bad = f"image:\n  repository: {IMG}\n  tag: \"1.1.0\"\n  digest: \"sha256:xyz\"\n"
    case("digest line not a sha256", [bad], ["--tag", "1.0.0", "--digest", D1], 9)

    # --- history cannot be read ---
    d2 = pathlib.Path(tempfile.mkdtemp())
    git(d2, "init", "-q")
    (d2 / "README").write_text("x")  # a commit exists, but none touches the values file
    git(d2, "add", "-A")
    git(d2, "commit", "-qm", "unrelated")
    (d2 / SVC).parent.mkdir(parents=True, exist_ok=True)
    (d2 / SVC).write_text(values("1.1.0", D2))  # uncommitted: no history at all
    rc, after, out = run(script_text, d2, "--tag", "1.0.0")
    check("no history, pinned: refused", rc, 8, fails)
    check("no history is reported as unreadable history, not as an unused tag", "no history" in out, True, fails)
    check("no history, pinned: untouched", after, values("1.1.0", D2), fails)
    d3 = pathlib.Path(tempfile.mkdtemp())
    git(d3, "init", "-q")
    (d3 / "README").write_text("x")
    git(d3, "add", "-A")
    git(d3, "commit", "-qm", "unrelated")
    (d3 / SVC).parent.mkdir(parents=True, exist_ok=True)
    (d3 / SVC).write_text(values("1.1.0"))
    rc, after, _ = run(script_text, d3, "--tag", "1.0.0")
    check("no history, not pinned: tag alone moves", (rc, after), (0, values("1.0.0")), fails)
    rc, after, _ = run(script_text, d2, "--tag", "1.0.0", "--digest", D1)
    check("no history, explicit digest", (rc, after), (0, values("1.0.0", D1)), fails)

    # --- argument and path validation: exit 2 ---
    base = [values("1.0.0", D1), values("1.1.0", D2)]
    for name, args in (("tag with a pipe", ["--tag", "1.0|x"]), ("empty tag", ["--tag", ""]),
                       ("leading dash tag", ["--tag", "-1"]), ("long tag", ["--tag", "a" * 129]),
                       ("digest uppercase", ["--tag", "1.0.0", "--digest", "sha256:" + "A" * 64]),
                       ("digest short", ["--tag", "1.0.0", "--digest", "sha256:abc"]),
                       ("digest wrong algo", ["--tag", "1.0.0", "--digest", "md5:" + "1" * 64])):
        d = repo(base)
        rc, after, _ = run(script_text, d, *args)
        check(name, rc, 2, fails)
        check(name + " untouched", after, base[-1], fails)
    for name, p in (("absolute path", "/etc/passwd"), ("outside services", "platform-gitops/other/values.yaml"),
                    ("dotdot", "platform-gitops/services/../services/labs/foo/values.yaml")):
        d = repo(base)
        rc, _, _ = run(script_text, d, "--tag", "1.0.0", path=p)
        check(name, rc, 2, fails)
    d = repo(base)
    link = d / "platform-gitops/services/labs/bar"
    link.symlink_to(d / "platform-gitops/services/labs/foo")
    rc, _, _ = run(script_text, d, "--tag", "1.0.0", path="platform-gitops/services/labs/bar/values.yaml")
    check("symlinked path", rc, 2, fails)
    d = repo(base)
    rc, _, _ = run(script_text, d, "--tag", "1.0.0", path="platform-gitops/services/labs/nope/values.yaml")
    check("missing file", rc, 9, fails)
    return fails


# Not listed, by design: the re-read of the edit before it replaces the file
# (`chk`) cannot differ from rewrite() on any input rewrite() gets right, so a
# mutation of it is equivalent; it is a guard against a future bug in rewrite().
# (A repository with no commit at all makes `git log` itself fail, which is the other
# branch of history(); the "no history" message needs a commit that misses the file.)
# The `digests[0] != i + 2` check is shadowed by the sha256 line check that
# follows it; both refuse with exit 9.
MUTATIONS = {
    "rewrite ignores the digest": ('    if digest:\n        line = f\'{ind}digest: "{digest}"\'', '    if False:\n        line = f\'{ind}digest: "{digest}"\''),
    "no refusal for a pinned file without a digest": ('    elif cur["digest"]:\n        why', '    elif False:\n        why'),
    "history conflict with --digest allowed": ('if pinned_known and pinned_known[0] != digest:', 'if False:'),
    "two digests in history allowed": ('if len(pinned_known) > 1:', 'if False:'),
    "history digest ignored": ('    elif pinned_known:\n        target, source = pinned_known[0], "history"', '    elif False:\n        target, source = None, "history"'),
    "several blocks tolerated": ('if len(found) != 1:', 'if len(found) < 1:'),
    "digest line not validated": ('if not dm:', 'if False:'),
    "duplicate digest tolerated": ('if len(digests) > 1:', 'if False:'),
    "digest grammar not enforced": ('if digest and not DIGEST_RE.fullmatch(digest):', 'if False:'),
    "tag grammar not enforced": ('if not TAG_RE.fullmatch(a.tag):', 'if False:'),
    "path prefix not enforced": ('or not norm.startswith(SERVICES_PREFIX)', 'or False'),
    "symlink not refused": ('if os.path.realpath(path) != os.path.join(os.path.realpath(os.curdir), norm):', 'if False:'),
    "shallow history treated as empty": ('    if not shas:\n        raise Unreadable', '    if False:\n        raise Unreadable'),
    "tag style not kept": ('lines[block["tag_at"]] = f"{ind}tag: {q}{tag}{q}"', 'lines[block["tag_at"]] = f\'{ind}tag: "{tag}"\''),
}


def template_checks():
    fails = []
    t = yaml.safe_load(TEMPLATE.read_text())
    args = {p["name"]: p for p in t["spec"]["arguments"]["parameters"]}
    check("target_digest is an optional workflow parameter", args.get("target_digest", {}).get("value"), "", fails)
    step = [x for x in t["spec"]["templates"] if x["name"] == "patch-values"][0]
    src = step["script"]["source"]
    code = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith("#"))
    env = {e["name"]: e["value"] for e in step["script"]["env"]}
    check("digest bound as env", env.get("PARAM_TARGET_DIGEST"), "{{inputs.parameters.target_digest}}", fails)
    if "{{" in src:
        fails.append("step source interpolates an Argo placeholder: parameters must arrive as env (gitops#992)")
    if "rollback-image-ref.py" not in src:
        fails.append("the step no longer calls scripts/rollback-image-ref.py")
    if "sed -i" in code and "tag:" in code.split("sed -i")[1].split("\n")[0]:
        fails.append("the step patches the tag line with sed again, leaving a pinned digest in place")
    if "--depth=1" in code:
        fails.append("a --depth=1 clone cannot answer which digest a tag had")
    if "--filter=blob:none" not in code:
        fails.append("the clone no longer carries history for the digest lookup")
    check("digest checked before use", "target_digest must be sha256" in src, True, fails)
    return fails


def main():
    base = cases(SCRIPT)
    base += template_checks()
    status = 0
    if base:
        print("FAIL on the real script:")
        for f in base:
            print("  " + f)
        status = 1
    else:
        print("ok: all cases pass on the real script")
    for name, (a, b) in MUTATIONS.items():
        if SCRIPT.count(a) != 1:
            print(f"MUTATION NOT APPLICABLE ({SCRIPT.count(a)} matches): {name}")
            status = 1
            continue
        red = cases(SCRIPT.replace(a, b))
        if not red:
            print(f"MUTATION SURVIVED: {name}")
            status = 1
    if status == 0:
        print(f"ok: all {len(MUTATIONS)} mutations turn at least one case red")
    return status


if __name__ == "__main__":
    sys.exit(main())
