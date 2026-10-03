#!/usr/bin/env python3
"""Fail when the usage pricing catalog is malformed or drifts from the ConfigMap.

mctlhq/mctl-gitops#1409 adds `platform-gitops/bootstrap/files/usage-pricing/
claude-firstparty.json` -- the rate card `mctl-api-usage-pricing.yaml` mounts
into mctl-api for the FinOps usage ledger (mctlhq/.github#50, ADR-012).
`internal/usage/pricing.go` (mctlhq/mctl-api) parses this file as a JSON array
of `Pricing` entries and its `NewCatalog` rejects one with no `version`, no
`canonical_model`, no `effective_from`, or two entries claiming the same
(`canonical_model`, `provider`, `effective_from`) triple -- but `main.go`
deliberately just LOGS that rejection and keeps serving every other endpoint
with a nil catalog. A malformed card would therefore degrade production
silently (no cost on any row) rather than fail anything. This check mirrors
`NewCatalog`'s own validation here, so it fails the PR instead.

It also renders the bootstrap chart and confirms the ConfigMap's `catalog.json`
key is byte-identical (as JSON) to the committed file: the template embeds it
with `.Files.Get | nindent`, and a leading/trailing whitespace regression there
would ship a file that fails to parse or silently differs from what a reviewer
approved.

Run with --selftest to prove the structural detector still detects (the
round-trip render check needs a real `helm` binary and the real chart, so
--selftest does not exercise it).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "platform-gitops/bootstrap/files/usage-pricing/claude-firstparty.json"
BOOTSTRAP = ROOT / "platform-gitops/bootstrap"
CONFIGMAP_NAME = "mctl-api-usage-pricing"
ISSUE = "mctlhq/mctl-gitops#1409"

REQUIRED_FIELDS = ("version", "canonical_model", "effective_from")
# internal/usage/pricing.go's Pricing JSON tags for the five rate fields.
RATE_FIELDS = (
    "input_per_mtok",
    "output_per_mtok",
    "cache_read_per_mtok",
    "cache_write_per_mtok",
    "web_search_per_call",
)


def violations(entries) -> list[str]:
    """Every way a rate-card list fails usage.NewCatalog's own invariants."""
    if not isinstance(entries, list) or not entries:
        return ["catalog must be a non-empty JSON array"]

    found: list[str] = []
    seen: dict[tuple[str, str, object], str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            found.append(f"entry {entry!r} is not an object")
            continue

        version = entry.get("version")
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                found.append(f"version {version!r}: missing required field {field!r}")

        for field in RATE_FIELDS:
            if field not in entry:
                continue
            value = entry[field]
            # bool is a subclass of int in Python; NewCatalog has no bool
            # rate, so True/False would silently pass an isinstance(int) test.
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                found.append(f"version {version!r}: {field} is {value!r}, must be a non-negative number")

        model = str(entry.get("canonical_model", "")).strip().lower()
        provider = str(entry.get("provider", "")).strip().lower()
        key = (model, provider, entry.get("effective_from"))
        if key in seen:
            found.append(
                f"versions {seen[key]!r} and {version!r} both claim (canonical_model={model!r}, "
                f"provider={provider!r}, effective_from={entry.get('effective_from')!r})"
            )
        else:
            seen[key] = version
    return found


def render_configmap_catalog(bootstrap_dir: Path) -> object:
    """helm template the bootstrap chart and return the parsed catalog.json value."""
    result = subprocess.run(
        ["helm", "template", "test", str(bootstrap_dir), "-f", str(bootstrap_dir / "values.yaml")],
        check=True,
        capture_output=True,
        text=True,
    )
    docs = list(yaml.safe_load_all(result.stdout))
    matches = [
        d
        for d in docs
        if d and d.get("kind") == "ConfigMap" and d.get("metadata", {}).get("name") == CONFIGMAP_NAME
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one {CONFIGMAP_NAME} ConfigMap, found {len(matches)}")
    return json.loads(matches[0]["data"]["catalog.json"])


def selftest() -> int:
    """Prove the structural detector fires on a broken catalog and stays quiet on a good one."""
    good = [
        {
            "version": "v1",
            "canonical_model": "claude-opus-5",
            "provider": "firstParty",
            "effective_from": "2026-09-01T00:00:00Z",
            "input_per_mtok": 5.0,
            "output_per_mtok": 25.0,
            "cache_read_per_mtok": 0.5,
            "cache_write_per_mtok": 6.25,
            "web_search_per_call": 0.01,
        },
    ]
    cases: list[tuple[str, object, bool]] = [
        ("good catalog", good, False),
        ("empty catalog", [], True),
        ("not a list", {"oops": True}, True),
        ("entry not an object", ["oops"], True),
        (
            "missing effective_from",
            [{k: v for k, v in good[0].items() if k != "effective_from"}],
            True,
        ),
        ("duplicate triple", good + [dict(good[0], version="v2")], True),
        ("negative rate", [dict(good[0], input_per_mtok=-1.0)], True),
        ("non-numeric rate", [dict(good[0], output_per_mtok="lots")], True),
        ("bool rate", [dict(good[0], cache_read_per_mtok=True)], True),
        (
            "different effective_from is not a duplicate",
            good + [dict(good[0], version="v2", effective_from="2026-10-01T00:00:00Z")],
            False,
        ),
        (
            "different provider is not a duplicate",
            good + [dict(good[0], version="v2", provider="bedrock")],
            False,
        ),
    ]
    for name, entries, should_fire in cases:
        found = violations(entries)
        if bool(found) != should_fire:
            print(f"selftest FAIL: case {name!r} expected fire={should_fire}, got {found}", file=sys.stderr)
            return 1
    print(
        "selftest OK: detector fires on an empty/malformed catalog, a missing required field, a "
        "duplicate (canonical_model, provider, effective_from) triple, and a negative, non-numeric "
        "or boolean rate; stays quiet on a well-formed catalog"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not CATALOG.is_file():
        print(f"::error::{CATALOG} does not exist", file=sys.stderr)
        return 1
    entries = json.loads(CATALOG.read_text())

    found = violations(entries)
    if found:
        rel = CATALOG.relative_to(ROOT)
        print(
            f"::error::{rel}: malformed usage pricing catalog ({ISSUE}) -- usage.NewCatalog "
            "(mctlhq/mctl-api) would reject this at pod startup, degrading every usage row to no "
            "cost rather than failing loudly:",
            file=sys.stderr,
        )
        for item in found:
            print(f"::error::{rel}: {item}", file=sys.stderr)
        return 1

    try:
        rendered = render_configmap_catalog(BOOTSTRAP)
    except Exception as exc:  # noqa: BLE001 - surfaced as a CI error, not a crash
        print(f"::error::failed to render/parse the {CONFIGMAP_NAME} ConfigMap: {exc}", file=sys.stderr)
        return 1

    if rendered != entries:
        print(
            f"::error::the rendered {CONFIGMAP_NAME} ConfigMap's catalog.json does not match "
            f"{CATALOG.relative_to(ROOT)} -- the template must embed the committed file byte-for-byte, "
            "never a second copy",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(entries)} pricing entries validated; rendered ConfigMap matches the committed catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
