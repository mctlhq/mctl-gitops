#!/usr/bin/env python3
"""Fail when a tenant member entry carries no canonical principal id.

mctl-api authorizes tenant access by canonical principal once
TENANT_AUTHZ_MODE=principal (mctlhq/mctl-api#377): a member entry in
platform-gitops/tenants/<tenant>/values.yaml grants by its `principalId`
and by nothing else. An entry with only a `userId` (a GitHub login) still
works under legacy authorization, so nothing notices it is missing — until
the switch, when that member silently loses the tenant.

So every member entry, at tenant level and in every team, must carry a
`principalId` of the exact shape mctl-api accepts ("prn_" and 26 Crockford
base32 characters; ValidPrincipalID in internal/gitops), and no list may
name one principal twice: mctl-api refuses to read a tenant whose list
contradicts itself, which in principal mode locks out every member of it.

A file that cannot be read or parsed is a violation, not a skip, and so is
finding no tenant at all: a check that observed nothing has not observed a
clean repository.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TENANTS = Path("platform-gitops/tenants")
ISSUE = "mctlhq/mctl-api#377"

# Kept identical to mctl-api's principalIDRE (internal/gitops).
PRINCIPAL_ID = re.compile(r"prn_[0-9A-HJKMNP-TV-Z]{26}")


def _members(scope: str, members: object) -> list[str]:
    """Violations in one member list."""
    if members is None:
        return []
    if not isinstance(members, list):
        return [f"{scope}: members is {type(members).__name__}, not a list"]
    found: list[str] = []
    seen: set[str] = set()
    for i, member in enumerate(members):
        where = f"{scope} member {i}"
        if not isinstance(member, dict):
            found.append(f"{where}: not a mapping")
            continue
        if member.get("userId"):
            where += f" ({member['userId']})"
        pid = member.get("principalId")
        if pid is None or pid == "":
            found.append(f"{where}: no principalId")
            continue
        # fullmatch, not match with $: "$" also matches before a trailing
        # newline, and a block scalar can end in one.
        if not isinstance(pid, str) or not PRINCIPAL_ID.fullmatch(pid):
            found.append(f"{where}: malformed principalId {pid!r}")
            continue
        if pid in seen:
            found.append(f"{scope}: principalId {pid} listed more than once")
        seen.add(pid)
    return found


def violations(root: Path) -> list[str]:
    """Every member entry under root's tenants that principal mode cannot use."""
    tenants_dir = root / TENANTS
    if not tenants_dir.is_dir():
        return [f"{tenants_dir} does not exist"]
    files = sorted(
        d / "values.yaml" for d in tenants_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    if not files:
        return [f"no tenant directories under {tenants_dir}; nothing was checked"]
    found: list[str] = []
    for path in files:
        rel = path.relative_to(root)
        try:
            doc = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            found.append(f"{rel}: cannot be read: {exc}")
            continue
        tenant = doc.get("tenant") if isinstance(doc, dict) else None
        if not isinstance(tenant, dict):
            found.append(f"{rel}: no tenant mapping; cannot check its members")
            continue
        found += _members(f"{rel}: tenant", tenant.get("members"))
        teams = tenant.get("teams")
        if teams is None:
            continue
        if not isinstance(teams, list):
            found.append(f"{rel}: teams is {type(teams).__name__}, not a list")
            continue
        for j, team in enumerate(teams):
            if not isinstance(team, dict):
                found.append(f"{rel}: team {j} is not a mapping")
                continue
            found += _members(f"{rel}: team {team.get('name', j)}", team.get("members"))
    return found


PID_A = "prn_01M39HRB7JRXZ2PHW5VVB695YZ"
PID_B = "prn_01M45DR1GWC87109EH88VBJX25"


def selftest() -> int:
    """Prove the detector fires on every unusable entry and stays quiet on keyed ones."""
    good = (
        "tenant:\n"
        "  name: t\n"
        "  members:\n"
        f"    - userId: alice\n      principalId: {PID_A}\n      role: owner\n"
        f"    - principalId: {PID_B}\n      role: developer\n"
        "  teams:\n"
        "    - name: web\n"
        "      members:\n"
        f"        - userId: alice\n          principalId: {PID_A}\n          role: owner\n"
    )
    team_line = f"        - userId: alice\n          principalId: {PID_A}\n"
    cases: list[tuple[str, str | None, bool]] = [
        # good also lists PID_A at tenant level and in a team, which is allowed.
        ("every entry keyed", good, False),
        ("no members at all", "tenant:\n  name: t\n", False),
        ("empty member list", "tenant:\n  name: t\n  members: []\n", False),
        ("tenant member without principalId", good.replace(f"      principalId: {PID_A}\n", "", 1), True),
        ("team member without principalId", good.replace(team_line, "        - userId: alice\n"), True),
        ("empty principalId", good.replace(f"principalId: {PID_B}", 'principalId: ""'), True),
        ("lowercase principalId", good.replace(PID_B, PID_B.lower()), True),
        ("principalId with an excluded letter", good.replace(PID_B, PID_B[:-1] + "I"), True),
        ("principalId one character short", good.replace(PID_B, PID_B[:-1]), True),
        ("principalId as a number", good.replace(f"principalId: {PID_B}", "principalId: 42"), True),
        (
            "principalId with a trailing newline",
            good.replace(f"principalId: {PID_B}", f"principalId: |\n        {PID_B}"),
            True,
        ),
        ("one principal twice in a list", good.replace(PID_B, PID_A), True),
        ("members not a list", "tenant:\n  name: t\n  members:\n    userId: alice\n", True),
        ("member not a mapping", "tenant:\n  name: t\n  members:\n    - alice\n", True),
        ("teams not a list", good.replace("  teams:\n    - name: web\n", "  teams:\n    web:\n"), True),
        ("no tenant mapping", "name: t\n", True),
        ("unparseable", "tenant: [\n", True),
        ("values.yaml missing", None, True),
    ]
    with tempfile.TemporaryDirectory() as d:
        for name, body, should_fire in cases:
            root = Path(d) / re.sub(r"\W+", "-", name)
            tenant = root / TENANTS / "t"
            tenant.mkdir(parents=True)
            if body is not None:
                (tenant / "values.yaml").write_text(body)
            try:
                found = violations(root)
            except Exception as exc:  # noqa: BLE001 - a crash is the failure being tested for
                print(f"selftest FAIL: case {name!r} crashed the scan: {exc}", file=sys.stderr)
                return 1
            if bool(found) != should_fire:
                print(f"selftest FAIL: case {name!r} expected fire={should_fire}, got {found}", file=sys.stderr)
                return 1
        # Observing nothing is not a clean result.
        empty = Path(d) / "empty"
        (empty / TENANTS).mkdir(parents=True)
        if not violations(empty) or not violations(Path(d) / "nowhere"):
            print("selftest FAIL: an empty or missing tenants directory passed", file=sys.stderr)
            return 1
    print(
        "selftest OK: detector fires on a missing, empty, malformed or repeated principalId, "
        "on unreadable structure and on an empty tenants directory; stays quiet on keyed entries"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    found = violations(ROOT)
    if found:
        print(f"Tenant member entries principal-mode authorization cannot use ({ISSUE}):", file=sys.stderr)
        for line in found:
            print(f"  - {line}", file=sys.stderr)
        print(
            "Every member needs `principalId: prn_...`, the principal mctl-api resolves "
            "the person to; see docs/principals.md in mctlhq/mctl-api.",
            file=sys.stderr,
        )
        return 1
    print("OK: every tenant member entry carries a principalId")
    return 0


if __name__ == "__main__":
    sys.exit(main())
