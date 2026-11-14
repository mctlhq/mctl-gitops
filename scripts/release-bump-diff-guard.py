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

Options (used by release-bump-apply.sh after a conflict resolution only):
--strict-order refuses a tag move whose tags are not both MAJOR.MINOR.PATCH;
--same-lines-as PATCH requires the changed lines to be exactly the ones PATCH
changes.

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


def _semver(tag: str):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", tag)
    return tuple(int(x) for x in m.groups()) if m else None


def shape(line: str):
    """(identity, tag) of a tag line, or None. Identity is everything but the tag value."""
    m = TAG_LINE.match(line)
    if m:
        return (m.group("key"), None), m.group("tag")
    m = REF_LINE.match(line)
    if m:
        return (m.group("key"), m.group("img")), m.group("tag")
    return None


def judge(diff: str, strict_order: bool = False, collect: dict = None) -> list:
    """Return the list of reasons to refuse; empty means every change is a tag move.

    strict_order: a tag move whose two tags are not both plain MAJOR.MINOR.PATCH
    is refused too (they cannot be shown to go forward), not just left unjudged.
    collect: when a dict, filled with file -> (identity, new tag) of the changed
    lines in order, for the caller to compare two diffs. The new tag is part of
    it because every split `tag:` line shares one identity.
    """
    problems = []
    files = []
    cur = None
    removed = added = None
    changed = 0
    in_header = False  # between `diff --git` and the first `@@`
    # One change block: the run of -/+ lines between two context lines (or a
    # hunk boundary). Removed and added tag lines pair by POSITION, so they
    # must pair inside the block. Pairing across the whole file let
    # ` a:` `-  tag: 1.0.0` ` b:` `+  tag: 1.0.1` pass as a tag move
    # although the tag key left block `a` and appeared under `b`.
    blk_removed, blk_added = [], []

    def end_block():
        if cur is not None and len(blk_removed) != len(blk_added):
            problems.append(
                f"{cur}: a change block removes {len(blk_removed)} and adds "
                f"{len(blk_added)} lines; tag lines must pair in place"
            )
        blk_removed.clear()
        blk_added.clear()

    def close():
        end_block()
        if cur is None:
            return
        if len(removed) != len(added):
            return  # already refused by end_block(): some block does not pair
        if collect is not None:
            collect[cur] = [(ai, at) for (ai, at) in added]
        for (ri, rt), (ai, at) in zip(removed, added):
            if ri != ai:
                problems.append(f"{cur}: a changed line moves more than the tag ({ri} -> {ai})")
            elif rt == at:
                problems.append(f"{cur}: a changed line keeps the same tag")
            elif strict_order and (_semver(rt) is None or _semver(at) is None):
                problems.append(f"{cur}: tags cannot be ordered ({rt} -> {at})")
            elif _semver(rt) is not None and _semver(at) is not None and _semver(at) < _semver(rt):
                # A re-run of an older release must not roll a newer tag back.
                # Tags that are not plain MAJOR.MINOR.PATCH cannot be ordered
                # and are not judged here.
                problems.append(f"{cur}: tag moves backwards ({rt} -> {at})")

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
            in_header = True
            if ".." in cur.split("/") or not cur.startswith(ALLOWED_PREFIXES) or not cur.endswith((".yaml", ".yml")):
                problems.append(f"{cur}: not a values or manifest file under an allowed prefix")
            continue
        if cur is None:
            continue
        if in_header:
            # File-level lines exist only before the first hunk. After it, every
            # line starting with + or - is content, also `+++ b/x` and `--- a/x`.
            if HEADER_REFUSE.match(line):
                problems.append(f"{cur}: {line[:60]}")
                continue
            if line.startswith("@@"):
                in_header = False
                continue
            if line.startswith(("--- ", "+++ ")):
                if not re.fullmatch(r"(---|\+\+\+) (a|b)/\S+", line):
                    problems.append(f"{cur}: unexpected file marker {line[:80]}")
                continue
            if line.startswith("index ") or line == "":
                continue
            problems.append(f"{cur}: unrecognised header line {line[:80]}")
            continue
        if line.startswith("\\ "):
            continue  # "\ No newline at end of file" belongs to the line above
        if line.startswith("@@") or line.startswith(" ") or line == "":
            end_block()
            continue
        if line[0] in "+-":
            changed += 1
            (blk_removed if line[0] == "-" else blk_added).append(line)
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
    argv = sys.argv[1:]
    strict_order = "--strict-order" in argv
    same_as = None
    if "--same-lines-as" in argv:
        i = argv.index("--same-lines-as")
        if i + 1 >= len(argv):
            print("release-bump-diff-guard: --same-lines-as needs a patch path", file=sys.stderr)
            return 2
        same_as = argv[i + 1]
    try:
        data = sys.stdin.buffer.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"release-bump-diff-guard: cannot read the diff: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    got = {}
    problems = judge(data, strict_order=strict_order, collect=got)
    if same_as is not None:
        # The resolved change must touch exactly the lines the bump patch itself
        # touches: a conflict resolution that took the patch side of a whole file
        # would otherwise also revert a neighbouring image line changed on main.
        try:
            with open(same_as, "rb") as fh:
                patch = fh.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"release-bump-diff-guard: cannot read the patch: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        want = {}
        # Only the changed lines are read from the patch; its mail headers and
        # signature are not judged here (the resolved diff is, above).
        judge(patch, collect=want)
        if not want:
            problems.append("the bump patch names no changed line")
        elif got != want:
            problems.append(f"the resolved change touches {got}, the bump patch touches {want}")
    if problems:
        for p in problems:
            print(f"release-bump-diff-guard: REFUSED: {p}", file=sys.stderr)
        return 1
    print("release-bump-diff-guard: only image tags move")
    return 0


if __name__ == "__main__":
    sys.exit(main())
