#!/usr/bin/env python3
"""Fail when a tenant's openclaw values.yaml has image.tag != env.OPENCLAW_VERSION.

`platform-gitops/platform-skills/catalog/mctl-platform/references/k8s.md`
documents that the two must "stay in sync on every bump" (the "Image bump
recipe" says to bump both together), but nothing enforced that until now.
gitops#1037: `admins` and `labs` had `image.tag` bumped to `2026.7.11-beta.2`
while `env.OPENCLAW_VERSION` was left at an older `2026.5.14-beta.1`, so the
version banner and anything gated on `OPENCLAW_VERSION` disagreed with the
binary actually running in the pod.

This deliberately does NOT look at `# release-drift: ignore` — that marker
(consumed by `.github/scripts/release-drift.sh`) opts a tenant out of
chasing the upstream GitHub release, a different axis (deployed vs.
released) from the one checked here (do the two fields in this one file
agree with each other).

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "platform-gitops/services"
GLOB = "*/openclaw/values.yaml"


def mismatches(directory: Path):
    """Yield (path, image_tag, openclaw_version) for every file where both
    keys are present and disagree."""
    for path in sorted(directory.glob(GLOB)):
        doc = yaml.safe_load(path.read_text())
        if not doc:
            continue
        image_tag = (doc.get("image") or {}).get("tag")
        openclaw_version = (doc.get("env") or {}).get("OPENCLAW_VERSION")
        if image_tag is None or openclaw_version is None:
            # Only one of the two keys present is out of scope for this check.
            continue
        if image_tag != openclaw_version:
            yield path, image_tag, openclaw_version


def _write_tenant(root: Path, team: str, image_tag: str, openclaw_version: str) -> None:
    values = root / "platform-gitops/services" / team / "openclaw"
    values.mkdir(parents=True)
    doc = {
        "image": {"repository": "ghcr.io/mctlhq/mctl-openclaw", "tag": image_tag},
        "env": {"APP_ENV": "production", "OPENCLAW_VERSION": openclaw_version},
    }
    (values / "values.yaml").write_text(yaml.dump(doc))


def selftest() -> int:
    """Prove the detector fires on a mismatch and stays quiet on a match."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write_tenant(root, "matched", "2026.7.11-beta.2", "2026.7.11-beta.2")
        _write_tenant(root, "drifted", "2026.7.11-beta.2", "2026.5.14-beta.1")
        found = list(mismatches(root / "platform-gitops/services"))

    if len(found) != 1:
        print(f"selftest FAIL: expected exactly one mismatch, got {found}", file=sys.stderr)
        return 1
    path, image_tag, openclaw_version = found[0]
    if path.parent.parent.name != "drifted":
        print(f"selftest FAIL: mismatch reported for the wrong tenant: {path}", file=sys.stderr)
        return 1
    if image_tag != "2026.7.11-beta.2" or openclaw_version != "2026.5.14-beta.1":
        print(f"selftest FAIL: wrong values reported: {image_tag} / {openclaw_version}", file=sys.stderr)
        return 1

    print("selftest OK: detector fires on a mismatched tenant, stays quiet on a matched one")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not SERVICES.is_dir():
        print(f"{SERVICES} not found -- refusing to pass vacuously", file=sys.stderr)
        return 2

    found = list(mismatches(SERVICES))
    if found:
        print(
            "::error::openclaw image.tag and env.OPENCLAW_VERSION disagree "
            "(both must stay in sync on every bump, per k8s.md):\n",
            file=sys.stderr,
        )
        for path, image_tag, openclaw_version in found:
            rel = path.relative_to(ROOT)
            print(
                f"::error::{rel}: image.tag={image_tag} OPENCLAW_VERSION={openclaw_version}",
                file=sys.stderr,
            )
        return 1

    print("OK: every tenant's openclaw image.tag matches its env.OPENCLAW_VERSION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
