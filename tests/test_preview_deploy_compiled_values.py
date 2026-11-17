"""preview-deploy deploys values compiled from a DeployIntent for a service
that is not in gitops yet (mctlhq/mctl-gitops#2654).

Runs the deploy template's own script with stub git/python3/helm/kubectl and
real base64/gzip/sha256sum. Every case runs against the real script (must be
green) and against mutants that remove one guard each (must be red).

Run: python3 tests/test_preview_deploy_compiled_values.py
"""
import base64
import gzip
import hashlib
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

import yaml

DEPLOY = pathlib.Path("platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml")
REWRITE = pathlib.Path("platform-gitops/argo-workflows/scripts/rewrite_preview_values.py")
SHELL = os.environ.get("PREVIEW_TEST_SHELL", "bash")
REF = "0123456789abcdef0123456789abcdef01234567"
VALUES = b"image:\n  repository: ghcr.io/mctlhq/probe\nservice:\n  port: 8080\n"


def stub(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def enc(raw):
    return base64.b64encode(gzip.compress(raw)).decode()


def deploy_source():
    doc = yaml.safe_load(DEPLOY.read_text())
    return next(t for t in doc["spec"]["templates"] if t["name"] == "deploy")["script"]["source"]


def run(source, **extra):
    """Run the script once; returns (rc, stderr, calls, root-relative files)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        bindir = root / "bin"
        bindir.mkdir()
        calls = root / "calls"
        calls.touch()
        stub(bindir / "git", '#!/bin/sh\necho "git $*" >> "$CALLS"\n'
             'case "$*" in\n'
             '  clone*) mkdir -p "$TMPROOT/mctl-gitops/platform-gitops/services/labs/probe"\n'
             '    [ -n "$STUB_EXISTING" ] && : > "$TMPROOT/mctl-gitops/platform-gitops/services/labs/probe/values.yaml" ;;\n'
             '  *"rev-parse HEAD") echo "$STUB_HEAD" ;;\nesac\nexit 0\n')
        stub(bindir / "python3", '#!/bin/sh\necho "python3 $*" >> "$CALLS"\nexit "${STUB_PY_RC:-42}"\n')
        stub(bindir / "helm", '#!/bin/sh\necho "helm $*" >> "$CALLS"\n'
             'case "$1" in upgrade) exit 1 ;; esac\nexit 0\n')
        stub(bindir / "kubectl", '#!/bin/sh\necho "kubectl $*" >> "$CALLS"\nexit 0\n')
        env = {
            "PATH": f"{bindir}:{os.environ['PATH']}", "CALLS": str(calls), "TMPROOT": str(root),
            "PARAM_TEAM_NAME": "labs", "PARAM_COMPONENT_NAME": "probe", "PARAM_IMAGE_TAG": "1.0.0",
            "PARAM_TTL_HOURS": "24", "PARAM_PORT": "", "PARAM_PREVIEW_ID": "ab12cd",
            "PARAM_GITOPS_REF": REF, "PARAM_COMPILED_VALUES": "", "PARAM_VALUES_SHA256": "",
            "PARAM_IMAGE_DIGEST": "", "ARGO_WORKFLOW_NAME": "preview-deploy-x7k2q",
            "PLATFORM_DOMAIN": "mctl.ai", "GITOPS_ORG": "mctlhq", "GITOPS_REPO": "mctl-gitops",
            "STUB_HEAD": REF, "STUB_EXISTING": "",
        }
        env.update(extra)
        src = source.replace("/tmp/", f"{root}/")
        p = subprocess.run([SHELL, "-c", src], env=env, capture_output=True, text=True)
        decoded = root / "compiled-values.yaml"
        return p.returncode, p.stderr, calls.read_text().splitlines(), (decoded.read_bytes() if decoded.exists() else None)


def good(**over):
    kw = {"PARAM_COMPILED_VALUES": enc(VALUES), "PARAM_VALUES_SHA256": hashlib.sha256(VALUES).hexdigest()}
    kw.update(over)
    return kw


def rewrite(values, repo):
    with tempfile.TemporaryDirectory() as tmp:
        i, o = pathlib.Path(tmp, "in.yaml"), pathlib.Path(tmp, "out.yaml")
        i.write_bytes(values)
        return subprocess.run([sys.executable, str(REWRITE), "--team", "labs", "--service", "probe",
                               "--in", str(i), "--out", str(o), "--require-image-repository", repo],
                              capture_output=True, text=True).returncode


def cases(source, rewrite_src_ok=True):
    bad = []

    def want(name, ok):
        if not ok:
            bad.append(name)

    rc, err, calls, dec = run(source, **good())
    py = [c for c in calls if c.startswith("python3")]
    want("valid compiled values reach the rewrite step", rc == 42 and len(py) == 1)
    want("rewrite reads the decoded values", dec == VALUES and any("--in" in c and "compiled-values.yaml" in c for c in py))
    want("rewrite is told the only image repository", any("--require-image-repository ghcr.io/mctlhq/probe" in c for c in py))

    for name, extra in {
        "compiled without hash": good(PARAM_VALUES_SHA256=""),
        "hash without compiled": good(PARAM_COMPILED_VALUES=""),
        "compiled without gitops_ref": good(PARAM_GITOPS_REF=""),
        "short hash": good(PARAM_VALUES_SHA256="ab" * 31),
        "uppercase hash": good(PARAM_VALUES_SHA256=hashlib.sha256(VALUES).hexdigest().upper()),
        "non-base64 values": good(PARAM_COMPILED_VALUES="a b;c"),
        "oversized values": good(PARAM_COMPILED_VALUES="A" * 96004),
    }.items():
        rc, err, calls, _ = run(source, **extra)
        want(f"refused before clone: {name}", rc == 1 and not [c for c in calls if c.startswith("git")])

    rc, err, calls, _ = run(source, **good(PARAM_VALUES_SHA256="0" * 64))
    want("hash mismatch refused", rc == 1 and "does not match" in err and not [c for c in calls if c.startswith("python3")])

    rc, err, calls, _ = run(source, **good(PARAM_COMPILED_VALUES=enc(VALUES + b"x: 1\n")))
    want("tampered values refused", rc == 1 and not [c for c in calls if c.startswith("python3")])

    rc, err, calls, _ = run(source, **good(STUB_EXISTING="1"))
    want("service already in gitops refused", rc == 1 and "already has a values.yaml" in err
         and not [c for c in calls if c.startswith("python3")])

    rc, err, calls, _ = run(source, PARAM_GITOPS_REF=REF)
    want("values.yaml path unchanged without compiled values",
         rc == 42 and not any("--require-image-repository" in c for c in calls))

    # A preview that does not come up is removed, only when compiled.
    rc, err, calls, _ = run(source, STUB_PY_RC="0", **good())
    want("failed compiled preview is uninstalled",
         any(c.startswith("helm uninstall preview-probe-ab12cd") for c in calls)
         and any(c.startswith("kubectl delete secret preview-probe-ab12cd-tls") for c in calls))
    rc, err, calls, _ = run(source, STUB_PY_RC="0")
    want("failed values.yaml preview keeps the old behaviour",
         rc != 0 and not any(c.startswith("helm uninstall") for c in calls))

    if rewrite_src_ok:
        want("rewrite accepts the built repository", rewrite(VALUES, "ghcr.io/mctlhq/probe") == 0)
        want("rewrite refuses another repository", rewrite(b"image:\n  repository: evil/x\n", "ghcr.io/mctlhq/probe") != 0)
        want("rewrite refuses a missing repository", rewrite(b"service:\n  port: 1\n", "ghcr.io/mctlhq/probe") != 0)
    return bad


def main():
    src = deploy_source()
    failed = False
    bad = cases(src)
    for b in bad:
        print("FAIL", b)
        failed = True
    if not bad:
        print("PASS all cases")

    def cut(a, b=""):
        assert src.count(a) == 1, a
        return src.replace(a, b)

    mutants = {
        "no hash check": cut('if [ "$GOT_SHA" != "$VALUES_SHA" ]; then', 'if false; then'),
        "no existing-service guard": cut('if [ -e "$SERVICE_VALUES" ]; then', 'if false; then'),
        "no failure cleanup": cut("trap cleanup_failed_preview EXIT"),
        "no image repository pin": cut('REWRITE_ARGS="--require-image-repository ghcr.io/${GITOPS_ORG}/${COMPONENT}"'),
        "no gitops_ref requirement": cut('if [ -z "$PARAM_GITOPS_REF" ]; then', 'if false; then'),
        "no size cap": cut('if [ "${#COMPILED}" -gt 96000 ]; then', 'if false; then'),
    }
    for name, m in mutants.items():
        if cases(m, rewrite_src_ok=False):
            print("PASS mutant killed:", name)
        else:
            print("FAIL mutant survived:", name)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
