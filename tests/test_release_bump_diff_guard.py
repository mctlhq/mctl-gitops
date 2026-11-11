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
    "two files": diff(SVC, TAGS) + diff(API, [('        tag: "4.154.0"', '        tag: "4.154.1"')]),
}
BAD = {
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
    "nine files": "".join(diff(f"platform-gitops/services/t/s{i}/values.yaml", TAGS) for i in range(9)),
    "same file twice": diff(SVC, TAGS) + diff(SVC, TAGS),
    "removals outnumber additions": diff(SVC, TAGS).replace("+  tag: \"1.1.0\"\n", ""),
}


def run(script, text):
    return subprocess.run([sys.executable, str(script)], input=text.encode(), capture_output=True)


def verdicts(script):
    out = []
    for n, t in GOOD.items():
        r = run(script, t)
        out.append((f"accepts: {n}", r.returncode == 0, r))
    for n, t in BAD.items():
        r = run(script, t)
        # A refusal is the guard's own verdict (exit 1, REFUSED on stderr), not a crash.
        out.append((f"refuses: {n}", r.returncode == 1 and b"REFUSED" in r.stderr, r))
    r = subprocess.run([sys.executable, str(script)], input=b"\xff\xfe", capture_output=True)
    out.append(("refuses: undecodable input (exit 2)", r.returncode == 2, r))
    return out


for n, ok, r in verdicts(GUARD):
    check(n, ok, f"rc={r.returncode} {r.stderr[-200:]!r}")

src = GUARD.read_text()
MUT = [
    ("empty diff passes (both emptiness checks removed)",
     [('    if not files:\n        problems.append("the diff names no file")', "    pass"),
      ('    if changed == 0:\n        problems.append("the diff changes no line")', "    pass")]),
    ("a header-only diff passes", [('    if changed == 0:\n        problems.append("the diff changes no line")', "    pass")]),
    ("any file accepted", [("not cur.startswith(ALLOWED_PREFIXES) or ", "")]),
    ("non-yaml accepted", [(' or not cur.endswith((".yaml", ".yml"))', "")]),
    ("traversal accepted", [('".." in cur.split("/") or ', "")]),
    ("file cap removed", [("    if len(files) > MAX_FILES:", "    if False:")]),
    ("duplicate files accepted", [("    if len(set(files)) != len(files):", "    if False:")]),
    ("non-tag lines accepted", [("            if s is None:\n                problems.append", "            if s is None:\n                continue\n                problems.append")]),
    ("identity (key, image) not compared", [("            if ri != ai:", "            if False:")]),
    ("same-tag rewrite accepted", [("            elif rt == at:", "            elif False:")]),
    ("unpaired lines accepted", [("        if len(removed) != len(added):", "        if False:")]),
    ("new/deleted/mode/rename headers accepted (both defences removed)",
     [("        if HEADER_REFUSE.match(line):", "        if HEADER_REFUSE.match(line) and False:"),
      ('        problems.append(f"{cur}: unrecognised diff line {line[:80]}")', "        pass")]),
    ("renames accepted (both defences removed)",
     [("m.group(1) != m.group(2)", "False"), ("        if HEADER_REFUSE.match(line):", "        if False:"),
      ('        problems.append(f"{cur}: unrecognised diff line {line[:80]}")', "        pass")]),
    ("tag charset loosened", [('TAG = r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"', 'TAG = r"[^\\n]+"')]),
]
for name, reps in MUT:
    for old, _ in reps:
        check(f"mutant anchor exists: {name}", src.count(old) == 1, f"count={src.count(old)}")
    with tempfile.TemporaryDirectory() as d:
        m = pathlib.Path(d) / "release-bump-diff-guard.py"
        text = src
        for old, new in reps:
            text = text.replace(old, new)
        m.write_text(text)
        killed = not all(ok for _, ok, _ in verdicts(m))
        check(f"mutant killed: {name}", killed)

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("all release-bump-diff-guard checks passed")
