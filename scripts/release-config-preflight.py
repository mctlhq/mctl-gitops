#!/usr/bin/env python3
"""Before an mctl-api image tag is bumped on main, run THAT image's own
`--check-config` against the configuration main renders today.

Why: the zitadel-iac guard in validate-manifests.yml checks the image PINNED on
main. A stricter rule shipped in a NEW image is only seen after the bump lands
and Argo rolls it, which is how 4.166.0 crash-looped (gitops#2737 / #2762).
This closes that direction: release-deploy.yaml and gitops-bump.yaml run it in
the `bump` job, before the tag edit is made or any commit is pushed.

Inputs (env): IMAGE_NAME, IMAGE_TAG. For any image other than
ghcr.io/mctlhq/mctl-api it is not applicable and exits 0, printing why.
For mctl-api it delegates to scripts/check-mctl-api-oidc-config.py with
--image-tag, so there is one implementation of the check, and it fails closed:
no helm, no docker, a failed pull, an image without the ok line, an unparsable
tag, a changed Secret wiring all exit 1. The only skip is the documented
transition (candidate tag older than MIN_CHECKER_VERSION, decided from the
version string alone, with a visible warning).

Usage: release-config-preflight.py [--min-version X.Y.Z]   (flag: local proofs only)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).resolve().parent / "check-mctl-api-oidc-config.py"
IMAGE = "ghcr.io/mctlhq/mctl-api"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-version")
    a = ap.parse_args()
    name, tag = os.environ.get("IMAGE_NAME", ""), os.environ.get("IMAGE_TAG", "")
    if not name or not tag:
        print("::error::release config preflight: IMAGE_NAME and IMAGE_TAG are required", file=sys.stderr)
        return 2
    if name != IMAGE:
        print(f"release config preflight: not applicable to {name}")
        return 0
    cmd = [sys.executable, str(CHECK), "--image-tag", tag]
    if a.min_version:
        cmd += ["--min-version", a.min_version]
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"::error::release config preflight: {IMAGE}:{tag} does not accept the configuration main renders today; "
              "the bump is refused (fix the config first, in its own PR)", file=sys.stderr)
        return 1
    print(f"release config preflight: {IMAGE}:{tag} ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
