#!/usr/bin/env python3
"""Insert one sync window into an AppProject template, and hash a window.

Used by .github/workflows/release-window-pr.yml (proposal issue-2828, 8.2).
The AppProject templates are Helm templates (`{{ .Values... }}`), so they are
edited as text, never loaded and dumped. The caller re-renders the chart and
checks that exactly this window arrived; this script only places the text.

  release-window-insert.py hash PROJECT         window JSON on stdin -> sha256 hex
  release-window-insert.py hash-remove PROJECT  the same window, for a REMOVAL -> sha256 hex
  release-window-insert.py insert FILE          window JSON on stdin, edits FILE
  release-window-insert.py remove FILE          window JSON on stdin, deletes that one window from FILE
  release-window-insert.py --selftest

The canonical form behind `hash` is
  json.dumps({"project": PROJECT, "window": WINDOW}, sort_keys=True, separators=(",", ":"))
so whoever approves a window (the dispatcher) and the workflow that applies it
hash the same bytes, and an approval for one project cannot be replayed against
another. A window that is not a JSON object is refused.

`insert` adds the window under `spec.syncWindows` (two-space indent):
  * no `syncWindows` key: the block is appended at the end of the file;
  * an existing block: the item is appended after its last line;
  * `syncWindows: []`, a flow-style value, or a file whose last non-blank line
    ends in a template control action: refused. A shape this script does not recognise
    is exit 2, never a guess.
`remove` (release-window-removal-pr.yml) deletes exactly one block, the one whose
parsed content equals the window (same keys, same values, same list order). No
match, more than one match, a comment or blank line between items, or a block
that does not parse is exit 2. When that was the last window the `syncWindows:`
key goes with it, together with the two lines `insert` writes above it when it
creates the key, so insert followed by remove returns the file byte for byte.
The removal hash is over {"action":"remove","project":P,"window":W}: an approval
to add a window cannot be spent as an approval to lift it, or the reverse.

Exit: 0 done, 2 refused or unreadable.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

import yaml


class Refuse(Exception):
    pass


class _Indented(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def canonical(window: object) -> str:
    if not isinstance(window, dict):
        raise Refuse("the window must be a JSON object")
    return json.dumps(window, sort_keys=True, separators=(",", ":"))


def window_hash(project: str, window: object) -> str:
    """sha256 of {"project": P, "window": W}, canonical. The project is in the
    hashed bytes so one approval cannot be replayed against another project."""
    if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project):
        raise Refuse("the project must be a lowercase DNS-style name")
    body = json.dumps({"project": project, "window": json.loads(canonical(window))},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def removal_hash(project: str, window: object) -> str:
    """sha256 of {"action":"remove","project":P,"window":W}, canonical. The
    action is in the hashed bytes, so an approval to add the window is a
    different number from an approval to remove it."""
    if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project):
        raise Refuse("the project must be a lowercase DNS-style name")
    body = json.dumps({"action": "remove", "project": project, "window": json.loads(canonical(window))},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _item_lines(window: dict, indent: int) -> list[str]:
    dumped = yaml.dump([window], Dumper=_Indented, sort_keys=False, default_flow_style=False)
    pad = " " * indent
    return [pad + ln if ln else ln for ln in dumped.rstrip("\n").split("\n")]


_KEY = re.compile(r"^  syncWindows:(.*)$")
# `{{ .Values.x }}` is a value and fine at the end; `{{- end }}` and the like
# close a block, and text appended after them would land outside it.
_CONTROL = re.compile(r"^\s*\{\{-?\s*(end|else|if|range|with|define|template|include|block)\b")


def insert(text: str, window: dict) -> str:
    canonical(window)
    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise Refuse("empty file")
    if _CONTROL.match(lines[-1]):
        raise Refuse("the last line is a template control action; not appending after it")
    starts = [i for i, ln in enumerate(lines) if _KEY.match(ln)]
    if len(starts) > 1:
        raise Refuse("more than one `  syncWindows:` key")
    if not starts:
        out = lines + ["", "  # Sync windows (proposal issue-2828): deny-only, never in project default."]
        out += ["  syncWindows:"] + _item_lines(window, 4)
        return "\n".join(out) + "\n"
    i = starts[0]
    rest = _KEY.match(lines[i]).group(1).strip()
    if rest and not rest.startswith("#"):
        raise Refuse(f"`syncWindows:` has an inline value ({rest!r}); only a block list is edited")
    end = i + 1
    last_item = i
    while end < len(lines):
        ln = lines[end]
        if ln.strip() == "":
            end += 1
            continue
        indent = len(ln) - len(ln.lstrip(" "))
        if indent <= 2:
            break
        last_item = end
        end += 1
    if last_item == i:
        raise Refuse("`syncWindows:` has no block items; refusing to guess its shape")
    out = lines[: last_item + 1] + _item_lines(window, 4) + lines[last_item + 1:]
    return "\n".join(out) + "\n"


_CREATED_COMMENT = "  # Sync windows (proposal issue-2828): deny-only, never in project default."


def remove(text: str, window: dict) -> str:
    """Delete the one window block equal to `window`; refuse anything else."""
    canonical(window)
    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    starts = [i for i, ln in enumerate(lines) if _KEY.match(ln)]
    if len(starts) != 1:
        raise Refuse("expected exactly one `  syncWindows:` key, found %d" % len(starts))
    i = starts[0]
    rest = _KEY.match(lines[i]).group(1).strip()
    if rest and not rest.startswith("#"):
        raise Refuse(f"`syncWindows:` has an inline value ({rest!r}); only a block list is edited")
    end = i + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() != "" and len(ln) - len(ln.lstrip(" ")) <= 2:
            break
        end += 1
    # The block ends at the first line indented two or less. A template action
    # there (a column-0 `{{- if }}` followed by more items) would end it early,
    # so that more windows sit past it than this function sees; it is not a
    # guess to be made, so it is refused.
    if end < len(lines) and _CONTROL.match(lines[end]):
        raise Refuse("a template action ends `syncWindows:`; items may follow it, not guessing")
    block = lines[i + 1:end]
    if not block:
        raise Refuse("`syncWindows:` has no block items")
    if any(b.strip() == "" or b.lstrip().startswith("#") for b in block):
        raise Refuse("a blank or comment line inside `syncWindows:`; not guessing item boundaries")
    item_indent = min(len(b) - len(b.lstrip(" ")) for b in block)
    if not all((b[item_indent:].startswith("- ") or len(b) - len(b.lstrip(" ")) > item_indent) for b in block):
        raise Refuse("`syncWindows:` items are not a plain block list")
    item_starts = [k for k, b in enumerate(block) if len(b) - len(b.lstrip(" ")) == item_indent]
    if not item_starts or item_starts[0] != 0 or not all(block[k].lstrip().startswith("- ") for k in item_starts):
        raise Refuse("`syncWindows:` items are not a plain block list")
    bounds = list(zip(item_starts, item_starts[1:] + [len(block)]))
    want = json.loads(canonical(window))
    hits = []
    for a, b in bounds:
        chunk = "\n".join(x[item_indent:] for x in block[a:b])
        try:
            parsed = yaml.safe_load(chunk)
        except yaml.YAMLError as e:
            raise Refuse(f"an item of `syncWindows:` does not parse: {e}") from e
        if not (isinstance(parsed, list) and len(parsed) == 1):
            raise Refuse("an item of `syncWindows:` is not a single list entry")
        if parsed[0] == want:
            hits.append((a, b))
    if len(hits) != 1:
        raise Refuse("the window matches %d items of `syncWindows:`, need exactly 1" % len(hits))
    a, b = hits[0]
    if len(bounds) > 1:
        out = lines[:i + 1 + a] + lines[i + 1 + b:]
    else:
        # The last window: drop the key, and the two lines insert writes above
        # it, but only when they are exactly what insert writes.
        lo = i
        if i >= 2 and lines[i - 1] == _CREATED_COMMENT and lines[i - 2] == "":
            lo = i - 2
        out = lines[:lo] + lines[end:]
    return "\n".join(out) + "\n"


def _selftest() -> int:
    ok = True

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        print(f"selftest {'ok  ' if cond else 'FAIL'} {label}")
        ok = ok and cond

    w = {"kind": "deny", "schedule": "0 22 * * 5", "duration": "48h", "applications": ["labs-bot"]}
    base = "apiVersion: v1\nspec:\n  description: x\n  sourceRepos:\n    - {{ .Values.r }}\n"
    out = insert(base, w)
    parsed = yaml.safe_load(out.replace("{{ .Values.r }}", "r"))
    check("append creates a block that parses to exactly the window", parsed["spec"]["syncWindows"] == [w])
    check("the template action is untouched", "- {{ .Values.r }}" in out)
    out2 = insert(out, {**w, "applications": ["labs-web"]})
    p2 = yaml.safe_load(out2.replace("{{ .Values.r }}", "r"))["spec"]["syncWindows"]
    check("a second window is appended after the first", [x["applications"] for x in p2] == [["labs-bot"], ["labs-web"]])
    mid = "spec:\n  syncWindows:\n    - kind: deny\n      schedule: '0 1 * * *'\n      duration: 1h\n      applications: [a]\n  orphanedResources:\n    warn: false\n"
    p3 = yaml.safe_load(insert(mid, w))
    check("an existing block is extended and later keys stay", len(p3["spec"]["syncWindows"]) == 2 and p3["spec"]["orphanedResources"] == {"warn": False})
    for label, text in (("inline empty list", "spec:\n  syncWindows: []\n"),
                        ("flow value", "spec:\n  syncWindows: [{kind: deny}]\n"),
                        ("duplicate key", "spec:\n  syncWindows:\n    - a: 1\n  syncWindows:\n    - b: 2\n"),
                        ("template action last", "spec:\n  a: 1\n{{- end }}\n"),
                        ("empty file", "\n\n"),
                        ("key without items", "spec:\n  syncWindows:\n  other: 1\n")):
        try:
            insert(text, w)
            check(f"refused: {label}", False)
        except Refuse:
            check(f"refused: {label}", True)
    try:
        insert(base, ["not", "an", "object"])
        check("refused: window that is not an object", False)
    except Refuse:
        check("refused: window that is not an object", True)
    # insert then remove returns the file byte for byte, for the created key and
    # for a list of more than one.
    check("insert then remove is the identity (key created)", remove(insert(base, w), w) == base)
    two = insert(insert(base, w), {**w, "applications": ["labs-web"]})
    check("removing the first of two leaves the second",
          yaml.safe_load(remove(two, w).replace("{{ .Values.r }}", "r"))["spec"]["syncWindows"] == [{**w, "applications": ["labs-web"]}])
    check("removing the second of two is the file with one window", remove(two, {**w, "applications": ["labs-web"]}) == insert(base, w))
    check("the template action is untouched by remove", "- {{ .Values.r }}" in remove(two, w))
    check("remove matches by value, not key order", remove(insert(base, w), dict(reversed(list(w.items())))) == base)
    for label, text, win in (
            ("no such window", insert(base, w), {**w, "duration": "2h"}),
            ("same window with another list order", insert(base, {**w, "applications": ["a", "b"]}), {**w, "applications": ["b", "a"]}),
            ("a window with an extra key", insert(base, {**w, "manualSync": True}), w),
            ("two identical windows", insert(insert(base, w), w), w),
            ("no syncWindows key", base, w),
            ("inline empty list", "spec:\n  syncWindows: []\n", w),
            ("a comment inside the block", "spec:\n  syncWindows:\n    # c\n    - kind: deny\n", w),
            ("a blank line inside the block", insert(insert(base, w), w).replace("\n    - kind", "\n\n    - kind", 1), w),
            ("duplicate key", "spec:\n  syncWindows:\n    - a: 1\n  syncWindows:\n    - b: 2\n", w),
            ("a template action ends the block with items after it",
             insert(base, w) + "{{- if .Values.more }}\n    - kind: deny\n      schedule: '0 1 * * *'\n      duration: 1h\n      applications: [a]\n{{- end }}\n", w),
            ("unparseable item", "spec:\n  syncWindows:\n    - kind: [deny\n", w)):
        try:
            remove(text, win)
            check(f"remove refused: {label}", False)
        except Refuse:
            check(f"remove refused: {label}", True)
    try:
        remove(base, ["x"])
        check("remove refused: window that is not an object", False)
    except Refuse:
        check("remove refused: window that is not an object", True)
    check("removal hash differs from the add hash", removal_hash("apps", w) != window_hash("apps", w))
    check("removal hash does not depend on key order", removal_hash("apps", w) == removal_hash("apps", dict(reversed(list(w.items())))))
    check("removal hash changes with the project", removal_hash("apps", w) != removal_hash("platform", w))
    check("removal hash changes with the window", removal_hash("apps", w) != removal_hash("apps", {**w, "duration": "49h"}))
    a, b = window_hash("apps", w), window_hash("apps", dict(reversed(list(w.items()))))
    check("hash does not depend on key order", a == b and len(a) == 64)
    check("hash changes with the window", a != window_hash("apps", {**w, "duration": "49h"}))
    check("hash changes with the project", a != window_hash("platform", w))
    try:
        window_hash("Apps; rm", w)
        check("refused: malformed project name", False)
    except Refuse:
        check("refused: malformed project name", True)
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return _selftest()
    try:
        if len(argv) == 3 and argv[1] == "hash":
            print(window_hash(argv[2], json.load(sys.stdin)))
            return 0
        if len(argv) == 3 and argv[1] == "hash-remove":
            print(removal_hash(argv[2], json.load(sys.stdin)))
            return 0
        if len(argv) == 3 and argv[1] == "remove":
            window = json.load(sys.stdin)
            with open(argv[2], encoding="utf-8") as fh:
                text = fh.read()
            new = remove(text, window)
            with open(argv[2], "w", encoding="utf-8") as fh:
                fh.write(new)
            return 0
        if len(argv) == 3 and argv[1] == "insert":
            window = json.load(sys.stdin)
            with open(argv[2], encoding="utf-8") as fh:
                text = fh.read()
            new = insert(text, window)
            with open(argv[2], "w", encoding="utf-8") as fh:
                fh.write(new)
            return 0
    except (Refuse, OSError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
