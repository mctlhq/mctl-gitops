#!/usr/bin/env python3
"""Validate platform-gitops/images/mirrors.yaml (third-party GHCR mirrors).

Usage:
  validate-image-mirrors.py              validate the committed file
  validate-image-mirrors.py --selftest   prove the checks fire both ways
  validate-image-mirrors.py --get NAME   validate, then print NAME's entry
                                         as KEY=VALUE lines (for
                                         .github/workflows/mirror-image.yaml)

Every mirror name must also be `reserved` in
platform-gitops/argo-workflows/config/image-names.txt and must not appear in a
`grant` or `shared` line. Otherwise a tenant build with that component name
could push its own tags into the mirror package.

A missing, unreadable or malformed file is an error, never "no mirrors" or
"nothing reserved".
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MIRRORS = ROOT / "platform-gitops/images/mirrors.yaml"
IMAGE_NAMES = ROOT / "platform-gitops/argo-workflows/config/image-names.txt"

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
# registry/repo[/repo...]@sha256:<64 hex>; no tag part, so the ref cannot move.
SOURCE_RE = re.compile(r"^[a-z0-9.-]+(?::[0-9]+)?(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}$")
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PLATFORMS = {"linux/amd64"}
KEYS = {"name", "source", "platform", "tag"}


def check(doc):
    """Return a list of error strings; empty means valid."""
    errors = []
    if not isinstance(doc, dict) or not isinstance(doc.get("mirrors"), list):
        return ["top level must be a mapping with a `mirrors` list"]
    if not doc["mirrors"]:
        return ["`mirrors` is empty; delete the file instead of emptying it"]
    names = set()
    for i, m in enumerate(doc["mirrors"]):
        where = f"mirrors[{i}]"
        if not isinstance(m, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        if set(m) != KEYS:
            errors.append(f"{where}: keys must be exactly {sorted(KEYS)}, got {sorted(m)}")
            continue
        name, source, platform, tag = (m[k] for k in ("name", "source", "platform", "tag"))
        if not all(isinstance(v, str) for v in (name, source, platform, tag)):
            errors.append(f"{where}: every value must be a string (quote the tag if YAML reads it as a number)")
            continue
        where = f"mirrors[{i}] ({name})"
        if not NAME_RE.match(name):
            errors.append(f"{where}: name must match {NAME_RE.pattern}")
        if name in names:
            errors.append(f"{where}: duplicate name")
        names.add(name)
        if not SOURCE_RE.match(source):
            errors.append(f"{where}: source must be registry/repo@sha256:<64 hex> with no tag")
        if source.startswith("ghcr.io/mctlhq/"):
            errors.append(f"{where}: source is already in ghcr.io/mctlhq")
        if platform not in PLATFORMS:
            errors.append(f"{where}: platform must be one of {sorted(PLATFORMS)}")
        if not TAG_RE.match(tag) or tag == "latest":
            errors.append(f"{where}: tag must match {TAG_RE.pattern} and not be `latest`")
    return errors


def check_reservations(doc, names_text):
    """Mirror names must be reserved and never granted or shared.

    Call only with a doc that check() accepted. Returns a list of errors.
    """
    reserved, opened = set(), {}
    for line in names_text.splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "reserved" and len(parts) == 2:
            reserved.add(parts[1])
        elif parts[0] == "grant" and len(parts) == 3:
            opened.setdefault(parts[2], []).append(" ".join(parts))
        elif parts[0] == "shared" and len(parts) == 2:
            opened.setdefault(parts[1], []).append(" ".join(parts))
    if not reserved:
        return ["image-names.txt has no `reserved` lines; refusing to read that as nothing reserved"]
    errors = []
    for m in doc["mirrors"]:
        name = m["name"]
        if name not in reserved:
            errors.append(f"mirror {name}: add `reserved {name}` to image-names.txt")
        for line in opened.get(name, []):
            errors.append(f"mirror {name}: `{line}` in image-names.txt lets a team push to it")
    return errors


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def selftest():
    good = {"mirrors": [{
        "name": "chainguard-nginx",
        "source": "docker.io/chainguard/nginx@sha256:" + "a" * 64,
        "platform": "linux/amd64",
        "tag": "1.31.8-20261115",
    }]}
    assert check(good) == [], check(good)

    def mutated(**kw):
        m = dict(good["mirrors"][0], **kw)
        return {"mirrors": [m]}

    bad = {
        "tag-only source": mutated(source="docker.io/chainguard/nginx:latest"),
        "tag+digest source": mutated(source="docker.io/chainguard/nginx:latest@sha256:" + "a" * 64),
        "short digest": mutated(source="docker.io/chainguard/nginx@sha256:abc"),
        "ghcr source": mutated(source="ghcr.io/mctlhq/x@sha256:" + "a" * 64),
        "latest tag": mutated(tag="latest"),
        "numeric tag": mutated(tag=1.31),
        "arm64": mutated(platform="linux/arm64"),
        "bad name": mutated(name="Chainguard_Nginx"),
        "extra key": mutated(extra="x"),
        "duplicate": {"mirrors": good["mirrors"] * 2},
        "empty list": {"mirrors": []},
        "no list": {},
        "not a mapping": None,
    }
    for label, doc in bad.items():
        assert check(doc), f"selftest: {label} was accepted"

    names_ok = "registry ghcr.io/mctlhq\nreserved-prefix mctl-\nreserved chainguard-nginx\n"
    assert check_reservations(good, names_ok) == [], check_reservations(good, names_ok)
    bad_names = {
        "not reserved": "registry ghcr.io/mctlhq\nreserved other\n",
        "commented out": "registry ghcr.io/mctlhq\nreserved other\n# reserved chainguard-nginx\n",
        "granted": names_ok + "grant labs chainguard-nginx\n",
        "shared": names_ok + "shared chainguard-nginx\n",
        "empty list": "",
    }
    for label, text in bad_names.items():
        assert check_reservations(good, text), f"selftest: reservation {label} was accepted"
    print(f"selftest OK: 1 valid fixture accepted, {len(bad)} mutations rejected; "
          f"reservations: 1 accepted, {len(bad_names)} rejected")


def main(argv):
    if argv[1:] == ["--selftest"]:
        selftest()
        return 0
    get = None
    if len(argv) == 3 and argv[1] == "--get":
        get = argv[2]
    elif len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        doc = load(MIRRORS)
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: cannot read {MIRRORS}: {e}", file=sys.stderr)
        return 1
    errors = check(doc)
    if not errors:
        try:
            names_text = IMAGE_NAMES.read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: cannot read {IMAGE_NAMES}: {e}", file=sys.stderr)
            return 1
        errors = check_reservations(doc, names_text)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if get is None:
        print(f"{MIRRORS.name}: {len(doc['mirrors'])} mirror(s) valid")
        return 0
    matches = [m for m in doc["mirrors"] if m["name"] == get]
    if len(matches) != 1:
        print(f"ERROR: no mirror named {get!r}", file=sys.stderr)
        return 1
    m = matches[0]
    repo, digest = m["source"].split("@", 1)
    print(f"source={m['source']}")
    print(f"source_repo={repo}")
    print(f"digest={digest}")
    print(f"platform={m['platform']}")
    print(f"dest=ghcr.io/mctlhq/{m['name']}:{m['tag']}")
    print(f"package={m['name']}")
    print(f"tag={m['tag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
