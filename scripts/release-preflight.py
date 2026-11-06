#!/usr/bin/env python3
"""What release-deploy.yaml may publish (mctlhq/mctl-agents#1007).

Run from the root of a checkout of main, so the policy never comes from what a
dispatch chose:

  release-preflight.py preflight     before the build starts, with no credentials
  release-preflight.py publish       the same checks plus tag replacement, right
                                     before the push, where docker is logged in
  release-preflight.py publish-direct   the same point, for a direct dispatch

Inputs arrive as env: REPO, IMAGE_NAME, IMAGE_TAG, GIT_REF, TEAM, SERVICE,
VALUES_PATH, VALUES_GLOB. Anything this script cannot read or decide refuses.

Exit: 0 allowed; 2 usage or unreadable policy; 4 path; 5 input shape;
6 release gate; 8 repository not bound to image; 9 ref does not fit the tag;
10 the tag exists and must not be replaced; 11 cannot tell whether it exists.
"""
import glob as globmod
import os
import pathlib
import re
import subprocess
import sys

import yaml

BINDINGS = pathlib.Path("platform-gitops/release-bindings.yaml")
GATES = pathlib.Path("platform-gitops/release-gates.yaml")
# Same list as release-deploy.yaml; tests/test_release_preflight.py asserts it.
ALLOWED_PREFIXES = (
    "platform-gitops/services/",
    "platform-gitops/argo-workflows/cluster-templates/",
    "platform-gitops/bootstrap/templates/mctl-platform/",
)
TAG_RE = r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"
IMAGE_RE = r"ghcr\.io/mctlhq/[a-z0-9][a-z0-9._-]*"
REPO_RE = r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+"
# `main-<sha>` or a bare short sha: the tag names the commit it was built from.
SHA_TAG_RE = r"(?:main-)?([0-9a-f]{7,40})"
# A release builds a tag that looks like a version, so a branch name such as
# `main` cannot stand in for one.
RELEASE_TAG_RE = r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][A-Za-z0-9._-]+)?"
ABSENT_RE = re.compile(r"no such manifest|manifest unknown", re.I)


def refuse(code, msg):
    print(f"::error::release preflight: {msg}", file=sys.stderr)
    sys.exit(code)


def env(name):
    return os.environ.get(name, "")


def check_shapes():
    for name, pattern in (("IMAGE_TAG", TAG_RE), ("IMAGE_NAME", IMAGE_RE), ("REPO", REPO_RE)):
        if not re.fullmatch(pattern, env(name)):
            refuse(5, f"{name} has an invalid shape: {env(name)!r}")
    if not re.fullmatch(r"[A-Za-z0-9._/+-]{1,255}", env("GIT_REF")) or env("GIT_REF").startswith("-"):
        refuse(5, f"GIT_REF has an invalid shape: {env('GIT_REF')!r}")


def check_binding():
    try:
        doc = yaml.safe_load(BINDINGS.read_text())
        table = doc["bindings"]
        if not isinstance(table, dict) or not table:
            raise ValueError("no bindings")
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as e:
        refuse(2, f"cannot read {BINDINGS}: {e}")
    bound = table.get(env("IMAGE_NAME"))
    if not isinstance(bound, str) or not bound:
        refuse(8, f"{env('IMAGE_NAME')} is not in {BINDINGS}; add it in a reviewed PR")
    if bound.lower() != env("REPO").lower():
        refuse(8, f"{env('IMAGE_NAME')} is bound to {bound}, got {env('REPO')}")


def tag_names_commit():
    m = re.fullmatch(SHA_TAG_RE, env("IMAGE_TAG"))
    return bool(m) and re.fullmatch(r"[0-9a-f]{40}", env("GIT_REF")) is not None \
        and env("GIT_REF").startswith(m.group(1))


