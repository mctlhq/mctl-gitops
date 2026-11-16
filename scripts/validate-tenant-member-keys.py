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

An entry may also say what the portal names its catalog User by:
`catalogKey: principal` (by principalId; a self-service customer account,
mctl-web docs/plans/site-onboarding-review.md stage C2) or `login` (by
userId, the default when absent). Any other value is a violation: the portal
would fall back to the login, which the GitHub login's next holder signs in
as.

An entry without a `userId` (listed by principalId alone, so that its
holder's GitHub login is not published in this public repository) is
governed by PID_ONLY_ALLOWED below:
- False (rule c, now): refused outright. mctl-api's identity hook answers
  503 to every new customer account while any such entry exists, until
  mctlhq/mctl-api#1075 is released.
- True (rule b, after that release): allowed only with `catalogKey:
  principal`. Without it the portal's TenantSync keys the catalog User by
  the missing login, so it skips the entry with only a warning and the
  member silently loses the portal.

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

# The catalog keys the portal understands (tenant-backend TenantSync).
CATALOG_KEYS = ("login", "principal")

# Whether an entry may omit userId (see the module docstring). Flip this one
# line to True once a mctl-api release containing mctlhq/mctl-api#1075 runs
# in production; before that, a pid-only entry makes every new customer
# sign-up fail. The selftest checks both settings either way.
PID_ONLY_ALLOWED = False


def _members(scope: str, members: object, pid_only_allowed: bool) -> list[str]:
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
        if "catalogKey" in member and member["catalogKey"] not in CATALOG_KEYS:
            found.append(f"{where}: catalogKey {member['catalogKey']!r} is not one of {', '.join(CATALOG_KEYS)}")
        if not member.get("userId"):
            if not pid_only_allowed:
                found.append(
                    f"{where}: no userId; listing a member by principalId alone needs "
                    "mctlhq/mctl-api#1075 released first (PID_ONLY_ALLOWED)"
                )
            elif member.get("catalogKey") != "principal":
                found.append(f"{where}: no userId, so it needs catalogKey: principal or the portal drops it")
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


def violations(root: Path, pid_only_allowed: bool = PID_ONLY_ALLOWED) -> list[str]:
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
        found += _members(f"{rel}: tenant", tenant.get("members"), pid_only_allowed)
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
            found += _members(f"{rel}: team {team.get('name', j)}", team.get("members"), pid_only_allowed)
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
        f"    - userId: bob\n      principalId: {PID_B}\n      role: developer\n      catalogKey: principal\n"
        "  teams:\n"
        "    - name: web\n"
        "      members:\n"
        f"        - userId: alice\n          principalId: {PID_A}\n          role: owner\n"
    )
    team_line = f"        - userId: alice\n          principalId: {PID_A}\n"
    pid_only = good.replace("    - userId: bob\n      principalId", "    - principalId")
    # Entries without userId: (name, body, fires under rule c, fires under rule b).
    pid_only_cases: list[tuple[str, str, bool, bool]] = [
        ("pid-only member with catalogKey principal", pid_only, True, False),
        ("pid-only member with empty userId", good.replace("userId: bob", 'userId: ""'), True, False),
        ("pid-only member without catalogKey", pid_only.replace("\n      catalogKey: principal", ""), True, True),
        ("pid-only member with catalogKey login", pid_only.replace("catalogKey: principal", "catalogKey: login"), True, True),
        ("pid-only team member without catalogKey", good.replace(team_line, f"        - principalId: {PID_A}\n"), True, True),
        (
            "pid-only team member with catalogKey principal",
            good.replace(team_line, f"        - principalId: {PID_A}\n          catalogKey: principal\n"),
            True,
            False,
        ),
    ]
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
        ("catalogKey login", good.replace("catalogKey: principal", "catalogKey: login"), False),
        ("unknown catalogKey", good.replace("catalogKey: principal", "catalogKey: Principal"), True),
        ("empty catalogKey", good.replace("catalogKey: principal", 'catalogKey: ""'), True),
        ("null catalogKey", good.replace("catalogKey: principal", "catalogKey: null"), True),
        ("members not a list", "tenant:\n  name: t\n  members:\n    userId: alice\n", True),
        ("member not a mapping", "tenant:\n  name: t\n  members:\n    - alice\n", True),
        ("teams not a list", good.replace("  teams:\n    - name: web\n", "  teams:\n    web:\n"), True),
        ("no tenant mapping", "name: t\n", True),
        ("unparseable", "tenant: [\n", True),
        ("values.yaml missing", None, True),
    ]
    # Every case runs under both settings of PID_ONLY_ALLOWED, so flipping it
    # never ships an unproven rule.
    runs = [(n, b, f, f) for n, b, f in cases] + pid_only_cases
    with tempfile.TemporaryDirectory() as d:
        for name, body, fire_c, fire_b in runs:
            for allowed, should_fire in ((False, fire_c), (True, fire_b)):
                root = Path(d) / (re.sub(r"\W+", "-", name) + f"-{allowed}")
                tenant = root / TENANTS / "t"
                tenant.mkdir(parents=True)
                if body is not None:
                    (tenant / "values.yaml").write_text(body)
                try:
                    found = violations(root, pid_only_allowed=allowed)
                except Exception as exc:  # noqa: BLE001 - a crash is the failure being tested for
                    print(f"selftest FAIL: case {name!r} crashed the scan: {exc}", file=sys.stderr)
                    return 1
                if bool(found) != should_fire:
                    print(
                        f"selftest FAIL: case {name!r} (PID_ONLY_ALLOWED={allowed}) "
                        f"expected fire={should_fire}, got {found}",
                        file=sys.stderr,
                    )
                    return 1
        # Observing nothing is not a clean result.
        empty = Path(d) / "empty"
        (empty / TENANTS).mkdir(parents=True)
        if not violations(empty) or not violations(Path(d) / "nowhere"):
            print("selftest FAIL: an empty or missing tenants directory passed", file=sys.stderr)
            return 1
    print(
        "selftest OK: detector fires on a missing, empty, malformed or repeated principalId, "
        "on an unknown catalogKey, on a member without userId (refused outright, or without "
        "catalogKey: principal once PID_ONLY_ALLOWED), "
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
