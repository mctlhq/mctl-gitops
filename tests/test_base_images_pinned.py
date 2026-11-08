"""Base images in Argo templates and bootstrap manifests are pinned by digest (mctlhq/mctl-gitops#1033).

The listed repositories run next to credentials (clone steps, tenant tooling), so a
moved tag must not change what runs. Every literal `image:` line naming one of them
must carry an @sha256 digest. Templated values ({{ ... }}) are out of scope.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCOPES = ("platform-gitops/argo-workflows", "platform-gitops/bootstrap")
PINNED_REPOS = ("alpine", "alpine/git", "alpine/k8s", "busybox", "docker.io/library/busybox", "python")
IMAGE = re.compile(r"^\s*(?:-\s*)?image:\s*['\"]?([^\s'\"#]+)")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def unpinned(lines, name=""):
    bad = []
    for n, line in enumerate(lines, 1):
        m = IMAGE.match(line)
        if not m or "{{" in m.group(1):
            continue
        ref = m.group(1)
        repo = ref.split("@")[0].rsplit(":", 1)[0] if ":" in ref.split("@")[0].rsplit("/", 1)[-1] else ref.split("@")[0]
        if repo in PINNED_REPOS and not DIGEST.search(ref):
            bad.append(f"{name}:{n}: {ref}")
    return bad


def tracked():
    out = subprocess.check_output(["git", "ls-files", *SCOPES], cwd=ROOT, text=True)
    return [p for p in out.split("\n") if p.endswith((".yaml", ".yml"))]


failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:600]}")


# Detector self-test: red on tag-only and truncated digests, green on pinned and templated.
check("detector flags a tag-only image", len(unpinned(["  image: alpine:3.19"])) == 1)
check("detector flags a bare repo", len(unpinned(["  image: alpine/git"])) == 1)
check("detector flags a short digest", len(unpinned(["  image: alpine:3.19@sha256:abc"])) == 1)
check("detector accepts a digest", unpinned(["  image: alpine:3.19@sha256:" + "a" * 64 + " # alpine:3.19"]) == [])
check("detector ignores other repos and templated values",
      unpinned(["  image: ghcr.io/mctlhq/x:1.0.0", "  image: alpine:{{inputs.parameters.v}}"]) == [])

files = tracked()
check("manifest list was readable", len(files) > 0, files)
bad = []
for f in files:
    bad += unpinned((ROOT / f).read_text().split("\n"), f)
check("every listed base image is digest-pinned", not bad, bad[:10])

if failures:
    print("\n".join(failures))
    sys.exit(1)
