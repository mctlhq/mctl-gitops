#!/usr/bin/env python3
"""Refuse a release-bump diff that does anything but move an image tag.

    git diff <base>..<head> | release-bump-diff-guard.py
    gh pr diff N            | release-bump-diff-guard.py

Reads a unified diff on stdin. Exit 0 only when every change is a tag move on a
values or manifest file under an allowed platform-gitops prefix: the removed
and the added lines pair up one to one, keep their key, indentation and image
name, and differ only in the tag. Exit 1 refuses; exit 2 means the diff could
not be read. Both are a refusal for the callers (publish-pr, auto-merge.yml):
"could not read" is never "nothing to object to", and an empty diff is not a
pass either.

New, deleted, renamed and mode-changed files, binary patches, workflow files,
scripts and the gate policy are all outside what a bump may touch. The
allowlist mirrors ALLOWED_PREFIXES of release-deploy.yaml and gitops-bump.yaml.
"""
import re
import sys

ALLOWED_PREFIXES = (
    "platform-gitops/services/",
    "platform-gitops/argo-workflows/cluster-templates/",
    "platform-gitops/bootstrap/templates/mctl-platform/",
)
MAX_FILES = 8
TAG = r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"
# `tag: "1.2.3"` and the split registry/repository/tag shape.
TAG_LINE = re.compile(r'^(?P<key>\s*(?:-\s+)?tag:)\s*(?P<q>["\']?)(?P<tag>' + TAG + r')(?P=q)\s*$')
# `image: ghcr.io/org/name:1.2.3` and the workflow-parameter `value:` default.
REF_LINE = re.compile(
    r'^(?P<key>\s*(?:-\s+)?(?:image|value):)\s*(?P<q>["\']?)'
    r'(?P<img>[a-z0-9.-]+(?::[0-9]+)?(?:/[a-z0-9._-]+)+):(?P<tag>' + TAG + r')(?P=q)\s*$'
)
HEADER_REFUSE = re.compile(
    r"^(new file mode|deleted file mode|old mode|new mode|rename |copy |similarity index|dissimilarity index|Binary files|GIT binary patch)"
)


def shape(line: str):
    """(identity, tag) of a tag line, or None. Identity is everything but the tag value."""
    m = TAG_LINE.match(line)
    if m:
        return (m.group("key"), None), m.group("tag")
    m = REF_LINE.match(line)
    if m:
        return (m.group("key"), m.group("img")), m.group("tag")
    return None


def judge(diff: str) -> list:
    """Return the list of reasons to refuse; empty means every change is a tag move."""
    problems = []
    files = []
    cur = None
    removed = added = None
    changed = 0

    def close():
        if cur is None:
            return
        if len(removed) != len(added):
            problems.append(f"{cur}: {len(removed)} removed and {len(added)} added lines do not pair")
            return
        for (ri, rt), (ai, at) in zip(removed, added):
            if ri != ai:
                problems.append(f"{cur}: a changed line moves more than the tag ({ri} -> {ai})")
            elif rt == at:
                problems.append(f"{cur}: a changed line keeps the same tag")

    for raw in diff.split("\n"):
        line = raw
        if line.startswith("diff --git "):
            close()
            m = re.fullmatch(r"diff --git a/(\S+) b/(\S+)", line)
            if not m or m.group(1) != m.group(2):
                problems.append(f"unreadable or renamed file header: {line[:120]}")
                cur, removed, added = None, [], []
                continue
            cur = m.group(1)
            files.append(cur)
            removed, added = [], []
            if ".." in cur.split("/") or not cur.startswith(ALLOWED_PREFIXES) or not cur.endswith((".yaml", ".yml")):
                problems.append(f"{cur}: not a values or manifest file under an allowed prefix")
            continue
        if cur is None:
            continue
        if HEADER_REFUSE.match(line):
            problems.append(f"{cur}: {line[:60]}")
            continue
        if line.startswith(("--- ", "+++ ", "index ", "@@", "\\ ", " ")) or line == "":
            if line.startswith(("--- ", "+++ ")) and not re.fullmatch(r"(---|\+\+\+) (a|b)/\S+", line):
                problems.append(f"{cur}: unexpected file marker {line[:80]}")
            continue
        if line[0] in "+-":
            changed += 1
            s = shape(line[1:])
            if s is None:
                problems.append(f"{cur}: not a tag line: {line[:100]}")
                continue
            (removed if line[0] == "-" else added).append(s)
            continue
        problems.append(f"{cur}: unrecognised diff line {line[:80]}")
    close()
    if not files:
        problems.append("the diff names no file")
    if len(files) > MAX_FILES:
        problems.append(f"{len(files)} files exceed the cap of {MAX_FILES}")
    if len(set(files)) != len(files):
        problems.append("a file appears twice")
    if changed == 0:
        problems.append("the diff changes no line")
    return problems


def main() -> int:
    try:
        data = sys.stdin.buffer.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"release-bump-diff-guard: cannot read the diff: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    problems = judge(data)
    if problems:
        for p in problems:
            print(f"release-bump-diff-guard: REFUSED: {p}", file=sys.stderr)
        return 1
    print("release-bump-diff-guard: only image tags move")
    return 0


if __name__ == "__main__":
    sys.exit(main())
