#!/usr/bin/env python3
"""Fail-closed release gate for grouped worker Deployments (mctl-agents#1007).

  release-gate.py check  --files F... --new-tag T   before a bump writes
  release-gate.py verify                            whole tree (CI, post-rebase)
  release-gate.py --selftest

Exit 0 = pass, 6 = refused. Anything that cannot be observed (gate missing or
malformed, a file or key absent, a tag that is not X.Y.Z) is a refusal:
"could not observe" is never "observed fine".
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = "platform-gitops/release-gates.yaml"
REFUSED = 6
# ASCII digits only, no leading zeros: `\d` accepts Unicode digits and "01".
_N = r"(0|[1-9][0-9]*)"
SEMVER = re.compile(rf"{_N}\.{_N}\.{_N}", re.ASCII)


def _semver(tag: Any) -> tuple[int, int, int] | None:
    m = SEMVER.fullmatch(str(tag)) if tag is not None else None
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def _load(root: Path, rel: str) -> Any:
    return yaml.safe_load((root / rel).read_text())


def _dig(doc: Any, key: str) -> Any:
    for part in key.split("."):
        if not isinstance(doc, dict) or part not in doc:
            raise KeyError(key)
        doc = doc[part]
    return doc


def _gates(root: Path) -> list[dict]:
    doc = _load(root, GATE)
    gates = doc.get("gates") if isinstance(doc, dict) else None
    if not isinstance(gates, list) or not gates:
        raise ValueError("no gates list")
    for g in gates:
        if not (isinstance(g, dict) and g.get("name") and isinstance(g.get("paths"), list) and g["paths"]):
            raise ValueError(f"malformed gate {g!r}")
        if _semver(g.get("min_tag")) is None:
            raise ValueError(f"gate {g.get('name')}: min_tag is not X.Y.Z")
        for r in g.get("requires") or []:
            if not (isinstance(r, dict) and {"path", "key", "equals"} <= set(r) and r["path"] in g["paths"]):
                raise ValueError(f"gate {g['name']}: malformed requires {r!r}")
    return gates


def problems(root: Path, files: list[str] | None, new_tag: str | None) -> list[str]:
    """Every reason to refuse. `files=None` is verify mode (whole tree)."""
    try:
        gates = _gates(root)
    except Exception as exc:  # noqa: BLE001 - unreadable gate is a refusal
        return [f"UNKNOWN: gate {GATE} unreadable: {type(exc).__name__}: {exc}"]
    out: list[str] = []
    for g in gates:
        paths = g["paths"]
        touched = paths if files is None else [p for p in paths if p in files]
        if not touched:
            continue
        if files is not None:
            if sorted(touched) != sorted(paths):
                missing = sorted(set(paths) - set(touched))
                out.append(f"{g['name']}: partial bump, missing {missing}")
            floor = _semver(g["min_tag"])
            nt = _semver(new_tag)
            if nt is None:
                out.append(f"{g['name']}: new tag {new_tag!r} is not X.Y.Z, cannot compare to the floor")
            elif nt < floor:  # type: ignore[operator]
                out.append(f"{g['name']}: new tag {new_tag} is below the floor {g['min_tag']}")
        tags: dict[str, Any] = {}
        for p in touched:
            try:
                doc = _load(root, p)
                tag = _dig(doc, "image.tag")
                if g.get("repository") and _dig(doc, "image.repository") != g["repository"]:
                    out.append(f"{p}: image.repository is {_dig(doc, 'image.repository')!r}, gate says {g['repository']!r}")
                tags[p] = tag
            except Exception as exc:  # noqa: BLE001
                out.append(f"UNKNOWN: {p} image.tag unreadable: {type(exc).__name__}")
                continue
            cur = _semver(tag)
            if cur is None:
                out.append(f"{p}: current tag {tag!r} is not X.Y.Z")
            elif files is None and cur < _semver(g["min_tag"]):  # type: ignore[operator]
                out.append(f"{p}: tag {tag} is below the floor {g['min_tag']}")
        # The group moves together: after a bump, and in the tree, the tags
        # must be equal. A glob that silently skipped one file (no image
        # pattern matched) leaves exactly this state.
        if len({str(t) for t in tags.values()}) > 1:
            out.append(f"{g['name']}: tags differ across the group: {tags}")
        for r in g.get("requires") or []:
            if r["path"] not in touched:
                continue
            try:
                got = _dig(_load(root, r["path"]), r["key"])
            except Exception as exc:  # noqa: BLE001
                out.append(f"UNKNOWN: {r['path']} {r['key']} unreadable: {type(exc).__name__}")
                continue
            if got != r["equals"]:
                out.append(f"{r['path']}: {r['key']} is {got!r}, requires {r['equals']!r}")
    return out


def run(root: Path, files: list[str] | None, new_tag: str | None) -> int:
    found = problems(root, files, new_tag)
    for line in found:
        print(f"::error::release gate: {line}", file=sys.stderr)
    if found:
        return REFUSED
    print("release gate: pass")
    return 0


# -- selftest: green on a converged tree, red on every deliberate mutation ----

_P = [
    "platform-gitops/services/admins/mctl-agents-worker/values.yaml",
    "platform-gitops/services/admins/mctl-agents-worker-exec/values.yaml",
    "platform-gitops/services/admins/mctl-agents-worker-implement/values.yaml",
]


def _tree(d: Path, *, tags=("1.117.0",) * 3, strategy: str | None = "Recreate", gate: str | None = None,
          skip: str | None = None):
    for p, t in zip(_P, tags):
        f = d / p
        f.parent.mkdir(parents=True, exist_ok=True)
        if p == skip:
            continue
        body = {"image": {"tag": t, "repository": "ghcr.io/x/y"}}
        if p == _P[0] and strategy is not None:
            body["strategy"] = {"type": strategy}
        f.write_text(yaml.safe_dump(body))
    g = d / GATE
    g.parent.mkdir(parents=True, exist_ok=True)
    g.write_text(
        gate
        if gate is not None
        else yaml.safe_dump(
            {"gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0", "repository": "ghcr.io/x/y",
                        "requires": [{"path": _P[0], "key": "strategy.type", "equals": "Recreate"}]}]}
        )
    )


def selftest() -> int:
    cases: list[tuple[str, dict, list[str] | None, str | None, bool]] = [
        ("converged bump", {}, _P, "1.118.0", True),
        ("converged verify", {}, None, None, True),
        ("unrelated file is not gated", {}, ["platform-gitops/services/x/values.yaml"], "0.0.1", True),
        ("partial bump", {}, _P[:2], "1.118.0", False),
        ("tag below floor", {}, _P, "1.116.0", False),
        ("non-semver new tag", {}, _P, "latest", False),
        ("Recreate removed", {"strategy": "RollingUpdate"}, _P, "1.118.0", False),
        ("tags differ across the group (verify)", {"tags": ("1.118.0", "1.117.0", "1.118.0")}, None, None, False),
        ("numeric not string floor", {}, _P, "1.99.0", False),
        ("leading zero tag", {}, _P, "01.118.0", False),
        ("unicode digit tag", {}, _P, "1.\u0661\u0661\u0668.0", False),
        ("prerelease suffix", {}, _P, "1.118.0-rc.1", False),
        ("required key absent", {"strategy": None}, _P, "1.118.0", False),
        ("Recreate removed (verify)", {"strategy": "RollingUpdate"}, None, None, False),
        ("current tag below floor (verify)", {"tags": ("1.116.0",) * 3}, None, None, False),
        ("other image at a high tag", {"gate": "REPO"}, _P, "1.118.0", False),
        ("requires names a file outside the group", {"gate": "OUTSIDE"}, _P, "1.118.0", False),
        ("gate file malformed", {"gate": "gates: nope"}, _P, "1.118.0", False),
        ("gate file not yaml", {"gate": ": : :"}, None, None, False),
        ("listed file missing", {"skip": _P[1]}, _P, "1.118.0", False),
    ]
    bad = []
    for name, kw, files, tag, want_pass in cases:
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            if kw.get("gate") == "REPO":
                kw = {"gate": yaml.safe_dump({"gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0",
                                                         "repository": "ghcr.io/other/img"}]})}
            if kw.get("gate") == "OUTSIDE":
                kw = {"gate": yaml.safe_dump({"gates": [{"name": "g", "paths": _P, "min_tag": "1.117.0",
                                                         "requires": [{"path": "elsewhere.yaml", "key": "a", "equals": 1}]}]})}
            _tree(d, **kw)
            if name == "gate file missing":
                (d / GATE).unlink()
            rc = 0 if not problems(d, files, tag) else REFUSED
        if (rc == 0) != want_pass:
            bad.append(name)
    with tempfile.TemporaryDirectory() as t:  # gate absent entirely
        d = Path(t)
        _tree(d)
        (d / GATE).unlink()
        if not problems(d, _P, "1.118.0"):
            bad.append("gate file missing")
    if bad:
        print(f"selftest FAILED: {bad}", file=sys.stderr)
        return 1
    print(f"selftest ok ({len(cases) + 1} cases)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--files", nargs="+", required=True)
    c.add_argument("--new-tag", required=True)
    sub.add_parser("verify")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "check":
        return run(Path(a.root), a.files, a.new_tag)
    if a.cmd == "verify":
        return run(Path(a.root), None, None)
    ap.error("a command or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
