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
inspects the stored inputSchema and outputSchema for the closed form.

What it does NOT detect, stated so nobody reads more into a green run: a
schema whose CONTENT changed while its tool kept its name and its snapshot
stayed open, on either side. A retyped property or a newly required
parameter breaks clients against the stale snapshot exactly like a field
added to an output does, and nothing
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

Exit status, and the split matters because the remedies cost different
things:

    0  in sync (any waived finding is printed, and the run says so)
    1  the catalogue is stale -- re-snapshot per the portal README, which
       takes a server down and makes every portal user re-authorize
    2  could not be determined -- nothing was compared, fix the check
    3  a waiver in this file matches nothing any more -- delete it here;
       do NOT re-snapshot for this
    4  an upstream this script expects is not mapped on the portal at all --
       restore the mapping, or retire it from OWNERS

Every non-zero status is a failure a caller must surface. The numbers say
which one happened, never that any of them is ignorable.
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
    if any(sid is None for sid in servers):
        # Otherwise None is carried into live_snapshot, requests
        # .../servers/None, and the run reports a server called "None" instead
        # of the shape problem -- and, if the nameless entry is one this script
        # expects, ALSO reports that server as missing from the portal.
        raise Undetermined("portal: a server mapping has no server_id; refusing to compare")
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
    raw_live, raw_want = snapshot.get("tools"), allowlist.get("tools")

    # Everything below this point is the same argument in four shapes: a side
    # this script cannot read is not drift, and exit 1 is the status that
    # means "stale, go re-snapshot", for a server that may be perfectly fresh.
    if not isinstance(raw_live, list) or not isinstance(raw_want, list):
        raise Undetermined(
            f"{server}: tools is not a list "
            f"(portal {type(raw_live).__name__}, allowlist {type(raw_want).__name__}); "
            "refusing to compare")

    live = {t.get("name"): t for t in raw_live}
    want = {t.get("name") for t in raw_want}

    # A nameless entry would otherwise reach sorted() as a None key and raise
    # TypeError.
    if None in live or None in want:
        raise Undetermined(f"{server}: a tool entry has no name; refusing to compare")

    # An empty side is not an empty catalogue. The portal holds no tools for a
    # server nobody has authorized yet -- `status: waiting`, which is also
    # where the README's own recipe parks a server between step 2 and step 3 --
    # and reported as drift that is every upstream tool `missing-tool`, exit 1,
    # and a re-snapshot instruction for a condition only a user signing in can
    # clear. An empty allowlist is the mirror: the file parsed, so its shape
    # changed upstream, and every stored tool would be called `extra-tool`.
    if not live:
        raise Undetermined(
            f"{server}: the portal holds no tools at all (status "
            f"{snapshot.get('status')!r}, last_synced {snapshot.get('last_synced')}) "
            "-- a server waiting for its first authorization needs a user to "
            "sign in, not a re-snapshot")
    if not want:
        raise Undetermined(
            f"{server}: the allowlist lists no tools -- its shape changed "
            "upstream; refusing to call every stored tool extra")

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
            f"{name} is in the portal catalogue but no longer upstream -- "
            "re-snapshot, or the release that removes it is merged but not "
            "deployed yet, in which case wait for the rollout first: "
            "re-snapshotting now would capture the tool again and leave this red")

    # Both schemas. The README states the rule for the whole tool definition,
    # and a stale closed inputSchema rejects a parameter the upstream added
    # exactly as a closed outputSchema rejects a field it started returning.
    # Measured 2026-09-13: every stored inputSchema is open today, so this
    # widens what is watched without widening what is red.
    closed_out = sorted(n for n, t in live.items()
                        if closed_objects(t.get("outputSchema")))
    closed_in = sorted(n for n, t in live.items()
                       if closed_objects(t.get("inputSchema")))
    closed = sorted(set(closed_out) | set(closed_in))
    if closed:
        # Which side, because the remedies differ: a closed outputSchema is
        # the upstream bug mctlhq/mctl-telegram#637 and a release plus a
        # re-snapshot clears it, while a closed inputSchema may be deliberate
        # upstream behaviour no release will open, and then the only way out
        # of exit 1 is a KNOWN_STALE entry. `names` stays tool names, so a
        # waiver enumerates what it always enumerated.
        sides = []
        if closed_out:
            sides.append("output: " + ", ".join(closed_out))
        if closed_in:
            sides.append("input: " + ", ".join(closed_in))
        add("closed-schemas", closed,
            f"{len(closed)} stored schema(s) are closed "
            "(additionalProperties:false) -- a field or parameter added upstream "
            "fails the call, and re-snapshotting before the release that opens "
            "them is deployed just captures them closed again. "
            + "; ".join(sides))
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


