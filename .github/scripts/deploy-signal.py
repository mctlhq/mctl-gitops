#!/usr/bin/env python3
"""Assert that every release this platform cut has actually been deployed.

The failure this exists for (#1006) produced no job, no log and no failed
step: `release-deploy` was refused at startup, so nothing inside a run could
have noticed. Eleven hours of releases were cut, merged and believed shipped
while no image was built and no tag moved. The lesson is that the check has to
ask what the pipeline was supposed to *produce*, from outside any run of it.

So this compares two facts that exist independently of the deploy machinery:
the latest GitHub release of a source repository, and the image tag committed
in this repository. If a release is older than the grace period and the
deployed tag still does not match it, the deploy did not happen, whatever the
workflow history says.

Coverage is declared in .github/deploy-signal.yaml and is itself checked: a
service on disk with no entry is an error, and so is an entry for a file that
is gone. A check that silently covers less than it did yesterday is the same
class of defect as the one it is watching for.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / ".github" / "deploy-signal.yaml"
SERVICES_GLOB = "platform-gitops/services/*/*/values.yaml"

# A release needs time to become a deployment: image build, the gitops commit,
# then Argo CD picking it up (3 min poll + jitter + refs cache, ~8 min at the
# tail per argocd-freshness.sh). 45 minutes is comfortably past that and still
# well inside the window where someone can act on the alert.
DEFAULT_GRACE_MINUTES = 45

MAIN_TAG_RE = re.compile(r"^main-[0-9a-f]{7,40}$")
SHA_TAG_RE = re.compile(r"^[0-9a-f]{7,40}$")


class Drift(Exception):
    pass


def read_manifest(path=MANIFEST):
    doc = yaml.safe_load(path.read_text()) or {}
    services = doc.get("services")
    if not services:
        raise Drift(f"{path} declares no services; refusing to pass on an empty manifest")
    return services


def deployed_tag(values_path):
    doc = yaml.safe_load((REPO_ROOT / values_path).read_text()) or {}
    image = doc.get("image") or {}
    tag = image.get("tag")
    if tag is None:
        raise Drift(f"{values_path} has no image.tag")
    return str(tag)


def services_on_disk():
    return sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.glob(SERVICES_GLOB)
        if (yaml.safe_load(p.read_text()) or {}).get("image", {}).get("tag") is not None
    )


def latest_release(repo, token):
    """Latest published release of a repo, or None when it publishes none.

    None is a fact about the repository, not a reason to pass: the caller
    reports it as a manifest error, because an entry claiming a release_repo
    that has no releases can never fire and would sit here looking like cover.
    """
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "deploy-signal",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise Drift(f"{repo}: GitHub API returned {exc.code} for the latest release")
    except urllib.error.URLError as exc:
        # Fail, do not skip. An unreachable API means this run learned nothing
        # about whether the platform is deployed, and a check that reports
        # "fine" when it could not look is the same no-op as no check at all.
        raise Drift(f"{repo}: could not reach the GitHub API ({exc.reason})")
    published = datetime.fromisoformat(body["published_at"].replace("Z", "+00:00"))
    return body["tag_name"], published


def check(services, token, grace_minutes, now=None):
    now = now or datetime.now(timezone.utc)
    grace = timedelta(minutes=grace_minutes)
    problems, watched, unmapped = [], 0, 0

    declared = [s["path"] for s in services]
    if len(declared) != len(set(declared)):
        dupes = sorted({p for p in declared if declared.count(p) > 1})
        problems.append(f"manifest lists the same service twice: {', '.join(dupes)}")

    on_disk = set(services_on_disk())
    for missing in sorted(on_disk - set(declared)):
        problems.append(
            f"{missing} deploys an image but has no entry in .github/deploy-signal.yaml — "
            "add release_repo, tracks_main, pinned_to or unmapped"
        )
    for stale in sorted(set(declared) - on_disk):
        problems.append(f"manifest entry {stale} names a file that no longer deploys an image")

    for svc in services:
        path = svc["path"]
        if path not in on_disk:
            continue
        tag = deployed_tag(path)

        if "unmapped" in svc:
            unmapped += 1
            continue

        if svc.get("tracks_main"):
            pattern = SHA_TAG_RE if svc.get("sha_only") else MAIN_TAG_RE
            if not pattern.match(tag):
                problems.append(
                    f"{path}: declared as tracking main but deployed tag is {tag!r}"
                )
            watched += 1
            continue

        if "pinned_to" in svc:
            if tag != str(svc["pinned_to"]):
                problems.append(
                    f"{path}: pinned to {svc['pinned_to']} in the manifest but "
                    f"{tag} is deployed — decide which is right and update one of them"
                )
            watched += 1
            continue

        repo = svc["release_repo"]
        release = latest_release(repo, token)
        if release is None:
            problems.append(
                f"{path}: manifest points at {repo}, which publishes no releases, "
                "so this entry can never detect anything"
            )
            continue
        release_tag, published = release
        watched += 1
        if tag == release_tag:
            continue
        age = now - published
        if age < grace:
            continue
        problems.append(
            f"{path}: {repo} released {release_tag} {int(age.total_seconds() // 60)} min ago "
            f"but {tag} is deployed — the release was cut and never reached the cluster"
        )

    return problems, watched, unmapped


def self_test():
    """A checker that has never been seen to fail is not known to work.

    Each case breaks one thing and asserts this detector notices. The stale
    release case is the one that matters: it is the shape of #1006.
    """
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(hours=11)).isoformat().replace("+00:00", "Z")

    real_disk, real_tag, real_release = services_on_disk, deployed_tag, latest_release
    g = globals()
    try:
        g["services_on_disk"] = lambda: ["a/values.yaml", "b/values.yaml"]
        g["deployed_tag"] = lambda p: {"a/values.yaml": "0.58.0", "b/values.yaml": "0.1.0"}[p]
        g["latest_release"] = lambda repo, token: ("0.59.0", datetime.fromisoformat(old.replace("Z", "+00:00")))

        cases = [
            (
                "a release older than the grace period that never deployed",
                [{"path": "a/values.yaml", "release_repo": "o/r"}, {"path": "b/values.yaml", "unmapped": "x"}],
                "never reached the cluster",
            ),
            (
                "a service on disk with no manifest entry",
                [{"path": "a/values.yaml", "release_repo": "o/r"}],
                "no entry in",
            ),
            (
                "a manifest entry whose file is gone",
                [
                    {"path": "a/values.yaml", "release_repo": "o/r"},
                    {"path": "b/values.yaml", "unmapped": "x"},
                    {"path": "gone/values.yaml", "unmapped": "x"},
                ],
                "no longer deploys an image",
            ),
            (
                "a pin that no longer matches what is deployed",
                [{"path": "a/values.yaml", "pinned_to": "0.59.0"}, {"path": "b/values.yaml", "unmapped": "x"}],
                "pinned to",
            ),
            (
                "a main-tracking service deployed from a version tag",
                [{"path": "a/values.yaml", "tracks_main": True}, {"path": "b/values.yaml", "unmapped": "x"}],
                "declared as tracking main",
            ),
            (
                "the same service declared twice",
                [
                    {"path": "a/values.yaml", "unmapped": "x"},
                    {"path": "a/values.yaml", "unmapped": "x"},
                    {"path": "b/values.yaml", "unmapped": "x"},
                ],
                "same service twice",
            ),
        ]
        for name, services, expected in cases:
            problems, _, _ = check(services, None, DEFAULT_GRACE_MINUTES, now=now)
            if not any(expected in p for p in problems):
                print(f"SELF-TEST FAILED: {name}: expected {expected!r}, got {problems}")
                return 1
            print(f"  detects {name}")

        # And the converse: a healthy platform must not fire, or the alert is noise.
        g["deployed_tag"] = lambda p: {"a/values.yaml": "0.59.0", "b/values.yaml": "0.1.0"}[p]
        problems, watched, unmapped = check(
            [{"path": "a/values.yaml", "release_repo": "o/r"}, {"path": "b/values.yaml", "unmapped": "x"}],
            None, DEFAULT_GRACE_MINUTES, now=now,
        )
        if problems:
            print(f"SELF-TEST FAILED: a deployed release must be silent, got {problems}")
            return 1
        print("  stays silent when the deployed tag matches the release")

        # A release inside the grace period is a deploy in flight, not a fault.
        g["deployed_tag"] = lambda p: {"a/values.yaml": "0.58.0", "b/values.yaml": "0.1.0"}[p]
        g["latest_release"] = lambda repo, token: ("0.59.0", now - timedelta(minutes=5))
        problems, _, _ = check(
            [{"path": "a/values.yaml", "release_repo": "o/r"}, {"path": "b/values.yaml", "unmapped": "x"}],
            None, DEFAULT_GRACE_MINUTES, now=now,
        )
        if problems:
            print(f"SELF-TEST FAILED: a release inside the grace window must be silent, got {problems}")
            return 1
        print("  stays silent while a fresh release is still deploying")
    finally:
        g["services_on_disk"], g["deployed_tag"], g["latest_release"] = real_disk, real_tag, real_release

    print("self-test passed")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--grace-minutes", type=int, default=DEFAULT_GRACE_MINUTES)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    services = read_manifest()
    problems, watched, unmapped = check(services, token, args.grace_minutes)

    print(f"watched: {watched}   unmapped: {unmapped}   total: {len(services)}")
    if unmapped:
        print("not watched (no release to compare against):")
        for svc in services:
            if "unmapped" in svc:
                print(f"  {svc['path']}: {svc['unmapped']}")

    if problems:
        print()
        for p in problems:
            print(f"::error::{p}")
        return 1
    print("every watched service is running the release it should be")
    return 0


if __name__ == "__main__":
    sys.exit(main())
