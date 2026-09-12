#!/usr/bin/env python3
"""Detect drift in the one Cloudflare field OpenTofu cannot see.

`auth_credentials` on an MCP server is write-only: the API accepts it and
never returns it, exposing only the read-only `auth_config_summary`
projection. The provider therefore keeps whatever was last applied in state
and a refresh cannot correct it -- measured on 2026-09-12 against a throwaway
server: after an out-of-band PUT changed the live scope, `tofu plan` stayed
`no-op` while the live value read `probe:TAMPERED`.

That is the whole reason this exists. Everything else about the server is
plan-visible and belongs to OpenTofu; this compares the live projection
against what state says was applied, so an edit made in the dashboard or
through the API is not invisible.

There is no second source of truth: the desired value is read from the
OpenTofu state, not from a file next to it. A field this script does not
know about is reported rather than ignored, so a registration that grows a
key stops being silently unchecked.

Usage:
    tofu show -json | portal-auth-credentials-drift.py --account <id>
    portal-auth-credentials-drift.py --selftest

Exit status: 0 in sync, 1 drifted, 2 could not be determined.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

RESOURCE_TYPE = "cloudflare_zero_trust_access_ai_controls_mcp_server"
API = "https://api.cloudflare.com/client/v4"


class Undetermined(Exception):
    """The check could not be computed. Distinct from drift, and it exits 2.

    `raise SystemExit("...")` would have exited 1 -- the same status as
    "drifted" -- so an unreachable API would have read as a scope that
    changed. Caught by the script's own end-to-end run before it shipped.
    """


def desired_from_state(state: dict) -> dict[str, dict]:
    """server id -> {"blob", "summary", "account_id"} as state records them.

    "blob" is the auth_credentials that was applied -- the desired value.
    "summary" is the auth_config_summary the API returned at that moment: it
    is the only record of the two secret-bookkeeping fields, which the blob
    deliberately never carries, so it is what those are compared against.
    "account_id" is read here rather than passed in, because the docstring's
    claim that there is no second source of truth has to hold for the address
    as much as for the value.
    """
    out: dict[str, dict] = {}
    stack = [state.get("values", {}).get("root_module", {})]
    while stack:
        mod = stack.pop()
        for res in mod.get("resources", []) or []:
            if res.get("type") != RESOURCE_TYPE:
                continue
            values = res.get("values") or {}
            raw = values.get("auth_credentials")
            sid = values.get("id")
            if not sid:
                continue
            if not raw:
                # Applied by something that did not record it, or never
                # applied. Either way there is nothing to compare against,
                # and saying "in sync" would be a lie.
                raise Undetermined(
                    f"{sid}: state holds no auth_credentials; "
                    "apply the root before checking it"
                )
            try:
                out[sid] = {
                "blob": json.loads(raw),
                "summary": values.get("auth_config_summary") or {},
                "account_id": values.get("account_id"),
            }
            except json.JSONDecodeError as e:
                # Exits 2, not 1. An unparseable state value is not a changed
                # scope, and letting the ValueError escape would have reported
                # it as one -- the same confusion the Undetermined class exists
                # to prevent.
                raise Undetermined(f"{sid}: auth_credentials in state is not JSON: {e}")
        stack.extend(mod.get("child_modules", []) or [])
    return out


def live_summary(account: str, server: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API}/accounts/{account}/access/ai-controls/mcp/servers/{server}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:  # noqa: PERF203 - one call, one error
        raise Undetermined(f"{server}: API answered {e.code}: {e.read()[:200]!r}")
    except urllib.error.URLError as e:
        raise Undetermined(f"{server}: cannot reach the API: {e.reason}")
    if not body.get("success"):
        raise Undetermined(f"{server}: API refused: {body.get('errors')}")
    return (body.get("result") or {}).get("auth_config_summary") or {}


# Keys the live projection may carry that the applied blob never names. They
# are server-populated, so an "unknown live key" report on them would be a
# false alarm rather than a tamper. Everything NOT listed here is still
# reported: an unchecked field is how this class of drift stayed invisible.
SERVER_POPULATED = {("config", "resource")}


# The projection's top-level bookkeeping. Not in the applied blob by design --
# client_secret is a separate write-only field and must never be committed --
# so these are compared against what the API returned at apply time, recorded
# in state. A secret that vanished, or a version that moved without an apply,
# is exactly the kind of change this check exists to surface.
SECRET_BOOKKEEPING = ("has_client_secret", "client_secret_version")


def compare(server: str, want: dict, live: dict, applied_summary: dict | None = None) -> list[str]:
    """One line per difference. Scope as a set: the API stores it
    space-separated and the order it comes back in is not measured."""
    diffs: list[str] = []

    if want.get("auth_mode") != live.get("auth_mode"):
        diffs.append(
            f"{server}: auth_mode live={live.get('auth_mode')!r} "
            f"applied={want.get('auth_mode')!r}"
        )

    for key in SECRET_BOOKKEEPING:
        if applied_summary is None or key not in applied_summary:
            continue
        if applied_summary.get(key) != live.get(key):
            diffs.append(
                f"{server}: {key} live={json.dumps(live.get(key))} "
                f"applied={json.dumps(applied_summary.get(key))}"
            )

    for section in ("config", "registration_info"):
        w = want.get(section) or {}
        l = live.get(section) or {}
        for key in sorted(set(w) | set(l)):
            if (section, key) in SERVER_POPULATED and key not in w:
                continue
            wv, lv = w.get(key), l.get(key)
            if key == "scope":
                wv = sorted((wv or "").split())
                lv = sorted((lv or "").split())
            if isinstance(wv, list) and isinstance(lv, list):
                wv, lv = sorted(wv), sorted(lv)
            if wv != lv:
                diffs.append(
                    f"{server}: {section}.{key} live={json.dumps(lv)} "
                    f"applied={json.dumps(wv)}"
                )
    return diffs


def selftest() -> int:
    """A detector never seen to fire is not known to work."""
    base = {
        "auth_mode": "manual",
        "config": {"issuer": "https://example.test"},
        "registration_info": {
            "client_id": "c",
            "redirect_uris": ["https://a.test/cb"],
            "token_endpoint_auth_method": "none",
            "scope": "a:read b:read",
        },
    }

    def live_with(**over):
        out = json.loads(json.dumps(base))
        for path, value in over.items():
            section, key = path.split(".", 1)
            out[section][key] = value
        return out

    cases = [
        ("identical is quiet", live_with(), 0),
        ("reordered scope is not drift",
         live_with(**{"registration_info.scope": "b:read a:read"}), 0),
        ("a narrowed scope fires",
         live_with(**{"registration_info.scope": "a:read"}), 1),
        ("a widened scope fires",
         live_with(**{"registration_info.scope": "a:read b:read c:write"}), 1),
        ("a changed endpoint fires",
         live_with(**{"config.issuer": "https://evil.test"}), 1),
        ("a changed client fires",
         live_with(**{"registration_info.client_id": "other"}), 1),
        ("reordered redirect_uris is not drift",
         live_with(**{"registration_info.redirect_uris": ["https://a.test/cb"]}), 0),
    ]

    # A manual registration silently becoming DCR is the loudest thing that
    # could happen to this field, and the branch that catches it had no case.
    dcr = json.loads(json.dumps(base))
    dcr["auth_mode"] = "dcr"
    cases.append(("a switch to dcr fires", dcr, 1))

    # Cloudflare populating a server-side key it owns is not a tamper.
    populated = live_with()
    populated["config"]["resource"] = "https://example.test/mcp"
    cases.append(("a server-populated key is not drift", populated, 0))
    failures = []
    for name, live, expected in cases:
        got = 1 if compare("s", base, live) else 0
        print(f"{'ok  ' if got == expected else 'FAIL'} {name}")
        if got != expected:
            failures.append(name)

    # The bookkeeping pair, which has no desired value in the blob and is
    # compared against what state recorded at apply time.
    summary = {"has_client_secret": True, "client_secret_version": 1}

    def live_book(**over):
        out = live_with()
        out.update(summary)
        out.update(over)
        return out

    got = compare("s", base, live_book(), summary)
    ok = not got
    print(f"{'ok  ' if ok else 'FAIL'} matching secret bookkeeping is quiet")
    if not ok:
        failures.append("bookkeeping quiet")

    gone = live_book(has_client_secret=False)
    got = compare("s", base, gone, summary)
    ok = any("has_client_secret" in d for d in got)
    print(f"{'ok  ' if ok else 'FAIL'} a vanished client_secret fires")
    if not ok:
        failures.append("vanished secret")

    rotated = live_book(client_secret_version=2)
    got = compare("s", base, rotated, summary)
    ok = any("client_secret_version" in d for d in got)
    print(f"{'ok  ' if ok else 'FAIL'} a rotated client_secret version fires")
    if not ok:
        failures.append("rotated secret")

    # Without a recorded summary there is nothing to compare against, and
    # inventing a expectation would be worse than saying nothing.
    got = compare("s", base, gone, None)
    ok = not any("has_client_secret" in d for d in got)
    print(f"{'ok  ' if ok else 'FAIL'} no recorded summary means no claim")
    if not ok:
        failures.append("unrecorded summary")

    # A key the live side grew but the applied blob does not name must be
    # reported, not skipped: an unchecked field is how this class of drift
    # became invisible in the first place.
    extra = live_with()
    extra["registration_info"]["surprise"] = "x"
    got = compare("s", base, extra)
    ok = any("surprise" in d for d in got)
    print(f"{'ok  ' if ok else 'FAIL'} an unknown live key is reported")
    if not ok:
        failures.append("unknown key")

    if failures:
        print(f"\n{len(failures)} failing: {', '.join(failures)}")
        return 1
    print("\nall ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--account", help="Cloudflare account id (default: from state)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        print("[2] CLOUDFLARE_API_TOKEN is not set", file=sys.stderr)
        return 2

    try:
        state = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[2] stdin is not `tofu show -json` output: {e}", file=sys.stderr)
        return 2

    try:
        want = desired_from_state(state)
    except Undetermined as e:
        print(f"[2] {e}", file=sys.stderr)
        return 2
    if not want:
        # Nothing of this type in the root. Silent success here would make the
        # check pass for the wrong reason on a root that lost its resource.
        print("[2] state holds no MCP server resources", file=sys.stderr)
        return 2

    drifted = []
    for server, rec in sorted(want.items()):
        account = args.account or rec.get("account_id")
        if not account:
            print(f"[2] {server}: no account_id in state and none given", file=sys.stderr)
            return 2
        try:
            live = live_summary(account, server, token)
        except Undetermined as e:
            print(f"[2] {e}", file=sys.stderr)
            return 2
        drifted += compare(server, rec["blob"], live, rec.get("summary"))

    if drifted:
        print("auth_credentials has drifted from what was applied:", file=sys.stderr)
        for line in drifted:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"in sync: {', '.join(sorted(want))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
