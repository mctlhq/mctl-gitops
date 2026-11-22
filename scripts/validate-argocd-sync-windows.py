#!/usr/bin/env python3
"""Validate AppProject `spec.syncWindows` in rendered manifests.

Sync windows are the one Argo CD mechanism that can stop syncs on a schedule,
and a wrong one is expensive to undo: a window that matches root-app or
argocd-self-managed locks the very Applications a revert PR would need to
sync. This validator is the guard in front of any window reaching git
(proposal issue-2828, sections 2.1, 3.2 and 8.2). Today there are no windows
at all; the checks run over the render and the count is printed.

Rules (each violation carries a code):
  DEFAULT_PROJECT   no window in AppProject `default` (root-app and
                    argocd-self-managed live there).
  KIND_NOT_DENY     `kind` must be exactly `deny`. `allow` is refused: once
                    any allow matches an Application it is denied at every
                    instant outside the allow (Argo CanSync row 4); a missing
                    kind is refused too rather than defaulted.
  MANUAL_SYNC       `manualSync` must be absent or false. A true value opens
                    manual sync to every principal holding `sync`.
  NO_APPLICATIONS   `applications` must be a non-empty list of exact names;
                    a window selecting only by namespace or cluster is a
                    blanket scope.
  WILDCARD          no glob character (`*`, `?`, `[`) in applications,
                    namespaces or clusters.
  BAD_SCHEDULE      `schedule` is a 5-field cron, `duration` is a Go-style
                    duration (e.g. 2h, 90m, 1h30m).
  TIMEZONE          `timeZone` is not used (windows are UTC; see design 10).
  UNKNOWN_FIELD     only kind, schedule, duration, applications, namespaces,
                    clusters, manualSync are allowed.
  SHAPE             syncWindows is a list of mappings.

A document that cannot be read or has the wrong shape is exit 2, never a pass.

Usage:
  validate-argocd-sync-windows.py [--selftest] FILE ...
Exit: 0 clean, 1 violations, 2 unreadable input or selftest failure.
"""

from __future__ import annotations

import copy
import re
import sys

import yaml

ALLOWED = {"kind", "schedule", "duration", "applications", "namespaces", "clusters", "manualSync"}
GLOB = re.compile(r"[*?\[]")
DURATION = re.compile(r"^(\d+(\.\d+)?(h|m|s))+$")
CRON_FIELD = re.compile(r"^[\d*/,\-]+$")


class Unreadable(Exception):
    pass


def _cron_ok(s: object) -> bool:
    if not isinstance(s, str):
        return False
    parts = s.split()
    return len(parts) == 5 and all(CRON_FIELD.match(p) for p in parts)


def check_window(project: str, idx: int, w: object) -> list[str]:
    where = f"{project}.syncWindows[{idx}]"
    if not isinstance(w, dict):
        return [f"{where}: SHAPE window is not a mapping"]
    out: list[str] = []
    if project == "default":
        out.append(f"{where}: DEFAULT_PROJECT windows in project default can lock root-app")
    if w.get("kind") != "deny":
        out.append(f"{where}: KIND_NOT_DENY kind is {w.get('kind')!r}, only 'deny' is allowed")
    if w.get("manualSync") not in (None, False):
        out.append(f"{where}: MANUAL_SYNC manualSync must be absent or false")
    for k in sorted(set(w) - ALLOWED):
        out.append(f"{where}: UNKNOWN_FIELD {k!r}" + (" (timeZone is not used)" if k == "timeZone" else ""))
    if "timeZone" in w:
        out.append(f"{where}: TIMEZONE timeZone is not used")
    apps = w.get("applications")
    if not isinstance(apps, list) or not apps or not all(isinstance(a, str) and a for a in apps):
        out.append(f"{where}: NO_APPLICATIONS applications must be a non-empty list of names")
    for sel in ("applications", "namespaces", "clusters"):
        v = w.get(sel)
        if v is None:
            continue
        if not isinstance(v, list):
            out.append(f"{where}: SHAPE {sel} is not a list")
            continue
        for item in v:
            if not isinstance(item, str) or GLOB.search(item):
                out.append(f"{where}: WILDCARD {sel} entry {item!r} is not an exact name")
    if not _cron_ok(w.get("schedule")):
        out.append(f"{where}: BAD_SCHEDULE schedule {w.get('schedule')!r} is not a 5-field cron")
    d = w.get("duration")
    if not isinstance(d, str) or not DURATION.match(d):
        out.append(f"{where}: BAD_SCHEDULE duration {d!r} is not a duration like 2h or 1h30m")
    return out


