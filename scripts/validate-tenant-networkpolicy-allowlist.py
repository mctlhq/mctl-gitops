#!/usr/bin/env python3
"""Fail when the bootstrap chart renders a NetworkPolicy the admission policy would deny.

`mctl-tenant-networkpolicy-allowlist` (bootstrap/templates/system/
admission-policies.yaml) admits only a fixed list of NetworkPolicy names in
tenant namespaces. The bootstrap chart also places platform-owned policies in
tenant namespaces (admins, labs). A new one whose name is missing from that
list renders, lints and passes kubeconform, and is then rejected by the API
server at sync time, so root-app degrades and the policy never exists. That
happened on mctlhq/mctl-gitops#1484 and was caught only in review.

This check renders nothing itself: it reads a `helm template` output of the
bootstrap chart, takes the allowlist from the rendered
ValidatingAdmissionPolicy's CEL expression, and requires every NetworkPolicy
rendered into a tenant namespace to be on it. Tenant namespaces are derived
from platform-gitops/tenants/*/values.yaml the same way the tenant chart does
it: the tenant name, or `<tenant>-<team>` per team when teams are set.

An unreadable allowlist (policy absent, expression not in the expected shape)
is an error, never an empty list that everything fails against or passes.

Usage:
  validate-tenant-networkpolicy-allowlist.py RENDERED_BOOTSTRAP.yaml
  validate-tenant-networkpolicy-allowlist.py --selftest RENDERED_BOOTSTRAP.yaml
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TENANTS_DIR = ROOT / "platform-gitops" / "tenants"
POLICY_NAME = "mctl-tenant-networkpolicy-allowlist"


class CheckError(Exception):
    """The inputs could not be read; distinct from a violation."""


def tenant_namespaces() -> set[str]:
    namespaces: set[str] = set()
    values_files = sorted(TENANTS_DIR.glob("*/values.yaml"))
    if not values_files:
        raise CheckError(f"no tenant values found under {TENANTS_DIR}")
    for path in values_files:
        tenant = (yaml.safe_load(path.read_text()) or {}).get("tenant") or {}
        name = tenant.get("name") or path.parent.name
        teams = tenant.get("teams") or []
        if teams:
            namespaces.update(f"{name}-{team['name']}" for team in teams)
        else:
            namespaces.add(name)
    return namespaces


def allowlist(docs: list[dict]) -> set[str]:
    for doc in docs:
        if doc.get("kind") == "ValidatingAdmissionPolicy" and doc["metadata"]["name"] == POLICY_NAME:
            expressions = [v.get("expression", "") for v in doc["spec"].get("validations", [])]
            for expr in expressions:
                match = re.search(r"object\.metadata\.name\s+in\s+\[(.*?)\]", expr, re.S)
                if match:
                    names = set(re.findall(r"'([^']+)'", match.group(1)))
                    if names:
                        return names
            raise CheckError(f"{POLICY_NAME}: no `object.metadata.name in [...]` list in its validations")
    raise CheckError(f"{POLICY_NAME} not found in the rendered bootstrap chart")


def violations(docs: list[dict], tenants: set[str]) -> list[str]:
    allowed = allowlist(docs)
    found = []
    for doc in docs:
        if doc.get("kind") != "NetworkPolicy":
            continue
        meta = doc["metadata"]
        if meta.get("namespace") in tenants and meta["name"] not in allowed:
            found.append(f"{meta['namespace']}/{meta['name']}")
    return found


def load(path: str) -> list[dict]:
    try:
        return [d for d in yaml.safe_load_all(Path(path).read_text()) if d]
    except (OSError, yaml.YAMLError) as exc:
        raise CheckError(f"cannot read {path}: {exc}") from exc


def selftest(docs: list[dict], tenants: set[str]) -> None:
    # Converged input passes.
    assert violations(docs, tenants) == [], "selftest: real render must be clean"
    # A tenant-namespace policy missing from the allowlist fires.
    rogue = {"kind": "NetworkPolicy", "metadata": {"name": "selftest-not-allowlisted", "namespace": sorted(tenants)[0]}}
    assert violations(docs + [rogue], tenants), "selftest: unlisted tenant policy must fire"
    # The same policy in a platform namespace does not.
    platform = {"kind": "NetworkPolicy", "metadata": {"name": "selftest-not-allowlisted", "namespace": "selftest-platform"}}
    assert violations(docs + [platform], tenants) == [], "selftest: platform namespace must not fire"
    # A missing admission policy is an error, not a pass.
    without = [d for d in docs if d.get("kind") != "ValidatingAdmissionPolicy"]
    try:
        violations(without, tenants)
    except CheckError:
        pass
    else:
        raise AssertionError("selftest: missing admission policy must raise")
    print("selftest OK: clean render passes, unlisted policy fires, platform ns ignored, missing policy raises")


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--selftest"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        docs = load(args[0])
        tenants = tenant_namespaces()
        if "--selftest" in argv:
            selftest(docs, tenants)
        found = violations(docs, tenants)
    except CheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if found:
        for item in found:
            print(f"::error::{item} is rendered into a tenant namespace but missing from {POLICY_NAME}; "
                  "the API server will reject it at sync", file=sys.stderr)
        return 1
    print(f"OK: every bootstrap NetworkPolicy in a tenant namespace ({', '.join(sorted(tenants))}) is allowlisted")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
