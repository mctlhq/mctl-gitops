#!/usr/bin/env python3
"""Detect a stale tool catalogue on the Cloudflare MCP portal.

The portal serves clients from a snapshot of each upstream's tools --
names and `outputSchema` included. For a server in manual OAuth mode that
snapshot is taken once, at the first user authorization, and never
refreshed: `POST servers/{id}/sync` answers `success` and does nothing
(documented under the MCP Portals limitations; measured 2026-09-13,
mctlhq/.github#64). Two things then go wrong silently:

  - a tool added upstream is not in the catalogue, so the allowlist cannot
    enable it and no client ever sees it;
  - a tool whose output schema changed is validated by clients against the
    OLD schema. With `additionalProperties: false` in the snapshot, every
    added field is a failed call (mctlhq/mctl-telegram#637).

Neither is visible to `tofu plan` (`tools` is a computed attribute) nor to
the allowlist apply scripts, which hold back entries the portal has not
synced rather than failing on them. This compares the live snapshot with
the allowlist each owning repository commits on `main` -- that file is
test-enforced there to equal the set of tools the server registers, so it
is the honest statement of which tools the upstream advertises -- and
inspects the stored schemas for the closed form.

What it does NOT detect, stated so nobody reads more into a green run: a
schema whose CONTENT changed while its tool kept its name and its snapshot
stayed open. A retyped property or a newly required one breaks clients
against the stale snapshot exactly like an added field does, and nothing
here can see it, because no authoritative copy of the upstream's schemas is
committed anywhere to compare against -- the allowlist carries names and
decisions, not schemas. Closing that gap means a golden catalogue file in
each owning repository; tracked separately, and the reason this check
reports "names and closedness" rather than "the catalogue is fresh".

Usage:
    tofu show -json | portal-catalogue-drift.py
    portal-catalogue-drift.py --account <id>
    portal-catalogue-drift.py --selftest

The account id comes from `--account`, else `$CLOUDFLARE_ACCOUNT_ID`, else
the `account_id` of the MCP server resources in `tofu show -json` on stdin
-- the same address the registration check reads, so the two cannot check
different accounts.

Exit status: 0 in sync, 1 drifted (re-snapshot needed), 2 could not be
determined.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import http.client
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
RAW = "https://raw.githubusercontent.com"

# Portal server id -> the repository whose docs/portal-allowlist.json is the
# statement of that upstream's tool set. A server on the portal that is not
# named here is reported as undetermined, not skipped: an unchecked upstream
# is how this class of drift stays invisible.
#
# The allowlists are fetched from raw.githubusercontent.com WITHOUT a token,
# which works because all three repositories are public -- measured
# 2026-09-13, `gh repo view --json isPrivate` is false for each. If one is
# ever made private the fetch answers 404 and this check exits 2, "could not
# be determined", which is loud rather than silently green; the fix then is
# an App token with contents:read, the way release-drift.yml mints one.
OWNERS = {
    "tg": "mctlhq/mctl-telegram",
    "api": "mctlhq/mctl-api",
    "seerrsense": "mctlhq/seerrsense",
}
PORTAL = "mcp"


class Undetermined(Exception):
    """The check could not be computed. Distinct from drift; exits 2."""


def _get(url: str, token: str | None, what: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise Undetermined(f"{what}: answered {e.code}: {e.read()[:200]!r}")
    except urllib.error.URLError as e:
        raise Undetermined(f"{what}: unreachable: {e.reason}")
    except json.JSONDecodeError as e:
        raise Undetermined(f"{what}: not JSON: {e}")
    except (OSError, http.client.HTTPException) as e:
        # The headers arrived and the body did not: a read timeout, a reset
        # connection, an IncompleteRead. Uncaught, Python exits 1 -- the code
        # the workflow renders as "TOOL CATALOGUE STALE" with a re-snapshot
        # instruction, for a check that never compared anything. TimeoutError
        # and ConnectionResetError are both OSError subclasses.
        raise Undetermined(f"{what}: connection failed mid-response: {e!r}")


def account_from_state(state: dict) -> str:
    """account_id of the MCP server resources in the root, all agreeing."""
    found: set[str] = set()
    stack = [state.get("values", {}).get("root_module", {})]
    while stack:
        mod = stack.pop()
        for res in mod.get("resources", []) or []:
            if res.get("type") == "cloudflare_zero_trust_access_ai_controls_mcp_server":
                acct = (res.get("values") or {}).get("account_id")
                if acct:
                    found.add(acct)
        stack.extend(mod.get("child_modules", []) or [])
    if len(found) != 1:
        raise Undetermined(f"state names {len(found)} account ids for MCP servers, expected one")
    return found.pop()


def portal_servers(account: str, token: str) -> list[str]:
    body = _get(f"{API}/accounts/{account}/access/ai-controls/mcp/portals/{PORTAL}", token, "portal")
    if not body.get("success"):
        raise Undetermined(f"portal: API refused: {body.get('errors')}")
    servers = [s.get("server_id") for s in (body.get("result") or {}).get("servers") or []]
    if not servers:
        raise Undetermined("portal: no servers mapped -- silent success here would be wrong")
    return servers


def live_snapshot(account: str, server: str, token: str) -> dict:
    body = _get(f"{API}/accounts/{account}/access/ai-controls/mcp/servers/{server}", token, server)
    if not body.get("success"):
        raise Undetermined(f"{server}: API refused: {body.get('errors')}")
    return body.get("result") or {}


def owner_allowlist(server: str) -> dict:
    repo = OWNERS.get(server)
    if not repo:
        raise Undetermined(f"{server}: no owning repository known; add it to OWNERS")
    body = _get(f"{RAW}/{repo}/main/docs/portal-allowlist.json", None, f"{server}: {repo} allowlist")
    if body.get("server") != server:
        raise Undetermined(f"{server}: {repo} allowlist names server {body.get('server')!r}")
    return body


def closed_objects(schema, path: str = "") -> list[str]:
    """JSON-pointer-ish paths of every object with additionalProperties:false."""
    out: list[str] = []
    if isinstance(schema, dict):
        if schema.get("additionalProperties") is False:
            out.append(path or "/")
        for k, v in schema.items():
            out += closed_objects(v, f"{path}/{k}")
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            out += closed_objects(v, f"{path}/{i}")
    return out


def compare(server: str, snapshot: dict, allowlist: dict) -> list[dict]:
    """Structured findings: {"server", "kind", "names", "message"}.

    `kind` is what a waiver in KNOWN_STALE names and `names` is what it must
    enumerate, so a waiver excuses the tools someone looked at and nothing
    else.
    """
    out: list[dict] = []
    live = {t.get("name"): t for t in snapshot.get("tools") or []}
    want = {t.get("name") for t in allowlist.get("tools") or []}

    # A nameless entry on either side is not drift, it is a shape this script
    # does not understand -- and left alone it reaches sorted() as a None key,
    # raises TypeError, and exits 1: the status that means "stale, go
    # re-snapshot", for a server that may be perfectly fresh.
    if None in live or None in want:
        raise Undetermined(f"{server}: a tool entry has no name; refusing to compare")

    def add(kind: str, names: list[str], message: str) -> None:
        out.append({"server": server, "kind": kind, "names": names,
                    "message": f"{server}: {message}"})

    for name in sorted(want - set(live)):
        add("missing-tool", [name],
            f"{name} is upstream but not in the portal catalogue "
            f"(last_synced {snapshot.get('last_synced')}) -- re-snapshot, or the "
            "release that adds it is merged but not deployed yet, in which case "
            "wait for the rollout first")
    for name in sorted(set(live) - want):
        add("extra-tool", [name],
            f"{name} is in the portal catalogue but no longer upstream")

    closed = sorted(n for n, t in live.items() if closed_objects(t.get("outputSchema")))
    if closed:
        add("closed-schemas", closed,
            f"{len(closed)} stored outputSchema(s) are closed "
            "(additionalProperties:false) -- an added field fails the call: "
            + ", ".join(closed))
    return out


# Findings that are already tracked, with the date the excuse stops working.
# Without this the nightly run for this root is red from the day it lands, and
# a job that is red every night is one people stop reading -- the same disease
# as a green check nobody can trust, which is the argument cloudflare-drift.yml
# makes about itself.
#
# Three rules keep a waiver from becoming a blind spot: it names one kind of
# finding on one server, it expires on a date, and a waiver whose finding has
# stopped firing is itself an error, so the file cannot quietly accumulate
# excuses for things that were fixed months ago.
KNOWN_STALE = {
    ("seerrsense", "closed-schemas"): {
        "until": "2026-10-15",
        # The tools the waiver was written against. A finding is excused only
        # if every tool it names is in here, so a SIXTH seerrsense tool
        # acquiring a closed schema still fails -- without this the waiver
        # would cover the regression as well as the five known schemas, since
        # they arrive as one aggregated finding.
        "tools": ["get_media", "request_media", "resolve_media",
                  "search_media", "whoami"],
        "why": "seerrsense publishes closed output schemas in code (zod); the fix "
               "waits on its review freeze -- mctlhq/seerrsense#70, mctlhq/.github#64",
    },
}


def apply_waivers(findings: list[dict], today: str
                  ) -> tuple[list[str], list[str], list[str]]:
    """Split into (failing, waived, maintenance).

    `maintenance` is kept apart from `failing` because the two need opposite
    actions: a stale catalogue is fixed by the re-snapshot recipe, which takes
    a server down and makes every portal user re-authorize, while a dead
    waiver is fixed by deleting three lines from this file. Reporting both
    under one "re-snapshot" heading would send someone through the former for
    the latter.
    """
    failing: list[str] = []
    waived: list[str] = []
    maintenance: list[str] = []
    used: set[tuple[str, str]] = set()

    for f in findings:
        key = (f["server"], f["kind"])
        w = KNOWN_STALE.get(key)
        if w is None:
            failing.append(f["message"])
            continue
        used.add(key)
        # Expires the day AFTER `until`, the same boundary everywhere: on the
        # date itself the waiver still holds.
        if today > w["until"]:
            failing.append(f'{f["message"]}\n    (waiver expired {w["until"]}: {w["why"]})')
            continue
        new_names = sorted(set(f.get("names") or []) - set(w.get("tools") or []))
        if new_names:
            failing.append(
                f'{f["message"]}\n    (the waiver until {w["until"]} covers '
                f'{", ".join(w.get("tools") or []) or "nothing"} -- '
                f'NOT {", ".join(new_names)})')
            continue
        waived.append(f'{f["message"]}\n    (known until {w["until"]}: {w["why"]})')

    for key, w in sorted(KNOWN_STALE.items()):
        if key not in used:
            maintenance.append(
                f"{key[0]}: the waiver for {key[1]} excuses nothing -- the finding "
                f"it names is gone. Delete it from KNOWN_STALE in this script. "
                f"({w['why']})")
    return failing, waived, maintenance


def selftest() -> int:
    """A detector never seen to fire is not known to work."""
    def snap(names, closed=False, extra=None):
        tools = []
        for n in names:
            schema = {"type": "object", "properties": {"a": {"type": "string"}}}
            if closed:
                schema["additionalProperties"] = False
            tools.append({"name": n, "outputSchema": schema})
        if extra:
            tools.append(extra)
        return {"tools": tools, "last_synced": "2026-09-10 12:00:00"}

    def allow(names):
        return {"server": "s", "tools": [{"name": n, "enabled": True} for n in names]}

    nested_closed = {"name": "n", "outputSchema": {
        "type": "object", "properties": {"entries": {"type": "array", "items": {
            "type": "object", "additionalProperties": False}}}}}
    cases = [
        ("identical is quiet", snap(["a", "b"]), allow(["a", "b"]), 0),
        ("a tool missing from the catalogue fires", snap(["a"]), allow(["a", "b"]), 1),
        ("a tool gone from upstream fires", snap(["a", "b"]), allow(["a"]), 1),
        ("a closed top-level schema fires", snap(["a"], closed=True), allow(["a"]), 1),
        ("a closed nested schema fires", snap([], extra=nested_closed), allow(["n"]), 1),
        ("no outputSchema at all is quiet",
         {"tools": [{"name": "a"}], "last_synced": ""}, allow(["a"]), 0),
        ("order does not matter", snap(["b", "a"]), allow(["a", "b"]), 0),
    ]
    failures = []
    for name, sn, a, expected in cases:
        got = 1 if compare("s", sn, a) else 0
        print(f"{'ok  ' if got == expected else 'FAIL'} {name}")
        if got != expected:
            failures.append(name)

    # A finding carries the kind a waiver addresses and the tools it is about.
    # Asserting the spelling here is what keeps KNOWN_STALE's keys from
    # silently matching nothing.
    got = compare("s", snap(["a"], closed=True), allow(["a", "b"]))
    kinds = {f["kind"] for f in got}
    ok = kinds == {"missing-tool", "closed-schemas"} and all(f["names"] for f in got)
    print(f"{'ok  ' if ok else 'FAIL'} findings are labelled by kind and tools ({sorted(kinds)})")
    if not ok:
        failures.append("kinds")

    # A nameless entry is a shape this script does not understand, and must
    # exit 2 rather than reach sorted() and die as exit 1, "stale".
    try:
        compare("s", {"tools": [{"name": None}, {"name": "a"}]}, allow(["a"]))
        ok = False
    except Undetermined:
        ok = True
    print(f"{'ok  ' if ok else 'FAIL'} a nameless tool is undetermined, not drift")
    if not ok:
        failures.append("nameless tool")

    # The waiver machinery, against a fixture rather than the live table, so
    # these cases keep testing the logic after the real waivers are removed.
    fixture = dict(KNOWN_STALE)
    try:
        KNOWN_STALE.clear()
        KNOWN_STALE[("s", "closed-schemas")] = {
            "until": "2026-10-15", "tools": ["a", "b"], "why": "fixture"}
        finding = [{"server": "s", "kind": "closed-schemas", "names": ["a", "b"],
                    "message": "s: closed"}]
        grown = [{"server": "s", "kind": "closed-schemas", "names": ["a", "b", "c"],
                  "message": "s: closed"}]
        other = [{"server": "s", "kind": "missing-tool", "names": ["z"],
                  "message": "s: missing"}]

        wcases = [
            ("a live waiver excuses the tools it names", finding, "2026-09-13", 0, 0),
            ("it still holds on the expiry date itself", finding, "2026-10-15", 0, 0),
            ("it stops excusing the day after", finding, "2026-10-16", 1, 0),
            ("a tool the waiver does not name still fails", grown, "2026-09-13", 1, 0),
            ("a waiver does not excuse another kind", finding + other, "2026-09-13", 1, 0),
            ("an unwaived finding fails and does not excuse the waiver",
             other, "2026-09-13", 1, 1),
            ("a waiver that excuses nothing needs maintenance", [], "2026-09-13", 0, 1),
        ]
        for name, f, today, want_fail, want_maint in wcases:
            failing, _, maint = apply_waivers(f, today)
            got_f, got_m = (1 if failing else 0), (1 if maint else 0)
            ok = (got_f, got_m) == (want_fail, want_maint)
            print(f"{'ok  ' if ok else 'FAIL'} {name}")
            if not ok:
                failures.append(name)
    finally:
        KNOWN_STALE.clear()
        KNOWN_STALE.update(fixture)

    # Every committed waiver must name a date this script can compare and the
    # tools it covers. Deliberately NOT "and the date has not passed": this
    # selftest runs on every pull request in the repository, so asserting
    # freshness here would turn an expiry into a repo-wide red on unrelated
    # PRs. Expiry belongs to apply_waivers, which the nightly run calls.
    for key, w in sorted(KNOWN_STALE.items()):
        try:
            _dt.date.fromisoformat(w["until"])
            valid = bool(w.get("tools")) and bool(w.get("why"))
        except (KeyError, ValueError, TypeError):
            valid = False
        print(f"{'ok  ' if valid else 'FAIL'} committed waiver {key} is dated and names its tools")
        if not valid:
            failures.append(f"waiver {key}")
        if valid and w["until"] < _dt.date.today().isoformat():
            print(f"     note: waiver {key} expired on {w['until']}; the nightly run reports it")

    if failures:
        print(f"\n{len(failures)} failing: {', '.join(map(str, failures))}")
        return 1
    print("\nall ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--account", help="Cloudflare account id (default: $CLOUDFLARE_ACCOUNT_ID)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        print("[2] CLOUDFLARE_API_TOKEN is not set", file=sys.stderr)
        return 2
    account = args.account or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not account and not sys.stdin.isatty():
        try:
            account = account_from_state(json.load(sys.stdin))
        except (json.JSONDecodeError, Undetermined) as e:
            print(f"[2] stdin is not usable `tofu show -json` output: {e}", file=sys.stderr)
            return 2
    if not account:
        print("[2] no account id: pass --account, set CLOUDFLARE_ACCOUNT_ID, or pipe `tofu show -json`", file=sys.stderr)
        return 2

    findings: list[dict] = []
    checked: list[str] = []
    try:
        for server in portal_servers(account, token):
            snapshot = live_snapshot(account, server, token)
            allowlist = owner_allowlist(server)
            findings += compare(server, snapshot, allowlist)
            checked.append(f"{server}={len(snapshot.get('tools') or [])}@{snapshot.get('last_synced')}")
    except Undetermined as e:
        print(f"[2] {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - the exit code is the whole point
        # Anything unforeseen is "could not be determined", never "stale".
        # Python exits 1 on an uncaught exception and the workflow reads 1 as
        # confirmed drift, which sends someone through a recipe that takes a
        # server down to fix what is actually a bug in this file.
        print(f"[2] the check failed before it could compare: {e!r}", file=sys.stderr)
        return 2

    failing, waived, maintenance = apply_waivers(findings, _dt.date.today().isoformat())

    # Waived findings print on stdout even on a clean run. They are the
    # difference between "nothing is stale" and "nothing is stale that we have
    # not already written down", and the run says which.
    for line in waived:
        print(f"known stale: {line}")

    if failing:
        print("the portal's tool catalogue no longer matches its upstreams "
              "(re-snapshot per infrastructure/cloudflare/portal/README.md):", file=sys.stderr)
        for line in failing:
            print(f"  {line}", file=sys.stderr)
    if maintenance:
        # Its own heading: this one is fixed in this file, not on the portal.
        print("a waiver in this script no longer matches anything "
              "(do NOT re-snapshot for this):", file=sys.stderr)
        for line in maintenance:
            print(f"  {line}", file=sys.stderr)
    if failing or maintenance:
        return 1
    print(f"in sync: {', '.join(checked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
