"""gitops-bump refuses an image_digest the registry does not confirm (mctlhq/mctl-gitops#2652).

The "Check the image digest in the registry" step is run from the workflow's
own text against a stand-in `docker` on PATH. It must pass only when
name@digest resolves and name:tag points at exactly that digest; a registry it
cannot read is a refusal. The step runs in its own job, behind its login,
which the bump job needs, and only when a digest is given. Each named mutation must turn at
least one case red. Plain script: `python3 tests/test_gitops_bump_digest_registry.py`.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = yaml.safe_load((ROOT / ".github/workflows/gitops-bump.yaml").read_text())
JOBS = WF["jobs"]
STEPS = JOBS["check-digest"]["steps"]
NAMES = [s.get("name", "") for s in STEPS]
CHECK = next(s for s in STEPS if s.get("name") == "Check the image digest in the registry")
IMAGE = "ghcr.io/mctlhq/foo"
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64

# The stand-in answers from env: REG_DIGESTS lists name@digest refs that exist,
# REG_TAGS maps name:tag to its digest, printed as the manifest JSON that
# `--format '{{json .Manifest}}'` gives (checked against buildx 0.23 on GHCR).
# Anything else exits 1, like a miss or an
# unreachable registry.
FAKE_DOCKER = r'''#!/bin/sh
[ "$1 $2 $3" = "buildx imagetools inspect" ] || exit 9
ref=$4
case " $REG_DIGESTS " in *" $ref "*) exit 0;; esac
for pair in $REG_TAGS; do
  if [ "${pair%%=*}" = "$ref" ]; then
    [ "$5 $6" = "--format {{json .Manifest}}" ] || exit 8
    printf '{"mediaType":"application/vnd.oci.image.index.v1+json","digest":"%s","size":856}\n' "${pair#*=}"; exit 0
  fi
done
echo "not found: $ref" >&2; exit 1
'''


def run(script, digest, digests="", tags=""):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "docker").write_text(FAKE_DOCKER)
    (d / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{d}:{os.environ['PATH']}", "IMAGE_NAME": IMAGE, "NEW_TAG": "1.2.0",
           "IMAGE_DIGEST": digest, "REG_DIGESTS": digests, "REG_TAGS": tags}
    return subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True).returncode


def cases(script, steps_names, check_step, jobs=JOBS):
    bad = []

    def want(name, ok):
        if not ok:
            bad.append(name)

    tag_ok = f"{IMAGE}:1.2.0={D1}"
    want("accepts a digest that exists and the tag points at",
         run(script, D1, f"{IMAGE}@{D1}", tag_ok) == 0)
    want("refuses a digest missing from the registry", run(script, D1, "", tag_ok) != 0)
    want("refuses a tag that points at another digest",
         run(script, D1, f"{IMAGE}@{D1}", f"{IMAGE}:1.2.0={D2}") != 0)
    want("refuses a tag missing from the registry", run(script, D1, f"{IMAGE}@{D1}", "") != 0)
    want("refuses an empty tag digest", run(script, D1, f"{IMAGE}@{D1}", f"{IMAGE}:1.2.0=") != 0)
    want("refuses a malformed digest even if the registry knows it",
         run(script, "sha256:" + "A" * 64, f"{IMAGE}@sha256:{'A' * 64}", f"{IMAGE}:1.2.0=sha256:{'A' * 64}") != 0)

    want("runs only when a digest is given", check_step.get("if") == "inputs.image_digest != ''")
    try:
        want("login before the check",
             steps_names.index("Log in to GHCR (read)") < steps_names.index("Check the image digest in the registry"))
    except ValueError:
        want("login and check steps present", False)
    needs = jobs["bump"].get("needs")
    want("the bump job (the first write) waits for the check", "check-digest" in (needs if isinstance(needs, list) else [needs]))
    want("the bump job holds no registry credential", jobs["bump"].get("permissions") == {"contents": "read"})
    return bad


# The refusal on a failed tag lookup only names the cause: without it the empty
# tag digest still fails the equality check, so it has no mutant of its own.
MUTANTS = [
    ("digest existence unchecked", 'docker buildx imagetools inspect "${IMAGE_NAME}@${IMAGE_DIGEST}" >/dev/null', "true"),
    ("tag/digest mismatch accepted", '[[ "$tag_digest" == "$IMAGE_DIGEST" ]]', "true"),
    ("shape not re-asserted", '[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]', "true"),
]


def main():
    script = CHECK["run"]
    failures = cases(script, NAMES, CHECK)
    for f in failures:
        print("FAIL", f)
    print("PASS all cases" if not failures else f"{len(failures)} failure(s)")
    survivors = []
    for name, old, new in MUTANTS:
        if script.count(old) != 1:
            survivors.append(f"{name}: anchor not found once")
        elif not cases(script.replace(old, new), NAMES, CHECK):
            survivors.append(name)
    for name, mutate in [
        ("step runs without a digest", lambda st: {**st, "if": "always()"}),
    ]:
        if not cases(script, NAMES, mutate(CHECK)):
            survivors.append(name)
    order_mut = [n for n in NAMES if n != "Log in to GHCR (read)"] + ["Log in to GHCR (read)"]
    if not cases(script, order_mut, CHECK):
        survivors.append("login after the check")
    if not cases(script, NAMES, CHECK, {**JOBS, "bump": {**JOBS["bump"], "needs": "validate-inputs"}}):
        survivors.append("bump does not wait for the check")
    for s in survivors:
        print("MUTANT SURVIVED", s)
    n = len(MUTANTS) + 3
    print(f"{n - len(survivors)}/{n} mutants killed")
    sys.exit(1 if failures or survivors else 0)


if __name__ == "__main__":
    main()
