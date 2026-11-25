"""release-bump-diff-guard.py: a bump diff may only move image tags.

Plain script: `python3 tests/test_release_bump_diff_guard.py`. Green on real tag
moves, red on every other shape, and each mutant of the guard turns a case red.
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/release-bump-diff-guard.py"
failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(f"{name}: {detail}")


API = "platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml"
SVC = "platform-gitops/services/labs/claude-remote/values.yaml"
CWFT = "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-x.yaml"


def diff(path, pairs, extra=""):
    out = f"diff --git a/{path} b/{path}\n{extra}index 111..222 100644\n--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,3 @@\n ctx\n"
    for old, new in pairs:
        out += f"-{old}\n+{new}\n"
    return out + " ctx\n"


TAGS = [('  tag: "1.0.0"', '  tag: "1.1.0"')]
GOOD = {
    "tag line in a values file": diff(SVC, TAGS),
    "tag line unquoted": diff(SVC, [("  tag: 1.0.0", "  tag: 1.1.0")]),
    "tag inside the bootstrap values block": diff(API, [('        tag: "4.154.0"', '        tag: "4.155.1"')]),
    "inline image reference": diff(CWFT, [("        image: ghcr.io/mctlhq/mctl-agents:1.1.0", "        image: ghcr.io/mctlhq/mctl-agents:1.2.0")]),
    "workflow parameter value": diff(CWFT, [('          value: "ghcr.io/mctlhq/mctl-agents:1.1.0"', '          value: "ghcr.io/mctlhq/mctl-agents:1.2.0"')]),
    "non-semver tags are not ordered": diff(SVC, [("  tag: sha-aaa", "  tag: sha-bbb")]),
    "a prerelease-free upgrade across digits": diff(SVC, [("  tag: 1.9.0", "  tag: 1.10.0")]),
    "two files": diff(SVC, TAGS) + diff(API, [('        tag: "4.154.0"', '        tag: "4.154.1"')]),
    "two tag moves in one block, git order": diff(SVC, []).replace(
        " ctx\n", ' ctx\n-  tag: "1.0.0"\n-  tag: "2.0.0"\n+  tag: "1.1.0"\n+  tag: "2.1.0"\n', 1),
    "two tag moves in separate blocks": diff(SVC, []).replace(
        " ctx\n", ' a:\n-  tag: "1.0.0"\n+  tag: "1.1.0"\n b:\n-  tag: "2.0.0"\n+  tag: "2.1.0"\n', 1),
    "tag move on a last line without a newline": diff(SVC, []).replace(
        " ctx\n", ' ctx\n-  tag: "1.0.0"\n\\ No newline at end of file\n+  tag: "1.1.0"\n\\ No newline at end of file\n', 1),
}
D1 = '  digest: "sha256:' + "1" * 64 + '"'
D2 = '  digest: "sha256:' + "2" * 64 + '"'


def block(path, body):
    """A one-hunk diff whose change block is `body` (lines with their +/-/space prefix)."""
    return diff(path, []).replace(" ctx\n", " ctx\n" + "".join(l + "\n" for l in body), 1)


GOOD.update({
    "digest introduced with a tag move": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', "+" + D1]),
    "digest moves with its tag": block(SVC, ['-  tag: "1.0.0"', "-" + D1, '+  tag: "1.1.0"', "+" + D2]),
    "digest unquoted": block(SVC, ["-  tag: 1.0.0", "+  tag: 1.1.0", "+  digest: sha256:" + "a" * 64]),
    "digest line followed by context": block(SVC, ['-  tag: "1.0.0"', "-" + D1, '+  tag: "1.1.0"', "+" + D2, "   pullPolicy: IfNotPresent"]),
})
BAD = {
    "digest without a tag move": block(SVC, ["-" + D1, "+" + D2]),
    "digest added alone": block(SVC, ["+" + D1]),
    "digest outside a service values file": block(API, ['-        tag: "4.154.0"', '+        tag: "4.155.0"', "+        digest: \"sha256:" + "1" * 64 + '"']),
    "digest on an inline image reference":
        block(CWFT, ["-        image: ghcr.io/mctlhq/mctl-agents:1.1.0", "+        image: ghcr.io/mctlhq/mctl-agents:1.2.0", "+        digest: sha256:" + "1" * 64]),
    "digest indented differently from its tag": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', '+    digest: "sha256:' + "1" * 64 + '"']),
    "digest not directly under its tag": block(SVC, ['-  tag: "1.0.0"', "-  x: 1", '+  tag: "1.1.0"', "+  x: 1", "+" + D1]),
    "two digests for one tag": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', "+" + D1, "+" + D2]),
    "pinned digest dropped": block(SVC, ['-  tag: "1.0.0"', "-" + D1, '+  tag: "1.1.0"']),
    "tag moves under an unchanged digest": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', " " + D1]),
    "digest too short": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', '+  digest: "sha256:' + "1" * 63 + '"']),
    "digest uppercase hex": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', '+  digest: "sha256:' + "A" * 64 + '"']),
    "digest other algorithm": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', '+  digest: "sha512:' + "1" * 64 + '"']),
    "digest empty": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', '+  digest: ""']),
    "digest with a trailing comment": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', "+" + D1 + " # x"]),
    "digest under a tag that keeps its value": block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.0.0"', "+" + D1]),
    "empty diff": "",
    "no file header": "-  tag: 1\n+  tag: 2\n",
    "another key changed": diff(SVC, [("  replicas: 1", "  replicas: 3")]),
    "a tag line plus a second change": diff(SVC, TAGS + [("  replicas: 1", "  replicas: 9")]),
    "tag line added without a removal": diff(SVC, []).replace(" ctx\n", " ctx\n+  tag: 9\n", 1),
    "image name swapped": diff(CWFT, [("        image: ghcr.io/mctlhq/mctl-agents:1.1.0", "        image: ghcr.io/evil/agents:1.1.0")]),
    "image name swapped with the tag": diff(CWFT, [("        image: ghcr.io/mctlhq/mctl-agents:1.1.0", "        image: ghcr.io/evil/agents:1.2.0")]),
    "key changed from tag to value": diff(SVC, [("  tag: 1.0.0", "  value: 1.1.0")]),
    "indentation changed": diff(SVC, [("  tag: 1.0.0", "    tag: 1.1.0")]),
    "tag with a newline smuggle": diff(SVC, [("  tag: 1.0.0", '  tag: "1.1.0" # x')]),
    "tag with a space": diff(SVC, [("  tag: 1.0.0", "  tag: 1.1.0 privileged")]),
    "same tag rewritten": diff(SVC, [("  tag: 1.0.0", "  tag: 1.0.0")]),
    "workflow file": diff(".github/workflows/auto-merge.yml", TAGS),
    "release gate policy": diff("platform-gitops/release-gates.yaml", TAGS),
    "a script": diff("scripts/release-gate.py", TAGS),
    "path traversal": diff("platform-gitops/services/../../scripts/x.yaml", TAGS),
    "not yaml": diff("platform-gitops/services/a/b/run.sh", TAGS),
    "new file": diff(SVC, TAGS, extra="new file mode 100644\n"),
    "deleted file": diff(SVC, TAGS, extra="deleted file mode 100644\n"),
    "mode change": diff(SVC, TAGS, extra="old mode 100644\nnew mode 100755\n"),
    "rename": "diff --git a/" + SVC + " b/platform-gitops/services/x/y/values.yaml\nsimilarity index 90%\n",
    "binary patch": diff(SVC, TAGS, extra="GIT binary patch\n"),
    "header without a changed line": f"diff --git a/{SVC} b/{SVC}\nindex 1..2 100644\n--- a/{SVC}\n+++ b/{SVC}\n@@ -1 +1 @@\n ctx\n",
    "tag moves backwards": diff(SVC, [("  tag: 1.2.0", "  tag: 1.1.0")]),
    "tag moves backwards across digits": diff(SVC, [("  tag: 1.10.0", "  tag: 1.9.0")]),
    "added content line that looks like a file marker":
        diff(SVC, TAGS).replace(" ctx\n-  tag", " ctx\n+++ b/x\n-  tag", 1),
    "removed content line that looks like a file marker":
        diff(SVC, TAGS).replace(" ctx\n-  tag", " ctx\n--- a/x\n-  tag", 1),
    "hunk-less change lines": f"diff --git a/{SVC} b/{SVC}\nindex 1..2 100644\n--- a/{SVC}\n+++ b/{SVC}\n-  tag: 1.0.0\n+  tag: 1.1.0\n",
    "nine files": "".join(diff(f"platform-gitops/services/t/s{i}/values.yaml", TAGS) for i in range(9)),
    "same file twice": diff(SVC, TAGS) + diff(SVC, TAGS),
    "removals outnumber additions": diff(SVC, TAGS).replace("+  tag: \"1.1.0\"\n", ""),
    # gitops bug report ch. 14: the tag key leaves block `a` and appears
    # under `b`; pairing per file called that a tag move.
    "tag key moved to another block": diff(SVC, []).replace(
        " ctx\n", " a:\n-  tag: 1.0.0\n b:\n+  tag: 1.0.1\n", 1),
    "tag key moved across hunks": diff(SVC, []).replace(
        " ctx\n", " a:\n-  tag: 1.0.0\n@@ -9,2 +9,2 @@\n b:\n+  tag: 1.0.1\n", 1),
    "blocks that only pair across each other": diff(SVC, []).replace(
        " ctx\n", " a:\n-  tag: 1.0.0\n+  tag: 1.1.0\n+  tag: 1.2.0\n b:\n-  tag: 2.0.0\n", 1),
}


def run(script, text):
    return subprocess.run([sys.executable, str(script)], input=text.encode(), capture_output=True)


def run_opts(script, text, args, patch=None):
    """Run with options; `patch` (text) is written to a file and passed after --same-lines-as."""
    with tempfile.TemporaryDirectory() as d:
        args = list(args)
        if patch is not None:
            pf = pathlib.Path(d) / "bump.patch"
            pf.write_text(patch)
            args += ["--same-lines-as", str(pf)]
        return subprocess.run([sys.executable, str(script), *args], input=text.encode(), capture_output=True)


TWO = [('  tag: "1.0.0"', '  tag: "1.1.0"'), ('  tag: "2.0.0"', '  tag: "2.1.0"')]
SIG = "\n-- \n2.39.0\n\n"
PATCH_HEAD = "From abc Mon Sep 17 00:00:00 2001\nFrom: t <t@t>\nSubject: [PATCH] bump\n\n---\n"


def option_verdicts(script, witness=None):
    out = []

    def case(name, diff_text, args, want, patch=None):
        if witness is not None and witness != name:
            return
        r = run_opts(script, diff_text, args, patch=patch)
        ok = (r.returncode == 0) if want == "accept" else (r.returncode == 1 and b"REFUSED" in r.stderr)
        out.append((name, ok, r))

    case("strict-order accepts a forward semver move", diff(SVC, TAGS), ["--strict-order"], "accept")
    case("strict-order refuses tags that cannot be ordered", diff(SVC, [("  tag: sha-aaa", "  tag: sha-bbb")]), ["--strict-order"], "refuse")
    case("strict-order refuses a move between a semver and a non-semver tag", diff(SVC, [("  tag: 1.0.0", "  tag: sha-bbb")]), ["--strict-order"], "refuse")
    patch = PATCH_HEAD + diff(SVC, TAGS) + SIG
    case("same-lines-as accepts the same lines (format-patch signature ignored)", diff(SVC, TAGS), [], "accept", patch=patch)
    case("same-lines-as refuses an extra changed line of the same identity", diff(SVC, TWO), [], "refuse", patch=patch)
    case("same-lines-as refuses the same identity moved to a different tag",
         diff(SVC, [('  tag: "1.0.0"', '  tag: "1.2.0"')]), [], "refuse", patch=patch)
    case("same-lines-as refuses a different file", diff(API, [('        tag: "4.154.0"', '        tag: "4.154.1"')]), [], "refuse", patch=patch)
    case("same-lines-as refuses a different identity", diff(CWFT, [("        image: ghcr.io/mctlhq/mctl-agents:1.1.0", "        image: ghcr.io/mctlhq/mctl-agents:1.2.0")]), [], "refuse", patch=PATCH_HEAD + diff(CWFT, [('          value: "ghcr.io/mctlhq/mctl-agents:1.1.0"', '          value: "ghcr.io/mctlhq/mctl-agents:1.2.0"')]) + SIG)
    DPATCH = PATCH_HEAD + block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', "+" + D1]) + SIG
    case("same-lines-as accepts the same tag and digest",
         block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', "+" + D1]), [], "accept", patch=DPATCH)
    case("same-lines-as refuses the same tag with another digest",
         block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"', "+" + D2]), [], "refuse", patch=DPATCH)
    case("same-lines-as refuses a patch digest the resolution left out",
         block(SVC, ['-  tag: "1.0.0"', '+  tag: "1.1.0"']), [], "refuse", patch=DPATCH)
    case("same-lines-as refuses a patch that changes no line", diff(SVC, TAGS), [], "refuse", patch=PATCH_HEAD + SIG)
    if witness is None or witness == "same-lines-as with an unreadable patch exits 2":
        r = run_opts(script, diff(SVC, TAGS), ["--same-lines-as", "/nonexistent/bump.patch"])
        out.append(("same-lines-as with an unreadable patch exits 2", r.returncode == 2, r))
    if witness is None or witness == "same-lines-as without a path exits 2":
        r = run_opts(script, diff(SVC, TAGS), ["--same-lines-as"])
        out.append(("same-lines-as without a path exits 2", r.returncode == 2, r))
    return out


def verdicts(script, witness=None):
    out = []
    for n, t in GOOD.items():
        name = f"accepts: {n}"
        if witness is not None and witness != name:
            continue
        r = run(script, t)
        out.append((name, r.returncode == 0, r))
    for n, t in BAD.items():
        name = f"refuses: {n}"
        if witness is not None and witness != name:
            continue
        r = run(script, t)
        # A refusal is the guard's own verdict (exit 1, REFUSED on stderr), not a crash.
        out.append((name, r.returncode == 1 and b"REFUSED" in r.stderr, r))
    if witness is None or witness == "refuses: undecodable input (exit 2)":
        r = subprocess.run([sys.executable, str(script)], input=b"\xff\xfe", capture_output=True)
        out.append(("refuses: undecodable input (exit 2)", r.returncode == 2, r))
    return out + option_verdicts(script, witness=witness)


baseline = verdicts(GUARD)
baseline_names = {n for n, _, _ in baseline}
for n, ok, r in baseline:
    check(n, ok, f"rc={r.returncode} {r.stderr[-200:]!r}")

src = GUARD.read_text()
MUT = [
    ("empty diff passes (both emptiness checks removed)",
     [('    if not files:\n        problems.append("the diff names no file")', "    pass"),
      ('    if changed == 0:\n        problems.append("the diff changes no line")', "    pass")],
     "refuses: empty diff"),
    ("a header-only diff passes", [('    if changed == 0:\n        problems.append("the diff changes no line")', "    pass")],
     "refuses: header without a changed line"),
    ("any file accepted", [("not cur.startswith(ALLOWED_PREFIXES) or ", "")], "refuses: workflow file"),
    ("non-yaml accepted", [(' or not cur.endswith((".yaml", ".yml"))', "")], "refuses: not yaml"),
    ("traversal accepted", [('".." in cur.split("/") or ', "")], "refuses: path traversal"),
    ("file cap removed", [("    if len(files) > MAX_FILES:", "    if False:")], "refuses: nine files"),
    ("duplicate files accepted", [("    if len(set(files)) != len(files):", "    if False:")], "refuses: same file twice"),
    ("non-tag lines accepted", [("            if s is None:\n                problems.append", "            if s is None:\n                continue\n                problems.append")],
     "refuses: another key changed"),
    ("identity (key, image) not compared", [("            if ri != ai:", "            if False:")], "refuses: image name swapped with the tag"),
    ("same-tag rewrite accepted", [("            elif rt == at:", "            elif False:")], "refuses: digest under a tag that keeps its value"),
    ("unpaired lines accepted (tag lines no longer paired per block)",
     [("        if cur is not None and len(blk_removed) != len(blk_added):", "        if False:")],
     "refuses: tag line added without a removal"),
    ("context lines do not end a block",
     [('            end_block()\n            continue\n        if line[0] in "+-":', '            continue\n        if line[0] in "+-":')],
     "refuses: tag key moved to another block"),
    ("new/deleted/mode/rename headers accepted (both defences removed)",
     [("            if HEADER_REFUSE.match(line):", "            if HEADER_REFUSE.match(line) and False:"),
      ('            problems.append(f"{cur}: unrecognised header line {line[:80]}")', "            pass")],
     "refuses: new file"),
    ("renames accepted (both defences removed)",
     [("m.group(1) != m.group(2)", "False"), ("            if HEADER_REFUSE.match(line):", "            if False:"),
      ('            problems.append(f"{cur}: unrecognised header line {line[:80]}")', "            pass")],
     "refuses: new file"),
    ("file markers skipped anywhere, not only before the first hunk",
     [("                in_header = False\n                continue", "                continue")],
     "accepts: tag line in a values file"),
    ("a tag may move backwards", [("elif _semver(rt) is not None and _semver(at) is not None and _semver(at) < _semver(rt):", "elif False:")],
     "refuses: tag moves backwards"),
    ("semver compared as strings", [("_semver(at) < _semver(rt)", "at < rt")], "accepts: a prerelease-free upgrade across digits"),
    ("strict-order ignored", [("    strict_order = \"--strict-order\" in argv", "    strict_order = False")],
     "strict-order refuses tags that cannot be ordered"),
    ("unorderable tags pass strict-order", [("elif strict_order and (_semver(rt) is None or _semver(at) is None):", "elif False:")],
     "strict-order refuses tags that cannot be ordered"),
    ("same-lines comparison skipped", [("        elif got != want:", "        elif False:")],
     "same-lines-as refuses an extra changed line of the same identity"),
    ("same-lines compares identities only", [("collect[cur] = [(ai, at, ad) for (ai, at, ad) in added]", "collect[cur] = [(ai, None, None) for (ai, at, ad) in added]")],
     "same-lines-as refuses the same identity moved to a different tag"),
    ("same-lines ignores the digest", [("collect[cur] = [(ai, at, ad) for (ai, at, ad) in added]", "collect[cur] = [(ai, at, None) for (ai, at, ad) in added]")],
     "same-lines-as refuses the same tag with another digest"),
    ("a digest line accepted anywhere in the repo", [("                if not cur.startswith(DIGEST_PREFIX):", "                if False:")],
     "refuses: digest outside a service values file"),
    ("a digest line accepted away from its tag line",
     [('                elif not (isinstance(last, tuple) and last == ("tag", d.group("ind"))):', "                elif False:")],
     "refuses: digest without a tag move"),
    ("a pinned digest may be dropped", [("            if rd is not None and ad is None:", "            if False:")],
     "refuses: pinned digest dropped"),
    ("a tag may move under an unchanged digest", [('            if stale and blk_last["+"] == ("tag", stale.group("ind")):', "            if False:")],
     "refuses: tag moves under an unchanged digest"),
    ("digest charset loosened", [("(?P<digest>sha256:[0-9a-f]{64})", "(?P<digest>[^\\n]+)")], "refuses: digest too short"),
    ("an empty patch passes same-lines (both defences removed)", [("        if not want:", "        if False:"), ("        elif got != want:", "        elif False:")],
     "same-lines-as refuses an extra changed line of the same identity"),
    ("unreadable patch is not an error", [("            print(f\"release-bump-diff-guard: cannot read the patch: {type(exc).__name__}: {exc}\", file=sys.stderr)\n            return 2", "            return 0")],
     "same-lines-as with an unreadable patch exits 2"),
    ("tag charset loosened", [('TAG = r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"', 'TAG = r"[^\\n]+"')], "refuses: tag with a newline smuggle"),
]
for name, reps, witness in MUT:
    check(f"mutant target exists: {name}", witness in baseline_names, f"unknown witness {witness!r}")
    for old, _ in reps:
        check(f"mutant anchor exists: {name}", src.count(old) == 1, f"count={src.count(old)}")
    with tempfile.TemporaryDirectory() as d:
        m = pathlib.Path(d) / "release-bump-diff-guard.py"
        text = src
        for old, new in reps:
            text = text.replace(old, new)
        m.write_text(text)
        res = verdicts(m, witness=witness)
        killed = bool(res) and not all(ok for _, ok, _ in res)
        check(f"mutant killed: {name}", killed)

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("all release-bump-diff-guard checks passed")
