#!/usr/bin/env python3
"""Guard the issue-2286 OBI spike sandbox (bootstrap values `obiSpike`).

Only while `obiSpike.enabled` is true, fail when:
  - teardownAfter is missing, malformed, past or more than 14 days out (the
    date logic of scripts/validate-eval-teardown-date.py is reused);
  - the image digest is empty or not sha256:<64 hex>;
  - `privileged: true` or SYS_ADMIN in capabilities.add while
    allowPrivileged is not true;
  - any capability in `add` is outside the pinned list;
  - a target is empty or contains a glob character;
  - any toleration is present.

While the flag is false the check passes whatever the other keys hold.

Usage:
  validate-obi-spike.py [--values FILE ...] [--today YYYY-MM-DD]
  validate-obi-spike.py --selftest
`--values` may repeat; later files are deep-merged over earlier ones, so CI
can validate bootstrap values plus the enabled overlay.
"""
from __future__ import annotations

import copy
import datetime
import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES_FILE = ROOT / "platform-gitops/bootstrap/values.yaml"

PINNED_CAPABILITIES = {"BPF", "PERFMON", "SYS_PTRACE", "DAC_READ_SEARCH", "CHECKPOINT_RESTORE"}
GLOB_CHARS = frozenset("*?[]{}")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_spec = importlib.util.spec_from_file_location(
    "validate_eval_teardown_date", ROOT / "scripts/validate-eval-teardown-date.py"
)
_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_eval)

PATH_ENABLED = ("obiSpike", "enabled")
PATH_TEARDOWN = ("obiSpike", "teardownAfter")


def deep_merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base.get(k), v) if k in base else v
        return out
    return over


def check_values(doc: dict, today: datetime.date) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return errors
    spike = doc.get("obiSpike")
    if not isinstance(spike, dict) or spike.get("enabled") is not True:
        return errors

    err = _eval._check_one(doc, PATH_ENABLED, PATH_TEARDOWN, today)
    if err:
        errors.append(err)

    image = spike.get("image") or {}
    digest = image.get("digest")
    if not digest or not DIGEST_RE.match(str(digest)):
        errors.append(f"obiSpike.image.digest={digest!r} must be sha256:<64 hex>")
    if not image.get("repository"):
        errors.append("obiSpike.image.repository is empty")

    sc = spike.get("securityContext") or {}
    allow = spike.get("allowPrivileged") is True
    add = (sc.get("capabilities") or {}).get("add") or []
    if sc.get("privileged") is True and not allow:
        errors.append("securityContext.privileged is true while allowPrivileged is false")
    if "SYS_ADMIN" in add and not allow:
        errors.append("SYS_ADMIN in capabilities.add while allowPrivileged is false")
    extra = sorted(set(add) - PINNED_CAPABILITIES)
    if extra:
        errors.append(f"capabilities.add outside the pinned list: {extra}")

    targets = spike.get("targets") or []
    if not targets:
        errors.append("obiSpike.targets is empty")
    for t in targets:
        ns = (t or {}).get("namespace") if isinstance(t, dict) else None
        dep = (t or {}).get("deployment") if isinstance(t, dict) else None
        if not ns or not dep:
            errors.append(f"target {t!r} has an empty namespace or deployment")
        elif GLOB_CHARS.intersection(str(ns) + str(dep)):
            errors.append(f"target {t!r} contains a glob character")

    if spike.get("tolerations"):
        errors.append("obiSpike.tolerations must not be set")
    return errors


def _good(today: datetime.date) -> dict:
    return {
        "obiSpike": {
            "enabled": True,
            "teardownAfter": (today + datetime.timedelta(days=7)).isoformat(),
            "image": {"repository": "ghcr.io/example/obi", "digest": "sha256:" + "a" * 64},
            "allowPrivileged": False,
            "securityContext": {
                "privileged": False,
                "capabilities": {"drop": ["ALL"], "add": sorted(PINNED_CAPABILITIES)},
            },
            "targets": [{"namespace": "labs", "deployment": "x"}],
        }
    }


def selftest() -> int:
    today = datetime.date(2026, 10, 31)
    d = datetime.timedelta
    ok = True

    def case(label, mutate, should_pass):
        nonlocal ok
        doc = _good(today)
        mutate(doc["obiSpike"])
        passed = not check_values(doc, today)
        if passed != should_pass:
            ok = False
            print(f"selftest FAIL: {label}: expected pass={should_pass}, got {passed}", file=sys.stderr)

    def allow_privileged(s):
        s["securityContext"]["privileged"] = True
        s["allowPrivileged"] = True

    case("valid enabled spike passes", lambda s: None, True)
    case("disabled with junk passes", lambda s: s.update(enabled=False, teardownAfter="", targets=["*"]), True)
    case("missing teardownAfter fails", lambda s: s.update(teardownAfter=""), False)
    case("past teardownAfter fails", lambda s: s.update(teardownAfter=(today - d(days=1)).isoformat()), False)
    case("15 days out fails", lambda s: s.update(teardownAfter=(today + d(days=15)).isoformat()), False)
    case("14 days out passes", lambda s: s.update(teardownAfter=(today + d(days=14)).isoformat()), True)
    case("empty digest fails", lambda s: s["image"].update(digest=""), False)
    case("tag-style digest fails", lambda s: s["image"].update(digest="v1.0.0"), False)
    case("privileged without allow fails", lambda s: s["securityContext"].update(privileged=True), False)
    case("privileged with allow passes", allow_privileged, True)
    case("SYS_ADMIN without allow fails", lambda s: s["securityContext"]["capabilities"]["add"].append("SYS_ADMIN"), False)
    case("capability outside pinned list fails", lambda s: s["securityContext"]["capabilities"]["add"].append("NET_RAW"), False)
    case("empty target namespace fails", lambda s: s["targets"].append({"namespace": "", "deployment": "x"}), False)
    case("empty target deployment fails", lambda s: s["targets"].append({"namespace": "labs", "deployment": ""}), False)
    case("globbed target fails", lambda s: s["targets"].append({"namespace": "labs", "deployment": "obi-*"}), False)
    case("toleration fails", lambda s: s.update(tolerations=[{"operator": "Exists"}]), False)

    if not ok:
        return 1
    print("selftest OK: every obiSpike failure case fires, and the disabled/default state passes")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    files: list[Path] = []
    today = datetime.date.today()
    i = 0
    while i < len(argv):
        if argv[i] == "--values" and i + 1 < len(argv):
            files.append(Path(argv[i + 1]))
            i += 2
        elif argv[i] == "--today" and i + 1 < len(argv):
            today = datetime.date.fromisoformat(argv[i + 1])
            i += 2
        else:
            print(f"unknown or incomplete argument: {argv[i]}", file=sys.stderr)
            return 2
    files = files or [VALUES_FILE]
    doc: dict = {}
    for f in files:
        if not f.is_file():
            print(f"{f} not found -- refusing to pass vacuously", file=sys.stderr)
            return 2
        doc = deep_merge(doc, yaml.safe_load(f.read_text()) or {})
    errors = check_values(copy.deepcopy(doc), today)
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print("OK: obiSpike is closed or within policy")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
