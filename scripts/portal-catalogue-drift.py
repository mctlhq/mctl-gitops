#!/usr/bin/env python3
"""Detect a stale tool catalogue on the Cloudflare MCP portal.

The portal serves clients from a snapshot of each upstream's tools --
names, `inputSchema` and `outputSchema` included. For a server in manual OAuth mode that
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
    2  a side could not be read, or a server holds no tools at all -- the
       servers that WERE compared are still reported; an unauthorized server
       needs a user to sign in, anything else is a check to fix
    3  a waiver in this file needs attention -- it matches nothing any more,
       or it still names tools that have stopped firing. Delete or narrow it
       here; do NOT re-snapshot for either
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


# Where a JSON Schema keeps SUBSCHEMAS. The walk visits these and nothing
# else, because a schema also carries data: `examples: [{"additionalProperties":
# false}]` is a perfectly open schema whose sample happens to spell the closed
# form, and reported as closed it is exit 1 and a re-snapshot that cannot
# clear it. Skipping the data keywords by name instead would be wrong the
# other way -- inside `properties` the keys are names the upstream chose, so a
# parameter called `default` or `enum` would take its whole subtree out of the
# walk and hide a genuinely closed schema.
SUBSCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions",
                  "dependentSchemas")
SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
SUBSCHEMA_VALUES = ("items", "additionalItems", "contains", "not", "if", "then",
                    "else", "propertyNames", "additionalProperties",
                    "unevaluatedItems", "unevaluatedProperties")


def closed_objects(schema, path: str = "") -> list[str]:
    """JSON-pointer-ish paths of every object with additionalProperties:false."""
    out: list[str] = []
    if not isinstance(schema, dict):
        return out
    if schema.get("additionalProperties") is False:
        out.append(path or "/")
    for k in SUBSCHEMA_MAPS:
        v = schema.get(k)
        if isinstance(v, dict):
            for name, sub in v.items():
                out += closed_objects(sub, f"{path}/{k}/{name}")
    for k in SUBSCHEMA_LISTS:
        v = schema.get(k)
        if isinstance(v, list):
            for i, sub in enumerate(v):
                out += closed_objects(sub, f"{path}/{k}/{i}")
    for k in SUBSCHEMA_VALUES:
        v = schema.get(k)
        if isinstance(v, list):          # draft-4 tuple form of `items`
            for i, sub in enumerate(v):
                out += closed_objects(sub, f"{path}/{k}/{i}")
        else:
            out += closed_objects(v, f"{path}/{k}")
    return out


# Every `kind` compare() can emit. KNOWN_STALE keys are checked against this
# in selftest(), so a waiver naming a kind this file cannot produce fails on a
# pull request instead of at night, where it would arrive as a stale catalogue
# and a destructive instruction that fixes nothing.
KINDS = ("missing-tool", "extra-tool",
         "closed-output-schemas", "closed-input-schemas")


def compare(server: str, snapshot: dict, allowlist: dict) -> list[dict]:
    """Structured findings: {"server", "kind", "names", "message"}.

    `kind` is what a waiver in KNOWN_STALE names and `names` is what it must
    enumerate, so a waiver excuses the tools someone looked at and nothing
    else.
    """
    out: list[dict] = []
    raw_live, raw_want = snapshot.get("tools"), allowlist.get("tools")
    # `tools: null` is the portal's answer for a server waiting on its first
    # authorization -- the case the `if not live` guard below was written for,
    # with the message that says a user has to sign in. Left as None it trips
    # the type check first and that message becomes unreachable, replaced by
    # one about a broken payload shape. Same exit 2, wrong instruction.
    if raw_live is None:
        raw_live = []

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
        # The remedy follows the evidence. `tools` is None for two payloads:
        # the waiting server, where a user signing in is the fix, and a result
        # that simply has no `tools` -- a thin or renamed body from an API
        # answering success. Asserting the first while printing `status None`
        # right beside it puts the contradiction in one sentence and leaves the
        # on-call to spot it.
        status = snapshot.get("status")
        remedy = ("a server waiting for its first authorization needs a user "
                  "to sign in, not a re-snapshot" if status == "waiting" else
                  "the portal answered without a tool list; this is the check "
                  "or the API to look at, not the catalogue")
        raise Undetermined(
            f"{server}: the portal holds no tools at all (status "
            f"{status!r}, last_synced {snapshot.get('last_synced')}) -- {remedy}")
    if not want:
        raise Undetermined(
            f"{server}: the allowlist lists no tools -- its shape changed "
            "upstream; refusing to call every stored tool extra")

    def add(kind: str, names: list[str], message: str) -> None:
        out.append({"server": server, "kind": kind, "names": names,
                    "message": f"{server}: {message}"})

    for name in sorted(want - set(live)):
        add(KINDS[0], [name],
            f"{name} is upstream but not in the portal catalogue "
            f"(last_synced {snapshot.get('last_synced')}) -- re-snapshot, or the "
            "release that adds it is merged but not deployed yet, in which case "
            "wait for the rollout first")
    for name in sorted(set(live) - want):
        add(KINDS[1], [name],
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
    # One kind per side, not one aggregated finding: the kind is what a waiver
    # names, so aggregating them would let the waiver written for five closed
    # OUTPUT schemas silently also excuse those same five tools going closed on
    # the INPUT side -- same tool names, same `names` list, no new signal. That
    # is the exact path this file's own waiver predicts: seerrsense#70 opens
    # the zod output schemas, the next snapshot brings zod's closed inputs, and
    # the finding that should have died (exit 3, "delete the waiver") stays
    # alive instead.
    for kind, names, side in ((KINDS[2], closed_out, "output"),
                              (KINDS[3], closed_in, "input")):
        if not names:
            continue
        add(kind, names,
            f"{len(names)} stored {side}Schema(s) are closed "
            "(additionalProperties:false) -- a field or parameter added "
            "upstream fails the call" + (
                ", and re-snapshotting before the release that opens them is "
                "deployed just captures them closed again"
                if side == "output" else
                ", and a closed input schema may be deliberate upstream, in "
                "which case a KNOWN_STALE entry is the only way out") +
            ": " + ", ".join(names))
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
    ("seerrsense", "closed-output-schemas"): {
        "until": "2026-10-15",
        # The tools the waiver was written against. A finding is excused only
        # if every tool it names is in here, so a SIXTH seerrsense tool
        # acquiring a closed schema still fails -- without this the waiver
        # would cover the regression as well as the five known schemas, since
        # a side's finding arrives as one aggregated line. The kind pins the
        # side: the same five tools going closed on the INPUT side is a
        # different kind and is not excused here.
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
    # Every tool name waived under a key, ACROSS findings. `missing-tool` and
    # `extra-tool` arrive one finding per tool while the closed-schema kinds
    # arrive aggregated, so judging a waiver's width one finding at a time
    # would call a two-tool waiver too wide twice over, on a night when it is
    # working exactly as written.
    seen: dict[tuple[str, str], set[str]] = {}

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
        seen.setdefault(key, set()).update(f.get("names") or [])

    # The waiver covering MORE than what fired is a state worth a word: some of
    # the tools it was reviewed against have stopped firing -- a partial
    # upstream fix -- and the excuse silently keeps covering them, so one of
    # them regressing before the expiry date would be waived by a reason that
    # no longer applies to it. Not failing: nothing is stale. Maintenance, like
    # a waiver that excuses nothing at all, which is this same check at its
    # limit.
    for key, names in sorted(seen.items(), key=repr):
        w = KNOWN_STALE[key]
        gone = sorted(set(w.get("tools") or []) - names)
        if gone:
            maintenance.append(
                f"{key[0]}: the waiver for {key[1]} still names "
                f"{', '.join(gone)}, which no longer fire. Narrow it in "
                f"KNOWN_STALE to what is left, or delete it when nothing is. "
                f"({w['why']})")

    for key, w in sorted(KNOWN_STALE.items(), key=repr):
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


def waiver_is_wellformed(key, w) -> bool:
    """Both halves of a KNOWN_STALE key have to name something this file emits.

    A predicate rather than four conjuncts inline in selftest(), so the cases
    that matter -- a kind compare() cannot produce, a server not in OWNERS --
    are reachable. The committed table is valid by construction, so without
    them the clause that catches a rename or a singular typo is never seen to
    fire, and the cost of losing it is a nightly that reports a waived finding
    as a stale catalogue and sends someone to re-snapshot for it.
    """
    # Shape first. A three-element key passes an element-wise check and then
    # never matches the (server, kind) tuple apply_waivers() builds, so the
    # waiver is silently absent and its finding arrives at night as fresh
    # drift -- the exact failure this predicate exists to catch at PR time.
    if not isinstance(key, tuple) or len(key) != 2:
        return False
    try:
        _dt.date.fromisoformat(w["until"])
        return (bool(w.get("tools")) and bool(w.get("why"))
                and key[0] in OWNERS and key[1] in KINDS)
    except (KeyError, ValueError, TypeError):
        return False


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
        # An open schema carrying an example that spells the closed form is
        # open. Walking into `examples` reads a sample document as a schema.
        # ... and a PARAMETER named like one of those keywords is still
        # walked: inside `properties` the keys are the upstream's names.
        ("a closed schema under a property named default still fires",
         {"tools": [{"name": "a", "outputSchema": {
             "type": "object", "properties": {"default": {
                 "type": "object", "additionalProperties": False}}}}],
          "last_synced": ""}, allow(["a"]), 1),
        # One case per family of subschema location, since the walk names
        # twenty keywords and `properties`/`items` alone would leave the map,
        # list and value branches unexercised.
        ("a closed schema under $defs fires",
         {"tools": [{"name": "a", "outputSchema": {
             "$defs": {"row": {"type": "object", "additionalProperties": False}}}}],
          "last_synced": ""}, allow(["a"]), 1),
        ("a closed schema inside anyOf fires",
         {"tools": [{"name": "a", "outputSchema": {
             "anyOf": [{"type": "null"},
                       {"type": "object", "additionalProperties": False}]}}],
          "last_synced": ""}, allow(["a"]), 1),
        ("a closed schema in the tuple form of items fires",
         {"tools": [{"name": "a", "outputSchema": {
             "type": "array",
             "items": [{"type": "object", "additionalProperties": False}]}}],
          "last_synced": ""}, allow(["a"]), 1),
        ("a closed form inside examples is not a closed schema",
         {"tools": [{"name": "a", "outputSchema": {
             "type": "object", "properties": {"a": {"type": "string"}},
             "examples": [{"additionalProperties": False}]}}],
          "last_synced": ""}, allow(["a"]), 0),
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
         {"tools": "nope", "last_synced": ""}, allow(["a"]), "U"),
        # `tools: null` is the waiting-server shape, not a broken payload:
        # undetermined either way, but it has to reach the guard whose message
        # says a user must sign in.
        ("a result with no tool list at all is undetermined",
         {"status": "ready", "last_synced": ""}, allow(["a"]), "U"),
        ("a null catalogue is the waiting-server message",
         {"tools": None, "status": "waiting", "last_synced": ""}, allow(["a"]), "U"),
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
    ok = (kinds == {"missing-tool", "closed-output-schemas"}
          and all(f["names"] for f in got))
    print(f"{'ok  ' if ok else 'FAIL'} findings are labelled by kind and tools ({sorted(kinds)})")
    if not ok:
        failures.append("kinds")

    # The split by side, pinned: one tool closed on both sides is TWO findings,
    # because the kind is what a waiver names and an output-side waiver must
    # not excuse the same tool going closed on the input side.
    got = compare("s", snap(["a"], closed=True, closed_input=True), allow(["a"]))
    kinds = sorted(f["kind"] for f in got)
    ok = kinds == ["closed-input-schemas", "closed-output-schemas"]
    print(f"{'ok  ' if ok else 'FAIL'} a tool closed on both sides is two findings ({kinds})")
    if not ok:
        failures.append("both sides")

    # `tools: null` must reach the guard whose message names the remedy. Both
    # paths are exit 2, so the exit-code cases above cannot tell them apart --
    # the message IS the finding here.
    try:
        compare("s", {"tools": None, "status": "waiting", "last_synced": ""},
                allow(["a"]))
        ok = False
    except Undetermined as e:
        ok = "sign in" in str(e)
    print(f"{'ok  ' if ok else 'FAIL'} a null catalogue says a user must sign in")
    if not ok:
        failures.append("null catalogue message")

    # ... and the same shape with no `status: waiting` behind it must NOT say
    # that: the exit code is identical, so only the message separates "sign
    # in" from "the API answered oddly".
    try:
        compare("s", {"status": "ready", "last_synced": ""}, allow(["a"]))
        ok = False
    except Undetermined as e:
        ok = "sign in" not in str(e) and "without a tool list" in str(e)
    print(f"{'ok  ' if ok else 'FAIL'} a missing tool list does not claim the server is waiting")
    if not ok:
        failures.append("missing tool list message")

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
        KNOWN_STALE[("s", "closed-output-schemas")] = {
            "until": "2026-10-15", "tools": ["a", "b"], "why": "fixture"}
        finding = [{"server": "s", "kind": "closed-output-schemas", "names": ["a", "b"],
                    "message": "s: closed"}]
        grown = [{"server": "s", "kind": "closed-output-schemas", "names": ["a", "b", "c"],
                  "message": "s: closed"}]
        other = [{"server": "s", "kind": "missing-tool", "names": ["z"],
                  "message": "s: missing"}]
        per_tool = [{"server": "s", "kind": "missing-tool", "names": ["y"],
                     "message": "s: y missing"},
                    {"server": "s", "kind": "missing-tool", "names": ["z"],
                     "message": "s: z missing"}]

        shrunk = [{"server": "s", "kind": "closed-output-schemas", "names": ["a"],
                   "message": "s: a is closed"}]
        wcases = [
            ("a live waiver excuses the tools it names", finding, "2026-09-13", 0, 0),
            ("it still holds on the expiry date itself", finding, "2026-10-15", 0, 0),
            ("it stops excusing the day after", finding, "2026-10-16", 1, 0),
            ("a tool the waiver does not name still fails", grown, "2026-09-13", 1, 0),
            ("a waiver does not excuse another kind", finding + other, "2026-09-13", 1, 0),
            ("an unwaived finding fails and does not excuse the waiver",
             other, "2026-09-13", 1, 1),
            ("a waiver that excuses nothing needs maintenance", [], "2026-09-13", 0, 1),
            # The middle of that range: half the tools fixed. Nothing is
            # stale, so it must not fail -- but the waiver is now wider than
            # what fires, and left silent it would keep covering a tool that
            # closed again before the expiry date.
            ("a waiver wider than its finding needs narrowing",
             shrunk, "2026-09-13", 0, 1),
        ]
        # A server that could not be compared must not make its own waiver
        # look dead: it produces no findings by construction.
        _, _, maint = apply_waivers([], "2026-09-13", set())
        ok = not maint
        print(f"{'ok  ' if ok else 'FAIL'} an uncompared server does not condemn its waiver")
        if not ok:
            failures.append("uncompared server")

        # A per-tool kind: compare() emits one finding PER NAME for
        # missing-tool and extra-tool, so both waived tools arrive as separate
        # findings. Judged one finding at a time, each would look like the
        # other had stopped firing, and a waiver working exactly as written
        # would report itself broken twice a night. Its own table entry,
        # because a second waiver in the fixture would change every case above.
        KNOWN_STALE[("s", "missing-tool")] = {
            "until": "2026-10-15", "tools": ["y", "z"], "why": "fixture"}
        f_, _, m_ = apply_waivers(per_tool, "2026-09-13", {"s"})
        del KNOWN_STALE[("s", "missing-tool")]
        # The other fixture waiver fires nothing here and is swept as dead, so
        # only its own kind's lines are the subject.
        ok = not f_ and not [line for line in m_ if "missing-tool" in line]
        print(f"{'ok  ' if ok else 'FAIL'} a per-tool waiver matched in full is quiet")
        if not ok:
            failures.append("per-tool waiver")

        # And the loud half on the same kind: one of the two tools stopped
        # firing, so the waiver is genuinely wider than the night. `shrunk`
        # above cannot pin this -- it uses a kind that arrives as one
        # aggregated finding, where per-finding and unioned judging are
        # indistinguishable.
        KNOWN_STALE[("s", "missing-tool")] = {
            "until": "2026-10-15", "tools": ["y", "z"], "why": "fixture"}
        f_, _, m_ = apply_waivers(per_tool[:1], "2026-09-13", {"s"})
        del KNOWN_STALE[("s", "missing-tool")]
        narrow = [line for line in m_ if "missing-tool" in line and "z" in line]
        ok = not f_ and len(narrow) == 1
        print(f"{'ok  ' if ok else 'FAIL'} a per-tool waiver half matched needs narrowing")
        if not ok:
            failures.append("per-tool narrowing")

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
    # The key too, not just the body. Both halves have to line up with values
    # produced elsewhere in this file -- `kind` with what compare() emits,
    # `server` with OWNERS -- and neither was checked, so a rename here or a
    # singular typo in the next entry was silent until the nightly reported
    # the waived finding as exit 1, with a re-snapshot instruction that
    # re-captures exactly what the waiver was written for.
    for name, key, w, want in [
        ("a well-formed waiver passes", ("tg", "closed-output-schemas"),
         {"until": "2026-10-15", "tools": ["a"], "why": "fixture"}, True),
        ("a kind compare() cannot emit fails", ("tg", "closed-output-schema"),
         {"until": "2026-10-15", "tools": ["a"], "why": "fixture"}, False),
        ("a server not in OWNERS fails", ("nope", "closed-output-schemas"),
         {"until": "2026-10-15", "tools": ["a"], "why": "fixture"}, False),
        ("an undated waiver fails", ("tg", "closed-output-schemas"),
         {"until": "soon", "tools": ["a"], "why": "fixture"}, False),
        ("a waiver naming no tools fails", ("tg", "closed-output-schemas"),
         {"until": "2026-10-15", "tools": [], "why": "fixture"}, False),
        ("a key that is not a (server, kind) tuple fails", "seerrsense",
         {"until": "2026-10-15", "tools": ["a"], "why": "fixture"}, False),
        ("a three-element key fails",
         ("tg", "closed-output-schemas", "typo"),
         {"until": "2026-10-15", "tools": ["a"], "why": "fixture"}, False),
    ]:
        got = waiver_is_wellformed(key, w)
        print(f"{'ok  ' if got == want else 'FAIL'} {name}")
        if got != want:
            failures.append(name)

    # key=repr: a key written as a bare string instead of a 2-tuple is the
    # other easy typo here, and a plain sorted() compares str with tuple and
    # dies with a TypeError -- a traceback in place of the FAIL line that
    # names the offending key, which is the whole point of checking at PR time.
    for key, w in sorted(KNOWN_STALE.items(), key=repr):
        valid = waiver_is_wellformed(key, w)
        print(f"{'ok  ' if valid else 'FAIL'} committed waiver {key} names a known "
              "server and kind, is dated and names its tools")
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
        others = len(failing) + len(undetermined) + len(maintenance)
        if others:
            print(f"  (and {others} other finding(s) below -- stale catalogues, "
                  "servers that could not be compared, waivers to fix -- which "
                  "this exit status does not name)", file=sys.stderr)
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
        print("a waiver in this script needs attention -- it matches nothing, "
              "or it is wider than what fires (do NOT re-snapshot for either):",
              file=sys.stderr)
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
