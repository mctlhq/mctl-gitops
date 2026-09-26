#!/usr/bin/env python3
"""Validate the vendored MCP portal tool allowlists under
infrastructure/cloudflare/portal/allowlists/.

Part of mctlhq/mctl-gitops#1370 (PR A -- vendoring only; nothing here talks
to Cloudflare or Terraform). Six mechanisms used to write
`updated_tools` on the shared `mcp` portal object directly; this proposal
makes OpenTofu the single writer (a later PR) while keeping the *decision*
("this tool is safe to expose") in the service repo that ships the tool.
Each owning repo's `docs/portal-allowlist.json` is pinned here, byte-
identical, as `allowlists/<server>.json`, plus three small manifests this
script also checks:

  - `mapping.json`  -- {"servers": {"<id>": {"vendored", "default_disabled",
    "on_behalf", "updated_prompts", ["updated_tools"]}}}. Everything about a
    server's portal membership that is NOT the owning repo's call.
  - `sources.json`  -- {"servers": {"<id>": {"repo", "path", "ref", "sha",
    "vendored_at"}}}, the provenance of each vendored copy.
  - `baseline.json` -- {"servers": {"<id>": {"tools_total", "tools_enabled",
    "enabled_tools", "prompts_total", "prompts_enabled", ["enabled_prompts"],
    "recorded"}}}, the non-widening reference: a bump that raises a server's
    enabled/total tool count, or enables a tool NAME not listed in
    `enabled_tools` (or, in an `updated_prompts` list, a prompt name not in
    `enabled_prompts`), fails here until a human edits this file in the same
    diff.
  - `catalogue.json` -- {"servers": {"<id>": ["<tool>", ...]}}, each server's
    synced catalogue in portal order. mcp-portal.tf walks it to build
    `updated_tools` (provider 5.24 cannot read the catalogue itself, #1382).

What this script enforces, and what it deliberately does not:

  - shape: each `allowlists/<id>.json` is the service repo's file
    byte-identical, so its top-level keys are exactly the allowed set
    `{"$comment", "portal", "server", "default_disabled", "tools"}`; `portal`
    is `"mcp"`; `server` equals the file's own stem; `default_disabled` is
    `true`; `tools` is a non-empty list; each entry's keys are drawn from
    `{"name", "enabled", "reason", "upstream_gates", "override"}`, `name` is
    a non-empty string with no duplicates, `enabled` a boolean, `reason` a
    non-empty string, and `override`, when present, is exactly
    `"sensitive-read"` on an entry with `enabled: false` (it only ever
    narrows exposure -- see design.md amendment 4).
  - coverage: the set of `allowlists/*.json` files equals the set of
    `mapping.json` servers marked `vendored: true`; a non-vendored server's
    mapping entry carries a literal `updated_tools` list instead; every
    vendored server has a `sources.json` provenance entry.
  - existence: every server named in `mapping.json` is either on the
    commented `UNMANAGED` list (the `#1363` seam; empty since every mapped
    server got its resource) or has a literal
    `resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "<id>"`
    in `mcp-servers.tf` -- a literal grep rather than an HCL parser.
  - mapping entries: each `mapping.json` server carries exactly
    `vendored`, `default_disabled`, `on_behalf` and `updated_prompts`, plus
    `updated_tools` if and only if it is not vendored. The three switches are
    booleans -- PR B sends `default_disabled`/`on_behalf` to the portal as
    they stand, so a typo there must not reach the API.
  - literal mappings: a non-vendored server's `updated_tools` gets the same
    per-entry checks as a vendored file's tools (keys exactly `name` and
    `enabled`, `name` a non-empty unique string, `enabled` a boolean), minus
    the `reason` requirement -- a missing reason is exactly why such a server
    is not vendored. Every server's `updated_prompts` is `null` (no override)
    or a list of such `{name, enabled}` entries.
  - catalogue: `catalogue.json` names exactly the `mapping.json` servers,
    each a non-empty list of unique non-empty strings, and every name in it
    has a decision -- an entry in the vendored file or in the literal
    `updated_tools`. A catalogue tool with no decision would fail the plan
    on a lookup; here it fails with the server and tool named.
  - non-widening, for EVERY server in `mapping.json`, vendored or not:
    tools_total/tools_enabled (counted from the vendored file, or from the
    literal `updated_tools`) must not exceed `baseline.json`; every enabled
    tool name must appear in the server's `enabled_tools` there, so turning a
    read tool off and a write tool on at a constant count still fails (a
    count alone cannot see that swap); and the
    effective number of enabled prompts must not exceed `prompts_enabled`,
    where `updated_prompts: null` counts as all `prompts_total` enabled (no
    override means the portal shows every catalogue prompt), so replacing a
    narrowing list with `null` is caught as a widening too.

Two keys share the name `default_disabled` and mean opposite things. In a
vendored `allowlists/<id>.json` it is the owning repo's posture ("a tool this
file does not list is disabled") and must be `true`. In `mapping.json` it is
the portal object's per-server switch ("this server is off by default for
connecting clients"), copied from the live portal and `false` today. They are
expected to disagree; PR B must read the portal one from `mapping.json` only.

What it does NOT do: compare a vendored file against the server's live,
synced tool *catalogue*. CI holds no Cloudflare credential for this root
(#1111), so it cannot know which of a file's entries the portal has even
synced. Measured 2026-09-25 (design.md amendment 5): the `tg` file lists
more tools than its live catalogue -- upstream-gated entries
(`account:manage`, `admin:broadcast` scopes the portal's own OAuth grant does
not request) that exist upstream but that the portal has never seen. This is
why `baseline.json`'s tools_total/tools_enabled here are the vendored FILE's
own counts, not the live/catalogue-restricted counts quoted in the
proposal's requirements.md acceptance criteria (alice 12/12, projects 8/8,
tg 30/30, api 75/75, coolify 22/45, seerrsense 5/5). For the vendored
servers the two agree except tg (37 file entries, 36 enabled) and api (92
file entries, 77 enabled; vendored once mctlhq/mctl-api#396 gave every entry
a reason). In both, the extra entries are tools the portal has not synced,
and mcp-portal.tf leaves them out by walking catalogue.json. This script has no way to compute the
catalogue-restricted number, so it deliberately does not try to reproduce it;
it only refuses a FUTURE bump that grows a file's own counts past what is
already committed, which is the one thing it can check without a live
credential. Reconciling a file's extra entries against the live catalogue is
explicitly PR B's job (`updated_tools` sent to the API is the file's entries
intersected with the synced catalogue) -- see design.md's "Consequence for
PR B" paragraph. `allowlists/baseline.json`'s prompts_total/prompts_enabled,
by contrast, come straight from the live snapshot recorded in this
proposal's `live-snapshot-2026-09-25.json`, because no service repo ships a
prompts file for this script to compare against in the first place.

Usage:
    scripts/validate-portal-allowlists.py             validate the real
                                                        allowlists/ directory
    scripts/validate-portal-allowlists.py --widening-ok
                                                      the same, but a
                                                        widening against
                                                        baseline.json is a
                                                        warning, not an error:
                                                        the bump workflow
                                                        still opens its PR,
                                                        which stays red until
                                                        a human edits
                                                        baseline.json in it
    scripts/validate-portal-allowlists.py --vendor-check
                                                      compare each vendored
                                                        file with its owning
                                                        repo at the recorded
                                                        sha and at main
                                                        (network; see
                                                        vendor_check())
    scripts/validate-portal-allowlists.py --selftest   replay
                                                        scripts/tests/fixtures/portal-allowlists/{valid,invalid}
                                                        and assert every
                                                        valid/ case passes and
                                                        every invalid/ case
                                                        fails
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORTAL_DIR = ROOT / "infrastructure" / "cloudflare" / "portal"
ALLOWLISTS_DIR = PORTAL_DIR / "allowlists"
MCP_SERVERS_TF = PORTAL_DIR / "mcp-servers.tf"
FIXTURES_ROOT = ROOT / "scripts" / "tests" / "fixtures" / "portal-allowlists"

# mapping.json / sources.json / baseline.json / catalogue.json are manifests about the
# vendored files, not vendored files themselves -- excluded from the glob
# that discovers "one file per server".
SPECIAL_FILES = {"mapping.json", "sources.json", "baseline.json", "catalogue.json"}

ALLOWED_TOP_KEYS = {"$comment", "portal", "server", "default_disabled", "tools"}
REQUIRED_TOP_KEYS = {"portal", "server", "default_disabled", "tools"}
ALLOWED_TOOL_KEYS = {"name", "enabled", "reason", "upstream_gates", "override"}
LITERAL_ENTRY_KEYS = {"name", "enabled"}
PORTAL_ID = "mcp"
TF_RESOURCE_TYPE = "cloudflare_zero_trust_access_ai_controls_mcp_server"
MAPPING_SWITCHES = ("vendored", "default_disabled", "on_behalf")
MAPPING_KEYS = {*MAPPING_SWITCHES, "updated_prompts"}

# Mapped on the portal, no Terraform resource of their own yet -- the
# `#1363` seam. Recorded here, not discovered, so closing #1363 is a
# deletion from this one list rather than a rediscovery. Empty since
# 2026-09-26: `seerrsense` and then `api` were adopted into mcp-servers.tf.
# Kept as a named empty set so a future portal-first server has a place to go.
UNMANAGED: set[str] = set()


class Unreadable(Exception):
    """A file could not be read as JSON at all -- distinct from a shape error."""


def load_json(path: pathlib.Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise Unreadable(f"{path}: could not be read: {e}")
    except json.JSONDecodeError as e:
        raise Unreadable(f"{path}: not valid JSON: {e}")


def check_shape(server_id: str, data, errors: list[str]) -> None:
    """The vendored file's own shape: the allowed key set, all six live
    service files carry today (measured 2026-09-25) -- a byte-identical copy
    must pass this unchanged.
    """
    prefix = f"allowlists/{server_id}.json"
    if not isinstance(data, dict):
        errors.append(f"{prefix}: top-level value is a {type(data).__name__}, expected an object")
        return
    unknown = set(data) - ALLOWED_TOP_KEYS
    if unknown:
        errors.append(f"{prefix}: top-level key(s) outside the allowed set: {sorted(unknown)}")
    missing = REQUIRED_TOP_KEYS - set(data)
    if missing:
        errors.append(f"{prefix}: missing required top-level key(s): {sorted(missing)}")
        return
    if data.get("portal") != PORTAL_ID:
        errors.append(f"{prefix}: portal is {data.get('portal')!r}, expected {PORTAL_ID!r}")
    if data.get("server") != server_id:
        errors.append(
            f"{prefix}: server is {data.get('server')!r}, expected {server_id!r} (the file's own stem)"
        )
    if data.get("default_disabled") is not True:
        errors.append(f"{prefix}: default_disabled is {data.get('default_disabled')!r}, expected true")

    tools = data.get("tools")
    if not isinstance(tools, list):
        errors.append(f"{prefix}: tools is a {type(tools).__name__}, expected a list")
        return
    if not tools:
        errors.append(f"{prefix}: tools is empty")
        return

    seen_names: set[str] = set()
    for i, t in enumerate(tools):
        tp = f"{prefix}: tools[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{tp}: entry is a {type(t).__name__}, expected an object")
            continue
        unknown_t = set(t) - ALLOWED_TOOL_KEYS
        if unknown_t:
            errors.append(f"{tp}: key(s) outside the allowed set: {sorted(unknown_t)}")

        name = t.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{tp}: name is not a non-empty string ({name!r})")
        elif name in seen_names:
            errors.append(f"{prefix}: duplicate tool name {name!r}")
        else:
            seen_names.add(name)

        enabled = t.get("enabled")
        if not isinstance(enabled, bool):
            errors.append(f"{tp} ({name!r}): enabled is not a boolean ({enabled!r})")

        reason = t.get("reason")
        if not isinstance(reason, str) or not reason:
            errors.append(f"{tp} ({name!r}): reason is not a non-empty string")

        if "override" in t:
            override = t.get("override")
            if override != "sensitive-read":
                errors.append(
                    f"{tp} ({name!r}): override is {override!r}, only 'sensitive-read' is allowed"
                )
            elif enabled is not False:
                # It only ever narrows exposure (design.md amendment 4): an
                # override on an ENABLED entry is not a narrowing, and the
                # gitops validator accepts it only paired with enabled:false.
                errors.append(
                    f"{tp} ({name!r}): override is set on an entry that is not enabled: false"
                )


def check_literal_entries(where: str, entries, errors: list[str]) -> None:
    """A `{name, enabled}` list written in mapping.json itself: a
    non-vendored server's `updated_tools`, or any server's `updated_prompts`.
    Same per-entry rules as a vendored file's tools, without `reason`.
    """
    if not isinstance(entries, list):
        errors.append(f"{where}: is a {type(entries).__name__}, expected a list")
        return
    seen: set[str] = set()
    for i, e in enumerate(entries):
        ep = f"{where}[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{ep}: entry is a {type(e).__name__}, expected an object")
            continue
        extra = set(e) - LITERAL_ENTRY_KEYS
        if extra:
            errors.append(f"{ep}: key(s) outside {sorted(LITERAL_ENTRY_KEYS)}: {sorted(extra)}")
        name = e.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{ep}: name is not a non-empty string ({name!r})")
        elif name in seen:
            errors.append(f"{where}: duplicate name {name!r}")
        else:
            seen.add(name)
        if not isinstance(e.get("enabled"), bool):
            errors.append(f"{ep} ({name!r}): enabled is not a boolean ({e.get('enabled')!r})")


def check_mapping_entry(sid: str, s, errors: list[str]) -> None:
    """The keys PR B turns into the portal's `servers[]` element. Its
    `default_disabled`/`on_behalf` go to the API verbatim, so a string or a
    misspelt key here would be a live change, not a lint.
    """
    where = f"allowlists/mapping.json: {sid!r}"
    if not isinstance(s, dict):
        errors.append(f"{where}: entry is a {type(s).__name__}, expected an object")
        return
    allowed = MAPPING_KEYS if s.get("vendored") is True else MAPPING_KEYS | {"updated_tools"}
    unknown = set(s) - allowed
    if unknown:
        errors.append(f"{where}: key(s) outside the allowed set: {sorted(unknown)}")
    missing = MAPPING_KEYS - set(s)
    if missing:
        errors.append(f"{where}: missing key(s): {sorted(missing)}")
    for key in MAPPING_SWITCHES:
        if key in s and not isinstance(s[key], bool):
            errors.append(f"{where}: {key} is not a boolean ({s[key]!r})")


def check_coverage(file_ids: set[str], mapping, errors: list[str]) -> dict:
    """{files} == {mapping.json servers where vendored}, and a non-vendored
    entry declares its mapping literally (design.md's escape hatch for a
    server with no vendored file).
    """
    servers = mapping.get("servers") if isinstance(mapping, dict) else None
    if not isinstance(servers, dict):
        errors.append("allowlists/mapping.json: missing or malformed top-level 'servers' object")
        return {}

    for sid in sorted(servers):
        check_mapping_entry(sid, servers[sid], errors)

    vendored_ids = {sid for sid, s in servers.items() if isinstance(s, dict) and s.get("vendored") is True}
    non_vendored_ids = set(servers) - vendored_ids

    for sid in sorted(file_ids - vendored_ids):
        errors.append(f"allowlists/{sid}.json: exists, but mapping.json has no vendored entry named {sid!r}")
    for sid in sorted(vendored_ids - file_ids):
        errors.append(f"allowlists/mapping.json: server {sid!r} is vendored, but allowlists/{sid}.json does not exist")

    for sid in sorted(non_vendored_ids):
        s = servers[sid]
        if not isinstance(s, dict) or not isinstance(s.get("updated_tools"), list):
            errors.append(
                f"allowlists/mapping.json: server {sid!r} is not vendored and must carry a literal "
                "updated_tools list"
            )
            continue
        check_literal_entries(f"allowlists/mapping.json: {sid!r} updated_tools", s["updated_tools"], errors)

    for sid in sorted(servers):
        s = servers[sid]
        if isinstance(s, dict) and s.get("updated_prompts") is not None:
            check_literal_entries(
                f"allowlists/mapping.json: {sid!r} updated_prompts", s["updated_prompts"], errors
            )

    return servers


def check_sources(vendored_ids: set[str], sources, errors: list[str]) -> None:
    entries = sources.get("servers") if isinstance(sources, dict) else None
    if not isinstance(entries, dict):
        errors.append("allowlists/sources.json: missing or malformed top-level 'servers' object")
        entries = {}
    for sid in sorted(vendored_ids):
        e = entries.get(sid)
        if not isinstance(e, dict):
            errors.append(f"allowlists/sources.json: no provenance entry for vendored server {sid!r}")
            continue
        for key in ("repo", "path", "ref", "sha", "vendored_at"):
            v = e.get(key)
            if not isinstance(v, str) or not v:
                errors.append(f"allowlists/sources.json: {sid!r} entry missing a non-empty {key!r}")


def check_existence(server_ids: set[str], tf_text: str, errors: list[str]) -> None:
    """Every server named anywhere in the allowlists is either on UNMANAGED
    (the #1363 seam) or has a literal resource block in mcp-servers.tf --
    a literal grep rather than an HCL parser.
    """
    for sid in sorted(server_ids):
        if sid in UNMANAGED:
            continue
        needle = f'resource "{TF_RESOURCE_TYPE}" "{sid}"'
        if needle not in tf_text:
            errors.append(
                f"{sid!r}: no {needle} in mcp-servers.tf, and {sid!r} is not on the commented "
                f"UNMANAGED list ({sorted(UNMANAGED)}) -- add the resource, or add it to UNMANAGED "
                "if this is the #1363 split"
            )


def check_catalogue(files: dict, servers: dict, catalogue, errors: list[str]) -> None:
    entries = catalogue.get("servers") if isinstance(catalogue, dict) else None
    if not isinstance(entries, dict):
        errors.append("allowlists/catalogue.json: missing or malformed top-level 'servers' object")
        return
    for sid in sorted(set(servers) - set(entries)):
        errors.append(f"allowlists/catalogue.json: no catalogue for mapped server {sid!r}")
    for sid in sorted(set(entries) - set(servers)):
        errors.append(f"allowlists/catalogue.json: {sid!r} is not a mapping.json server")
    for sid in sorted(set(entries) & set(servers)):
        names = entries[sid]
        where = f"allowlists/catalogue.json: {sid!r}"
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
            errors.append(f"{where}: is not a non-empty list of non-empty strings")
            continue
        if len(set(names)) != len(names):
            errors.append(f"{where}: lists {sorted({n for n in names if names.count(n) > 1})} more than once")
        s = servers[sid]
        if not isinstance(s, dict):
            continue  # already reported by coverage
        tools = files.get(sid, {}).get("tools") if s.get("vendored") is True and isinstance(files.get(sid), dict) \
            else (s.get("updated_tools") if s.get("vendored") is not True else None)
        if not isinstance(tools, list) or not tools:
            continue  # already reported by shape/coverage
        decided = {t.get("name") for t in tools if isinstance(t, dict)}
        undecided = [n for n in names if n not in decided]
        if undecided:
            errors.append(
                f"{where}: catalogue tool(s) with no decision in the allowlist: {undecided} -- "
                "the owning repo's allowlist must list every tool the portal has synced"
            )


def check_baseline(files: dict, servers: dict, baseline, errors: list[str]) -> None:
    """Non-widening, for every server in mapping.json: tools counted from the
    vendored file (see the module docstring for why the FILE's own counts,
    not a catalogue-restricted one) or from the literal updated_tools, and
    prompts counted with `null` meaning all catalogue prompts enabled.
    """
    entries = baseline.get("servers") if isinstance(baseline, dict) else None
    if not isinstance(entries, dict):
        errors.append("allowlists/baseline.json: missing or malformed top-level 'servers' object")
        entries = {}

    for sid in sorted(servers):
        s = servers[sid]
        if not isinstance(s, dict):
            continue  # already reported by coverage
        if s.get("vendored") is True:
            data = files.get(sid)
            tools = data.get("tools") if isinstance(data, dict) else None
            where = f"allowlists/{sid}.json"
        else:
            tools = s.get("updated_tools")
            where = f"allowlists/mapping.json: {sid!r} updated_tools"
        if not isinstance(tools, list):
            continue  # already reported by shape/coverage

        b = entries.get(sid)
        if not isinstance(b, dict):
            errors.append(f"allowlists/baseline.json: no entry for server {sid!r}")
            continue
        ints = {k: b.get(k) for k in ("tools_total", "tools_enabled", "prompts_total", "prompts_enabled")}
        bad = [k for k, v in ints.items() if not isinstance(v, int) or isinstance(v, bool)]
        if bad:
            errors.append(f"allowlists/baseline.json: {sid!r} {', '.join(bad)} not integer(s)")
            continue

        # No `continue` on a malformed enabled_tools: the count and prompt
        # widening checks below still run, so one pass reports everything.
        names = b.get("enabled_tools")
        if not isinstance(names, list) or not all(isinstance(n, str) and n for n in names):
            errors.append(f"allowlists/baseline.json: {sid!r} enabled_tools is not a list of non-empty strings")
            names = None
        else:
            if len(set(names)) != len(names):
                dups = sorted({n for n in names if names.count(n) > 1})
                errors.append(f"allowlists/baseline.json: {sid!r} enabled_tools lists {dups} more than once")
            if len(set(names)) != ints["tools_enabled"]:
                errors.append(
                    f"allowlists/baseline.json: {sid!r} enabled_tools names {len(set(names))} distinct tool(s) "
                    f"but tools_enabled is {ints['tools_enabled']} -- the two must agree"
                )

        total = len(tools)
        enabled_names = {
            t["name"] for t in tools
            if isinstance(t, dict) and t.get("enabled") is True and isinstance(t.get("name"), str)
        }
        unlisted = sorted(enabled_names - set(names)) if names is not None else []
        if unlisted:
            errors.append(
                f"{where}: enables tool(s) not in baseline.json's enabled_tools for {sid!r}: {unlisted}; "
                "add them there in the same change if this widening is intentional"
            )
        enabled = sum(1 for t in tools if isinstance(t, dict) and t.get("enabled") is True)
        if enabled > ints["tools_enabled"] or total > ints["tools_total"]:
            errors.append(
                f"{where}: widens exposure -- {enabled}/{total} tools enabled/total now, "
                f"baseline.json records {ints['tools_enabled']}/{ints['tools_total']} for {sid!r}; "
                "update baseline.json in the same change if this widening is intentional"
            )

        prompts = s.get("updated_prompts")
        if prompts is None:
            p_enabled = ints["prompts_total"]  # no override: every catalogue prompt is shown
        elif isinstance(prompts, list):
            p_enabled = sum(1 for p in prompts if isinstance(p, dict) and p.get("enabled") is True)
            # The name gate for prompts, as enabled_tools is for tools: a
            # count alone passes one prompt off and another on. Only a list
            # can be checked by name -- null means "every catalogue prompt",
            # whose names this script cannot know -- and an absent
            # enabled_prompts means none may be enabled.
            allowed_p = b.get("enabled_prompts", [])
            if not isinstance(allowed_p, list) or not all(isinstance(n, str) and n for n in allowed_p):
                errors.append(f"allowlists/baseline.json: {sid!r} enabled_prompts is not a list of non-empty strings")
            else:
                # The same two consistency rules enabled_tools has, so a stale
                # name cannot sit here pre-authorising a prompt.
                if len(set(allowed_p)) != len(allowed_p):
                    errors.append(
                        f"allowlists/baseline.json: {sid!r} enabled_prompts lists "
                        f"{sorted({n for n in allowed_p if allowed_p.count(n) > 1})} more than once")
                if len(set(allowed_p)) != ints["prompts_enabled"]:
                    errors.append(
                        f"allowlists/baseline.json: {sid!r} enabled_prompts names {len(set(allowed_p))} "
                        f"distinct prompt(s) but prompts_enabled is {ints['prompts_enabled']} -- the two must agree")
                unlisted_p = sorted(
                    {p["name"] for p in prompts
                     if isinstance(p, dict) and p.get("enabled") is True and isinstance(p.get("name"), str)}
                    - set(allowed_p)
                )
                if unlisted_p:
                    errors.append(
                        f"allowlists/mapping.json: {sid!r} updated_prompts enables prompt(s) not in "
                        f"baseline.json's enabled_prompts: {unlisted_p}; add them there in the same change "
                        "if this widening is intentional"
                    )
        else:
            continue  # already reported by check_literal_entries
        if p_enabled > ints["prompts_enabled"]:
            shown = "null (no override, all shown)" if prompts is None else f"{p_enabled} enabled"
            errors.append(
                f"allowlists/mapping.json: {sid!r} updated_prompts widens exposure -- {shown}, "
                f"baseline.json records {ints['prompts_enabled']}/{ints['prompts_total']}; update "
                "baseline.json in the same change if this widening is intentional"
            )


def run(allowlists_dir: pathlib.Path, tf_text: str) -> list[str]:
    """Validate one allowlists/-shaped directory. Used both for the real
    infrastructure/cloudflare/portal/allowlists/ and for each --selftest
    fixture case, so a fixture is exactly the directory shape this script
    already knows how to read -- no separate fixture-only code path.
    """
    errors: list[str] = []
    files: dict[str, object] = {}

    for path in sorted(allowlists_dir.glob("*.json")):
        if path.name in SPECIAL_FILES:
            continue
        sid = path.stem
        try:
            data = load_json(path)
        except Unreadable as e:
            errors.append(str(e))
            continue
        files[sid] = data
        check_shape(sid, data, errors)

    mapping_path = allowlists_dir / "mapping.json"
    mapping: dict = {}
    if not mapping_path.is_file():
        errors.append("allowlists/mapping.json: missing")
    else:
        try:
            mapping = load_json(mapping_path)
        except Unreadable as e:
            errors.append(str(e))

    servers = check_coverage(set(files), mapping, errors)
    vendored_ids = {sid for sid, s in servers.items() if isinstance(s, dict) and s.get("vendored") is True}

    sources_path = allowlists_dir / "sources.json"
    sources: dict = {}
    if not sources_path.is_file():
        errors.append("allowlists/sources.json: missing")
    else:
        try:
            sources = load_json(sources_path)
        except Unreadable as e:
            errors.append(str(e))
    check_sources(vendored_ids, sources, errors)

    check_existence(set(servers) | set(files), tf_text, errors)

    baseline_path = allowlists_dir / "baseline.json"
    baseline: dict = {}
    if not baseline_path.is_file():
        errors.append("allowlists/baseline.json: missing")
    else:
        try:
            baseline = load_json(baseline_path)
        except Unreadable as e:
            errors.append(str(e))
    check_baseline(files, servers, baseline, errors)

    catalogue_path = allowlists_dir / "catalogue.json"
    catalogue: dict = {}
    if not catalogue_path.is_file():
        errors.append("allowlists/catalogue.json: missing")
    else:
        try:
            catalogue = load_json(catalogue_path)
        except Unreadable as e:
            errors.append(str(e))
    check_catalogue(files, servers, catalogue, errors)

    return errors


def case_tf_text(case_dir: pathlib.Path) -> str | None:
    """A fixture may ship its own mcp-servers.tf to exercise the existence
    check without depending on (or polluting) the real one -- the same
    opt-in shape validate-agent-platform.py uses for its own cross-checks.
    """
    fixture_tf = case_dir / "mcp-servers.tf"
    path = fixture_tf if fixture_tf.is_file() else MCP_SERVERS_TF
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        # Not "": a case whose servers are all UNMANAGED would then pass
        # without the existence check having read anything. The caller
        # reports the case as a selftest problem instead.
        return None


def case_dirs(parent: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in parent.iterdir() if p.is_dir()) if parent.is_dir() else []


def run_selftest() -> tuple[list[str], int, int]:
    """A detector never seen to fire is not known to work: replay every
    fixture under valid/ and invalid/ and assert the expected outcome. Each
    invalid/<case>/ names the error it exists for in expect.txt (a substring
    one of its errors must contain), so a case cannot silently keep "failing"
    on some other check after its own detector is gone. An absent or empty
    fixture tree is a failure, not a pass.
    """
    problems: list[str] = []
    valid, invalid = case_dirs(FIXTURES_ROOT / "valid"), case_dirs(FIXTURES_ROOT / "invalid")
    if not valid or not invalid:
        problems.append(
            f"{FIXTURES_ROOT}: valid/ has {len(valid)} case(s) and invalid/ {len(invalid)} -- "
            "refusing to pass vacuously"
        )
        return problems, len(valid), len(invalid)

    def tf_or_problem(case_dir: pathlib.Path) -> str | None:
        tf = case_tf_text(case_dir)
        if tf is None:
            problems.append(f"fixture {case_dir.name!r}: no readable mcp-servers.tf (own or fallback {MCP_SERVERS_TF})")
        return tf

    for case_dir in valid:
        tf = tf_or_problem(case_dir)
        if tf is None:
            continue
        errors = run(case_dir, tf)
        if errors:
            problems.append(f"valid fixture {case_dir.name!r} unexpectedly failed:")
            problems.extend(f"  {e}" for e in errors)

    for case_dir in invalid:
        expect_path = case_dir / "expect.txt"
        if not expect_path.is_file():
            problems.append(f"invalid fixture {case_dir.name!r} has no expect.txt naming the error it exists for")
            continue
        expect = expect_path.read_text(encoding="utf-8").strip()
        tf = tf_or_problem(case_dir)
        if tf is None:
            continue
        errors = run(case_dir, tf)
        if not any(expect in e for e in errors):
            problems.append(
                f"invalid fixture {case_dir.name!r}: no error contains {expect!r}; got {errors or 'none'}"
            )

    return problems, len(valid), len(invalid)


# The phrases check_baseline() uses for a widening, and nothing else. Only
# these become warnings under --widening-ok: a shape, coverage or catalogue
# error still fails the bump workflow before it commits anything.
WIDENING_MARKERS = (
    "widens exposure",
    "not in baseline.json's enabled_tools",
    "not in baseline.json's enabled_prompts",
)


def is_widening(error: str) -> bool:
    return any(m in error for m in WIDENING_MARKERS)


# --vendor-check. Repositories whose files cannot be read anonymously; named
# rather than probed, as in portal-catalogue-drift.py's PRIVATE_OWNERS.
PRIVATE_REPOS = {"mctlhq/projects-mcp"}
TOKEN_ENV = "ALLOWLIST_TOKEN"
USER_AGENT = "mctl-gitops-validate-portal-allowlists"


class Undetermined(Exception):
    """A side of the comparison could not be read. Not drift."""


def fetch_bytes(repo: str, path: str, ref: str) -> bytes:
    """The owning repo's file at `ref`, byte for byte (the vendored copy is
    compared byte-identical, so a JSON round-trip would hide a difference)."""
    if repo in PRIVATE_REPOS:
        token = os.environ.get(TOKEN_ENV)
        if not token:
            raise Undetermined(f"{repo} is private and ${TOKEN_ENV} is not set")
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"}
    else:
        url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
        headers = {}
    headers["User-Agent"] = USER_AGENT
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise Undetermined(f"{repo}@{ref}: answered {e.code}")
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        # HTTPException (IncompleteRead, BadStatusLine) is not an OSError and
        # escapes urlopen/read; uncaught it would exit 1, the tamper alarm.
        raise Undetermined(f"{repo}@{ref}: unreachable: {e!r}")


def vendor_check(allowlists_dir: pathlib.Path, fetch=fetch_bytes) -> tuple[int, list[str]]:
    """Each vendored file against its recorded source sha, and against main.

    Four outcomes per server, reported distinctly because they have
    different remedies:
      - in sync: the file equals the sha and main -- quiet;
      - lag: it equals the sha but main has moved -- a bump is due (the
        owning repo's dispatch did not run, or its PR is not merged yet);
      - tampered: it differs from the sha it claims to be -- someone edited
        the vendored copy here, which only a bump PR may do;
      - undetermined: a side could not be read -- not a finding.
    Exit: 1 if anything is tampered, else 3 if anything lags, else 2 if
    anything was undetermined, else 0.
    """
    lines: list[str] = []
    tampered = lagging = False
    # A count, not a flag: the note below says how many, and counting the
    # rendered lines for a word would tie that number to message wording.
    undetermined = 0
    try:
        sources = json.loads((allowlists_dir / "sources.json").read_text(encoding="utf-8"))["servers"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return 2, [f"sources.json could not be read: {e!r}"]
    if not isinstance(sources, dict):
        return 2, ["sources.json 'servers' is not an object"]
    for sid in sorted(sources):
        src = sources[sid]
        if not isinstance(src, dict) or not all(isinstance(src.get(k), str) and src.get(k)
                                                for k in ("repo", "path", "sha")):
            lines.append(f"{sid}: undetermined -- its sources.json entry lacks repo/path/sha")
            undetermined += 1
            continue
        local_path = allowlists_dir / f"{sid}.json"
        try:
            local = local_path.read_bytes()
        except OSError as e:
            lines.append(f"{sid}: undetermined -- the vendored file could not be read: {e!r}")
            undetermined += 1
            continue
        try:
            at_sha = fetch(src["repo"], src["path"], src["sha"])
        except Undetermined as e:
            lines.append(f"{sid}: undetermined -- {e}")
            undetermined += 1
            continue
        if local != at_sha:
            lines.append(
                f"{sid}: TAMPERED -- allowlists/{sid}.json differs from {src['repo']}@{src['sha'][:7]}, "
                "the commit sources.json says it was vendored from; only a bump PR may change it")
            tampered = True
            continue
        try:
            at_main = fetch(src["repo"], src["path"], src.get("ref") or "main")
        except Undetermined as e:
            lines.append(f"{sid}: matches its recorded sha; main undetermined -- {e}")
            undetermined += 1
            continue
        if at_main != at_sha:
            # The git blob sha of main's content lets the drift workflow tell
            # a bump PR that carries exactly this content from a stale one.
            blob = hashlib.sha1(b"blob %d\0" % len(at_main) + at_main).hexdigest()
            lines.append(
                f"{sid}: lags -- {src['repo']} main has a newer {src['path']} (blob {blob}); the bump "
                "dispatch did not run or its PR is not merged (dispatch portal-allowlist-vendor.yml by hand if needed)")
            lagging = True
        else:
            lines.append(f"{sid}: in sync with {src['repo']}@{src['sha'][:7]} and main")
    code = 1 if tampered else 3 if lagging else 2 if undetermined else 0
    if code in (1, 3) and undetermined:
        # Exit 1 and 3 outrank 2, so say what the status does not name (the
        # convention of portal-catalogue-drift.py's exit-4 and exit-5 notes).
        lines.append(f"(and {undetermined} server(s) that could not be compared, undetermined, "
                     "which this exit status does not name)")
    return code, lines


def vendor_check_selftest() -> list[str]:
    """T2: the four outcomes, with the network replaced by a dict."""
    import tempfile
    problems: list[str] = []
    a, b = b'{"v": 1}\n', b'{"v": 2}\n'
    cases = [
        ("equal to sha and main is quiet", a, {"S": a, "main": a}, 0),
        ("equal to sha, main moved is a lag", a, {"S": a, "main": b}, 3),
        ("differs from the recorded sha is tampered", b, {"S": a, "main": b}, 1),
        ("an unreadable upstream is undetermined, not drift", a, {}, 2),
        ("sha readable, main unreadable is undetermined", a, {"S": a}, 2),
    ]
    for label, local, remote, want in cases:
        with tempfile.TemporaryDirectory() as d:
            dp = pathlib.Path(d)
            (dp / "sources.json").write_text(json.dumps({"servers": {"w": {
                "repo": "mctlhq/w", "path": "docs/portal-allowlist.json", "ref": "main", "sha": "S",
                "vendored_at": "2026-09-25T00:00:00Z"}}}))
            (dp / "w.json").write_bytes(local)

            def stub(repo, path, ref, remote=remote):
                if ref not in remote:
                    raise Undetermined(f"{repo}@{ref}: stubbed 404")
                return remote[ref]
            code, lines = vendor_check(dp, stub)
        if code != want:
            problems.append(f"vendor-check: {label}: exit {code}, expected {want} ({lines})")
        # cloudflare-drift.yml compares this against the contents API's sha
        # of a bump PR's file; it must be git's blob sha (git hash-object).
        if want == 3 and not any("(blob 206a61de086a50dcac3be5aa7b5196bf4ef754f6)" in ln for ln in lines):
            problems.append(f"vendor-check: {label}: the lag line lacks main's git blob sha ({lines})")
    # A lag (3) or a tamper (1) outranks an undetermined server; the output
    # must still name it. Both sides of the `code in (1, 3)` guard.
    for label, local_w, want in (("a lag", a, 3), ("a tamper", b, 1)):
        with tempfile.TemporaryDirectory() as d:
            dp = pathlib.Path(d)
            ent = {"path": "docs/portal-allowlist.json", "ref": "main", "sha": "S",
                   "vendored_at": "2026-09-25T00:00:00Z"}
            (dp / "sources.json").write_text(json.dumps({"servers": {
                "w": {**ent, "repo": "mctlhq/w"}, "x": {**ent, "repo": "mctlhq/x"}}}))
            (dp / "w.json").write_bytes(local_w)
            (dp / "x.json").write_bytes(a)

            def stub2(repo, path, ref):
                if repo == "mctlhq/x":
                    raise Undetermined(f"{repo}@{ref}: stubbed 404")
                return {"S": a, "main": b}[ref]
            code, lines = vendor_check(dp, stub2)
        if code != want or not any("1 server(s) that could not be compared" in ln for ln in lines):
            problems.append(
                f"vendor-check: {label} must not hide an undetermined server: exit {code} ({lines})")
    return problems


def widening_selftest() -> list[str]:
    """--widening-ok downgrades exactly the widening findings. It decides
    whether the bump workflow opens a PR or fails, and it works by matching
    phrases, so a reworded message must fail here rather than silently move
    a finding across that line."""
    problems: list[str] = []
    inv = FIXTURES_ROOT / "invalid"
    for name in ("widening-more-enabled-than-baseline", "swap-read-for-write-constant-count",
                 "prompts-enabled-widening", "prompt-swap-constant-count"):
        tf = case_tf_text(inv / name)
        errors = run(inv / name, tf) if tf is not None else []
        if not errors or not all(is_widening(e) for e in errors):
            problems.append(f"widening-ok: {name!r} should be all widening, got {errors}")
    for name in ("tool-no-reason", "catalogue-tool-without-decision", "mapping-on-behalf-not-boolean",
                 "baseline-enabled-tools-count-mismatch"):
        tf = case_tf_text(inv / name)
        errors = run(inv / name, tf) if tf is not None else []
        if not errors or all(is_widening(e) for e in errors):
            problems.append(f"widening-ok: {name!r} must keep a non-widening error, got {errors}")
    return problems


def main() -> int:
    if "--vendor-check" in sys.argv[1:]:
        try:
            code, lines = vendor_check(ALLOWLISTS_DIR)
        except Exception as e:  # noqa: BLE001 - exit 1 is reserved for tampered
            code, lines = 2, [f"the vendor check failed before it could compare: {e!r}"]
        for line in lines:
            print(line, file=sys.stderr if code else sys.stdout)
        return code

    if "--selftest" in sys.argv[1:]:
        problems, valid_n, invalid_n = run_selftest()
        problems += vendor_check_selftest()
        problems += widening_selftest()
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"portal allowlists selftest: {len(problems)} problem(s)", file=sys.stderr)
            return 1
        print(f"selftest OK: {valid_n} valid fixture(s), {invalid_n} invalid fixture(s)")
        return 0

    if not ALLOWLISTS_DIR.is_dir():
        print(f"{ALLOWLISTS_DIR} not found -- refusing to pass vacuously", file=sys.stderr)
        return 2

    if not MCP_SERVERS_TF.is_file():
        print(f"{MCP_SERVERS_TF} not found -- the existence check has nothing to read", file=sys.stderr)
        return 2
    errors = run(ALLOWLISTS_DIR, MCP_SERVERS_TF.read_text(encoding="utf-8"))
    if "--widening-ok" in sys.argv[1:]:
        for w in (e for e in errors if is_widening(e)):
            print(f"WIDENING (baseline.json must be edited in this PR): {w}")
        errors = [e for e in errors if not is_widening(e)]
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"portal allowlists: {len(errors)} error(s)", file=sys.stderr)
        return 1

    vendored = [p for p in ALLOWLISTS_DIR.glob("*.json") if p.name not in SPECIAL_FILES]
    print(f"OK: {len(vendored)} vendored MCP portal allowlist(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