def apply_waivers(findings: list[dict], today: str, compared: set[str]
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
        # Only a server that was actually compared can prove its waiver dead.
        # One that could not be read produces no findings by construction, and
        # judging it here would tell someone to delete a waiver because
        # raw.githubusercontent.com timed out for a night.
        if key[0] in compared and key not in used:
            maintenance.append(
                f"{key[0]}: the waiver for {key[1]} excuses nothing -- the finding "
                f"it names is gone. Delete it from KNOWN_STALE in this script. "
                f"({w['why']})")
    return failing, waived, maintenance


def expected_missing(servers) -> list[str]:
    """Upstreams OWNERS expects that the portal does not map at all.

    A function rather than a set expression inline in main() so the loudest
    branch in this file is reachable from selftest() like every other one.
    """
    return [
        f"{missing}: expected on portal {PORTAL} and not mapped there at all "
        "-- restore the mapping, or drop it from OWNERS in this script if it "
        "was retired on purpose"
        for missing in sorted(set(OWNERS) - set(servers))
    ]


def selftest() -> int:
    """A detector never seen to fire is not known to work."""
    def snap(names, closed=False, extra=None, closed_input=False):
        tools = []
        for n in names:
            schema = {"type": "object", "properties": {"a": {"type": "string"}}}
            if closed:
                schema["additionalProperties"] = False
            t = {"name": n, "outputSchema": schema}
            if closed_input:
                t["inputSchema"] = {"type": "object", "additionalProperties": False}
            tools.append(t)
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
        # The inputSchema half of the closedness check: snap() writes an
        # outputSchema for every tool, so without this case the clause that
        # scans inputSchema could be deleted -- or misspelled input_schema,
        # which t.get() answers None to -- and every other case still passes.
        ("a closed inputSchema fires too",
         snap(["a"], closed_input=True), allow(["a"]), 1),
        # A side this script cannot read is exit 2, never exit 1: the four
        # shapes of that, since exit 1 sends someone through a destructive
        # recipe that fixes none of them.
        ("an unsnapshotted server is undetermined, not total drift",
         {"tools": [], "status": "waiting", "last_synced": ""}, allow(["a"]), "U"),
        ("an allowlist with no tools is undetermined, not total drift",
         snap(["a"]), {"server": "s", "tools": []}, "U"),
        ("a non-list catalogue is undetermined",
         {"tools": None, "last_synced": ""}, allow(["a"]), "U"),
        ("a non-list allowlist is undetermined",
         snap(["a"]), {"server": "s", "tools": {"a": True}}, "U"),
    ]
    failures = []
    for name, sn, a, expected in cases:
        try:
            got = 1 if compare("s", sn, a) else 0
        except Undetermined:
            got = "U"
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
        # A server that could not be compared must not make its own waiver
        # look dead: it produces no findings by construction.
        _, _, maint = apply_waivers([], "2026-09-13", set())
        ok = not maint
        print(f"{'ok  ' if ok else 'FAIL'} an uncompared server does not condemn its waiver")
        if not ok:
            failures.append("uncompared server")

        for name, f, today, want_fail, want_maint in wcases:
            failing, _, maint = apply_waivers(f, today, {"s"})
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

    # The loudest branch in the file, and until it moved out of main() the only
    # decision here with no case: an upstream OWNERS expects and the portal
    # does not map at all.
    for name, servers, want in [
        ("every expected upstream mapped is quiet", set(OWNERS), 0),
        ("an upstream missing from the portal fires", set(OWNERS) - {"tg"}, 1),
        ("a server the portal maps and OWNERS does not is not missing",
         set(OWNERS) | {"unknown"}, 0),
    ]:
        got = 1 if expected_missing(servers) else 0
        print(f"{'ok  ' if got == want else 'FAIL'} {name}")
        if got != want:
            failures.append(name)

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
        # Broad on purpose, like the server loop below: state that parses as
        # JSON but is not the shape account_from_state walks raises
        # AttributeError or TypeError, and an uncaught one exits 1 -- the
        # status that sends someone through the re-snapshot recipe.
        try:
            account = account_from_state(json.load(sys.stdin))
        except Undetermined as e:
            print(f"[2] {e}", file=sys.stderr)
            return 2
        except Exception as e:  # noqa: BLE001 - the exit code is the point
            print(f"[2] stdin is not usable `tofu show -json` output: {e!r}", file=sys.stderr)
            return 2
    if not account:
        print("[2] no account id: pass --account, set CLOUDFLARE_ACCOUNT_ID, or pipe `tofu show -json`", file=sys.stderr)
        return 2

    findings: list[dict] = []
    checked: list[str] = []
    undetermined: list[str] = []
    try:
        servers = portal_servers(account, token)
    except Undetermined as e:
        print(f"[2] {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - the exit code is the point
        print(f"[2] the portal could not be read: {e!r}", file=sys.stderr)
        return 2

    # An upstream OWNERS expects and the portal no longer maps is the loudest
    # thing that can happen here, and iterating what the portal returns would
    # miss it completely: the loop below simply never visits it, every other
    # catalogue is healthy, and the run exits 0 while a whole server has
    # vanished from production.
    # Its own list and its own exit status. Folded into `undetermined` it was
    # announced as "the catalogue check could not run", which is the triage
    # bucket people reach for last -- for the one finding here that means a
    # whole upstream has disappeared from production.
    vanished = expected_missing(servers)

    # Per server, so one unreachable upstream does not discard the drift
    # already found on the others. A read timeout on the last repository used
    # to cost the whole night's comparison: the run was red either way, but
    # the real finding waited until someone opened the raw step log.
    compared: set[str] = set()
    for server in servers:
        try:
            snapshot = live_snapshot(account, server, token)
            allowlist = owner_allowlist(server)
            findings += compare(server, snapshot, allowlist)
            checked.append(f"{server}={len(snapshot.get('tools') or [])}@{snapshot.get('last_synced')}")
            compared.add(server)
        except Undetermined as e:
            undetermined.append(str(e))
        except Exception as e:  # noqa: BLE001 - the exit code is the point
            undetermined.append(f"{server}: the check failed before it could compare: {e!r}")

    failing, waived, maintenance = apply_waivers(
        findings, _dt.date.today().isoformat(), compared)

    # Waived findings print on stdout even on a clean run. They are the
    # difference between "nothing is stale" and "nothing is stale that we have
    # not already written down", and the run says which.
    for line in waived:
        print(f"known stale: {line}")

    if vanished:
        print(f"an upstream is missing from portal {PORTAL} entirely:", file=sys.stderr)
        for line in vanished:
            print(f"  {line}", file=sys.stderr)
        # One exit code cannot carry two states, and exit 4 outranks exit 1 on
        # purpose. Say here that the quieter one also fired, so the heading and
        # the alert -- which are what get read first -- do not imply the
        # catalogues are otherwise in sync.
        if failing:
            print(f"  (and {len(failing)} catalogue finding(s) below, which this "
                  "exit status does not name)", file=sys.stderr)
    if undetermined:
        print("these servers were not compared:", file=sys.stderr)
        for line in undetermined:
            print(f"  {line}", file=sys.stderr)
    if failing:
        print("the portal's tool catalogue no longer matches its upstreams "
              "(re-snapshot per infrastructure/cloudflare/portal/README.md):", file=sys.stderr)
        for line in failing:
            print(f"  {line}", file=sys.stderr)
    if maintenance:
        # Its own heading and its own exit status: this one is fixed in this
        # file, not on the portal.
        print("a waiver in this script no longer matches anything "
              "(do NOT re-snapshot for this):", file=sys.stderr)
        for line in maintenance:
            print(f"  {line}", file=sys.stderr)

    # Printed for every outcome that has one, not only the clean run: this
    # line carries each snapshot's last_synced and tool count, and the person
    # reading a red summary is the one who most needs to know when the
    # catalogue was taken.
    if checked:
        print(f"compared: {', '.join(checked)}")

    # Ordered by how loud the finding is, not by exit number: a whole upstream
    # gone outranks a stale catalogue, which outranks a server that could not
    # be read, which outranks a waiver needing a delete.
    if vanished:
        return 4
    if failing:
        return 1
    if undetermined:
        return 2
    if maintenance:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
