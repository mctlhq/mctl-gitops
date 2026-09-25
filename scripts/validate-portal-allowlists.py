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
    "prompts_total", "prompts_enabled", "recorded"}}}, the non-widening
    reference: a bump that raises a server's enabled/total tool count fails
    here until a human edits this file in the same diff.

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
    commented `UNMANAGED` list (mirroring `#1363`: `api` and `seerrsense`
    are mapped on the portal but have no Terraform resource of their own
    yet) or has a literal
    `resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "<id>"`
    in `mcp-servers.tf` -- the same literal-grep technique
    `portal-membership-add.sh`'s `tf_declared()` already uses, rather than a
    HCL parser.
  - non-widening: a vendored file's own tools_total/tools_enabled (every
    entry in the file, counted as committed) must not exceed what
    `baseline.json` records for that server.

What it does NOT do: compare a vendored file against the server's live,
synced tool *catalogue*. CI holds no Cloudflare credential for this root
(#1111), so it cannot know which of a file's entries the portal has even
synced. Measured 2026-09-25 (design.md amendment 5): the `tg` and `api`
files each list more tools than their live catalogue -- upstream-gated
entries (`account:manage`, `admin:broadcast` scopes the portal's own OAuth
grant does not request) that exist upstream but that the portal has never
seen. This is why `baseline.json`'s tools_total/tools_enabled here are the
vendored FILE's own counts, not the live/catalogue-restricted counts quoted
in the proposal's requirements.md acceptance criteria (alice 12/12, projects
8/8, tg 30/30, api 75/75, coolify 22/45, seerrsense 5/5) -- those two sets of
numbers agree for four of six servers (alice, projects, coolify, seerrsense,
whose files carry no such extra entries) and differ only for tg (37 file
entries, 36 enabled) and api (92 file entries, 77 enabled), exactly the
servers design.md's amendment names. This script has no way to compute the
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
    scripts/validate-portal-allowlists.py --selftest   replay
                                                        scripts/tests/fixtures/portal-allowlists/{valid,invalid}
                                                        and assert every
                                                        valid/ case passes and
                                                        every invalid/ case
                                                        fails
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORTAL_DIR = ROOT / "infrastructure" / "cloudflare" / "portal"
ALLOWLISTS_DIR = PORTAL_DIR / "allowlists"
MCP_SERVERS_TF = PORTAL_DIR / "mcp-servers.tf"
FIXTURES_ROOT = ROOT / "scripts" / "tests" / "fixtures" / "portal-allowlists"

# mapping.json / sources.json / baseline.json are manifests about the
# vendored files, not vendored files themselves -- excluded from the glob
# that discovers "one file per server".
SPECIAL_FILES = {"mapping.json", "sources.json", "baseline.json"}

ALLOWED_TOP_KEYS = {"$comment", "portal", "server", "default_disabled", "tools"}
REQUIRED_TOP_KEYS = {"portal", "server", "default_disabled", "tools"}
ALLOWED_TOOL_KEYS = {"name", "enabled", "reason", "upstream_gates", "override"}
PORTAL_ID = "mcp"
TF_RESOURCE_TYPE = "cloudflare_zero_trust_access_ai_controls_mcp_server"

# Mapped on the portal, no Terraform resource of their own yet -- the
# `#1363` seam. Recorded here, not discovered, so closing #1363 is a
# deletion from this one list rather than a rediscovery.
UNMANAGED = {"api", "seerrsense"}


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


def check_coverage(file_ids: set[str], mapping, errors: list[str]) -> dict:
    """{files} == {mapping.json servers where vendored}, and a non-vendored
    entry declares its mapping literally (design.md's escape hatch for a
    server with no vendored file).
    """
    servers = mapping.get("servers") if isinstance(mapping, dict) else None
    if not isinstance(servers, dict):
        errors.append("allowlists/mapping.json: missing or malformed top-level 'servers' object")
        return {}

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
    the same technique portal-membership-add.sh's tf_declared() uses, a
    literal grep rather than an HCL parser.
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


