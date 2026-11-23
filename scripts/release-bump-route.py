#!/usr/bin/env python3
"""Decide how a release bump for one image reaches main: `pr` or `direct`.

    release-bump-route.py --image ghcr.io/mctlhq/mctl-api [--root DIR]

Prints exactly one word on stdout. Exit codes: 0 decided, 2 could not decide.

"Could not observe" is never "observed absent": a missing, unreadable or
malformed routes file, a duplicate key, a non-list or a non-string entry is
exit 2 with nothing on stdout. It never defaults to `direct` and never to `pr`,
so a broken file cannot silently move a release between the two paths.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

ROUTES = "platform-gitops/release-bump-routes.yaml"
IMAGE = re.compile(r"^[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)+$")


class _DupKeyLoader(yaml.SafeLoader):
    """safe_load keeps the last of two equal keys silently; that must be an error."""


def _no_dups(loader, node, deep=False):
    seen = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=True)
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_DupKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dups)


def pr_route_images(root: Path) -> list:
    data = yaml.load((root / ROUTES).read_text(), Loader=_DupKeyLoader)
    if not isinstance(data, dict) or set(data) != {"pr_route_images"}:
        raise ValueError("expected a mapping with exactly the key pr_route_images")
    images = data["pr_route_images"]
    if not isinstance(images, list):
        raise ValueError("pr_route_images is not a list")
    for i in images:
        if not isinstance(i, str) or not IMAGE.fullmatch(i):
            raise ValueError(f"bad image entry {i!r}")
    if len(set(images)) != len(images):
        raise ValueError("duplicate image entry")
    return images


def route(image: str, root: Path) -> str:
    if not IMAGE.fullmatch(image):
        raise ValueError(f"bad --image {image!r}")
    return "pr" if image in pr_route_images(root) else "direct"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args()
    try:
        out = route(a.image, Path(a.root))
    except Exception as exc:  # noqa: BLE001 - every failure is "could not decide"
        print(f"release-bump-route: cannot decide: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