def check_docs(docs: list[object]) -> tuple[list[str], int]:
    """Return (violations, window_count). Raises Unreadable on bad shape."""
    problems: list[str] = []
    count = 0
    for doc in docs:
        if not isinstance(doc, dict) or doc.get("kind") != "AppProject":
            continue
        name = (doc.get("metadata") or {}).get("name")
        if not isinstance(name, str) or not name:
            raise Unreadable("AppProject without metadata.name")
        spec = doc.get("spec")
        if not isinstance(spec, dict):
            raise Unreadable(f"AppProject {name}: spec is not a mapping")
        sw = spec.get("syncWindows")
        if sw is None:
            continue
        if not isinstance(sw, list):
            raise Unreadable(f"AppProject {name}: syncWindows is not a list")
        for i, w in enumerate(sw):
            count += 1
            problems.extend(check_window(name, i, w))
    return problems, count


def load(paths: list[str]) -> list[object]:
    docs: list[object] = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                docs.extend(d for d in yaml.safe_load_all(fh) if d is not None)
        except (OSError, yaml.YAMLError) as e:
            raise Unreadable(f"{p}: {e}") from e
    return docs


GOOD_WINDOW = {
    "kind": "deny",
    "schedule": "0 22 * * 5",
    "duration": "48h",
    "applications": ["labs-example"],
}


def _project(name: str, windows: list | None) -> dict:
    spec: dict = {"description": "x"}
    if windows is not None:
        spec["syncWindows"] = windows
    return {"apiVersion": "argoproj.io/v1alpha1", "kind": "AppProject",
            "metadata": {"name": name}, "spec": spec}


def selftest() -> int:
    ok = True

    def expect(label: str, docs: list, code: str | None) -> None:
        nonlocal ok
        try:
            problems, _ = check_docs(docs)
        except Unreadable:
            problems = ["UNREADABLE"]
        hit = (not problems) if code is None else any(code in p for p in problems)
        print(f"selftest {'ok  ' if hit else 'FAIL'} {label}")
        ok = ok and hit

    expect("no windows is clean", [_project("apps", None), _project("default", None)], None)
    expect("correct deny window is clean", [_project("apps", [copy.deepcopy(GOOD_WINDOW)])], None)

    def mut(**kw):
        w = copy.deepcopy(GOOD_WINDOW)
        for k, v in kw.items():
            if v is None:
                w.pop(k, None)
            else:
                w[k] = v
        return [_project("apps", [w])]

    expect("window in default is red", [_project("default", [copy.deepcopy(GOOD_WINDOW)])], "DEFAULT_PROJECT")
    expect("kind allow is red", mut(kind="allow"), "KIND_NOT_DENY")
    expect("missing kind is red", mut(kind=None), "KIND_NOT_DENY")
    expect("manualSync true is red", mut(manualSync=True), "MANUAL_SYNC")
    expect("manualSync false is clean", mut(manualSync=False), None)
    expect("namespace-only window is red", mut(applications=None, namespaces=["labs"]), "NO_APPLICATIONS")
    expect("empty applications is red", mut(applications=[]), "NO_APPLICATIONS")
    expect("wildcard application is red", mut(applications=["*"]), "WILDCARD")
    expect("glob namespace is red", mut(namespaces=["labs-*"]), "WILDCARD")
    expect("bad cron is red", mut(schedule="every friday"), "BAD_SCHEDULE")
    expect("bad duration is red", mut(duration="two days"), "BAD_SCHEDULE")
    expect("timeZone is red", mut(timeZone="Europe/Berlin"), "TIMEZONE")
    expect("unknown field is red", mut(foo=1), "UNKNOWN_FIELD")
    expect("non-mapping window is red", [_project("apps", ["x"])], "SHAPE")
    # Unreadable shape must be exit 2, not clean.
    try:
        check_docs([_project("apps", "oops")])
        print("selftest FAIL non-list syncWindows must be unreadable")
        ok = False
    except Unreadable:
        print("selftest ok   non-list syncWindows is unreadable")
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    args = argv[1:]
    run_self = "--selftest" in args
    paths = [a for a in args if a != "--selftest"]
    if run_self and selftest() != 0:
        print("selftest FAILED", file=sys.stderr)
        return 2
    if not paths:
        return 0 if run_self else 2
    try:
        problems, count = check_docs(load(paths))
    except Unreadable as e:
        print(f"unreadable: {e}", file=sys.stderr)
        return 2
    for p in problems:
        print(p)
    print(f"sync windows found: {count}; violations: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