def check_baseline(files: dict, vendored_ids: set[str], baseline, errors: list[str]) -> None:
    """Non-widening: a vendored file's own tools_total/tools_enabled must not
    exceed what baseline.json records for that server. See the module
    docstring for why this compares the FILE's own counts, not a
    catalogue-restricted one.
    """
    entries = baseline.get("servers") if isinstance(baseline, dict) else None
    if not isinstance(entries, dict):
        errors.append("allowlists/baseline.json: missing or malformed top-level 'servers' object")
        entries = {}

    for sid in sorted(vendored_ids):
        data = files.get(sid)
        if not isinstance(data, dict):
            continue  # already reported by load/coverage
        tools = data.get("tools")
        if not isinstance(tools, list):
            continue  # already reported by check_shape

        total = len(tools)
        enabled = sum(1 for t in tools if isinstance(t, dict) and t.get("enabled") is True)

        b = entries.get(sid)
        if not isinstance(b, dict):
            errors.append(f"allowlists/baseline.json: no entry for vendored server {sid!r}")
            continue
        b_total, b_enabled = b.get("tools_total"), b.get("tools_enabled")
        if not isinstance(b_total, int) or not isinstance(b_enabled, int):
            errors.append(f"allowlists/baseline.json: {sid!r} tools_total/tools_enabled are not integers")
            continue

        if enabled > b_enabled or total > b_total:
            errors.append(
                f"allowlists/{sid}.json: widens exposure -- {enabled}/{total} tools enabled/total now, "
                f"baseline.json records {b_enabled}/{b_total} for {sid!r}; update baseline.json in the "
                "same change if this widening is intentional"
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
    check_baseline(files, vendored_ids, baseline, errors)

    return errors


def case_tf_text(case_dir: pathlib.Path) -> str:
    """A fixture may ship its own mcp-servers.tf to exercise the existence
    check without depending on (or polluting) the real one -- the same
    opt-in shape validate-agent-platform.py uses for its own cross-checks.
    """
    fixture_tf = case_dir / "mcp-servers.tf"
    if fixture_tf.is_file():
        return fixture_tf.read_text(encoding="utf-8")
    return MCP_SERVERS_TF.read_text(encoding="utf-8")


def run_selftest() -> list[str]:
    """A detector never seen to fire is not known to work: replay every
    fixture under valid/ and invalid/ and assert the expected outcome.
    """
    problems: list[str] = []

    valid_dir = FIXTURES_ROOT / "valid"
    for case_dir in sorted(valid_dir.glob("*")) if valid_dir.is_dir() else []:
        if not case_dir.is_dir():
            continue
        errors = run(case_dir, case_tf_text(case_dir))
        if errors:
            problems.append(f"valid fixture {case_dir.name!r} unexpectedly failed:")
            problems.extend(f"  {e}" for e in errors)

    invalid_dir = FIXTURES_ROOT / "invalid"
    for case_dir in sorted(invalid_dir.glob("*")) if invalid_dir.is_dir() else []:
        if not case_dir.is_dir():
            continue
        errors = run(case_dir, case_tf_text(case_dir))
        if not errors:
            problems.append(f"invalid fixture {case_dir.name!r} unexpectedly passed (expected at least one error)")

    return problems


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        problems = run_selftest()
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"portal allowlists selftest: {len(problems)} problem(s)", file=sys.stderr)
            return 1
        valid_n = len(list((FIXTURES_ROOT / "valid").glob("*"))) if (FIXTURES_ROOT / "valid").is_dir() else 0
        invalid_n = len(list((FIXTURES_ROOT / "invalid").glob("*"))) if (FIXTURES_ROOT / "invalid").is_dir() else 0
        print(f"selftest OK: {valid_n} valid fixture(s), {invalid_n} invalid fixture(s)")
        return 0

    if not ALLOWLISTS_DIR.is_dir():
        print(f"{ALLOWLISTS_DIR} not found -- refusing to pass vacuously", file=sys.stderr)
        return 2

    errors = run(ALLOWLISTS_DIR, MCP_SERVERS_TF.read_text(encoding="utf-8"))
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