def check_ref():
    """A release builds the tag it names, or a commit whose sha is in the tag."""
    release = env("GIT_REF") == env("IMAGE_TAG") and re.fullmatch(RELEASE_TAG_RE, env("IMAGE_TAG"))
    if not release and not tag_names_commit():
        refuse(9, f"git_ref {env('GIT_REF')!r} does not fit image_tag {env('IMAGE_TAG')!r}: "
                  "use the same version tag, or a tag carrying the commit's full sha")


def allowed(path):
    if os.path.isabs(path) or ".." in path.split("/") or not os.path.normpath(path).startswith(ALLOWED_PREFIXES):
        refuse(4, f"path is not allowed: {path}")


def resolve_files():
    """The same file set the bump step resolves, so the gate judges the real bump."""
    files = []
    if env("VALUES_GLOB").strip():
        pattern = env("VALUES_GLOB").strip()
        allowed(pattern)
        matched = sorted(globmod.glob(pattern))
        if not matched:
            refuse(4, f"no files matched glob: {pattern}")
        files += matched
    named = [p.strip() for p in env("VALUES_PATH").replace("\n", ",").split(",") if p.strip()]
    files += named
    if not named and not env("VALUES_GLOB").strip():
        files.append(f"platform-gitops/services/{env('TEAM')}/{env('SERVICE')}/values.yaml")
    for f in files:
        allowed(f)
        if os.path.relpath(os.path.realpath(f)) != os.path.normpath(f):
            refuse(4, f"path goes through a symlink: {f}")
        if not os.path.isfile(f):
            refuse(4, f"file not found: {f}")
    return [os.path.normpath(f) for f in files]


def check_gate():
    gate = subprocess.run([sys.executable, "scripts/release-gate.py", "check",
                           "--files", *resolve_files(), "--new-tag", env("IMAGE_TAG")])
    if gate.returncode != 0:
        refuse(6, "the release gate refused this release")


def check_tag_free():
    if tag_names_commit():
        print("tag carries the commit's sha: a rebuild is the same source")
        return
    ref = f"{env('IMAGE_NAME')}:{env('IMAGE_TAG')}"
    try:
        r = subprocess.run(["docker", "manifest", "inspect", ref], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        refuse(11, f"cannot tell whether {ref} exists: {e}")
    if r.returncode == 0:
        refuse(10, f"{ref} already exists and a release tag is not replaced; release a new version")
    if not ABSENT_RE.search(r.stderr):
        refuse(11, f"cannot tell whether {ref} exists: {r.stderr.strip()[:200]}")
    print(f"{ref} does not exist yet")


def check_direct():
    """A direct dispatch skips the release checks. It may not publish a gated image,
    or replace a tag of any image that release-deploy publishes. A new tag, or an
    image outside the table, is the tenant build path and stays as it was.

    The shapes come first: the build action splits its tags on commas and newlines,
    so a tag carrying one names further images, past every other check here."""
    for name, pattern in (("IMAGE_TAG", TAG_RE), ("IMAGE_NAME", IMAGE_RE)):
        if not re.fullmatch(pattern, env(name)):
            refuse(5, f"{name} has an invalid shape: {env(name)!r}")
    try:
        doc = yaml.safe_load(GATES.read_text())
        repos = {g["repository"] for g in doc["gates"] if g.get("repository")}
        bound = yaml.safe_load(BINDINGS.read_text())["bindings"]
        if not isinstance(bound, dict) or not bound:
            raise ValueError("no bindings")
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError, ValueError) as e:
        refuse(2, f"cannot read the release policy: {e}")
    if env("IMAGE_NAME") in repos:
        refuse(8, f"{env('IMAGE_NAME')} is release-gated: publish it through release-deploy.yaml")
    if env("IMAGE_NAME") in bound:
        check_tag_free()


def main():
    stage = sys.argv[1] if len(sys.argv) == 2 else ""
    if stage == "publish-direct":
        check_direct()
    elif stage in ("preflight", "publish"):
        check_shapes()
        check_binding()
        check_ref()
        check_gate()
        if stage == "publish":
            check_tag_free()
    else:
        refuse(2, f"unknown stage: {stage!r}")
    print(f"release preflight: {stage} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
