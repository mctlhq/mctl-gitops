"""preview-deploy deploys the image its build pushed, by digest (mctlhq/mctl-gitops#2652).

trigger-github-build is run from the ClusterWorkflowTemplate's own source
against a local stand-in for the GitHub API: it must read the digest from the
build run's image-digest artifact, refuse anything else, and never send the
token to the blob host the download redirects to. The deploy step's digest
check is run from its own source in sh. Each named mutation must turn at least
one case red. Plain script: `python3 tests/test_preview_deploy_digest.py`.
"""
import http.server
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import zipfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CWFT = ROOT / "platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml"
DOC = yaml.safe_load(CWFT.read_text())
TEMPLATES = {t["name"]: t for t in DOC["spec"]["templates"]}
TRIGGER = TEMPLATES["trigger-github-build"]["script"]["source"]
DEPLOY = TEMPLATES["deploy"]["script"]["source"]
IMAGE = "ghcr.io/mctlhq/foo"
DIGEST = "sha256:" + "ab" * 32
ART = "/repos/mctlhq/mctl-gitops/actions/artifacts/9/zip"
failures = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def zipped(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, t in files.items():
            z.writestr(n, t)
    return buf.getvalue()


class Fake(http.server.BaseHTTPRequestHandler):
    scenario = {}
    seen = []

    def log_message(self, *a):
        pass

    def reply(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        Fake.seen.append(("POST", self.path, self.headers.get("Authorization")))
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.reply(204)

    def do_GET(self):
        import json
        Fake.seen.append(("GET", self.path, self.headers.get("Authorization")))
        sc = Fake.scenario
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/repos/mctlhq/mctl-gitops/actions/workflows/build-image.yaml/runs"):
            return self.reply(200, json.dumps({"workflow_runs": [{"id": 7, "name": "build-wf-abc: t/foo (1.0)"}]}).encode())
        if self.path == "/repos/mctlhq/mctl-gitops/actions/runs/7":
            return self.reply(200, json.dumps({"status": "completed", "conclusion": "success"}).encode())
        if self.path.startswith("/repos/mctlhq/mctl-gitops/actions/runs/7/artifacts"):
            arts = sc.get("artifacts", [{"name": "image-digest", "expired": False, "archive_download_url": base + ART}])
            arts = [{**a, "archive_download_url": a["archive_download_url"].replace("BASE", base)} for a in arts]
            return self.reply(200, json.dumps({"artifacts": arts}).encode())
        if self.path.endswith("/actions/artifacts/9/zip"):
            return self.reply(302, headers={"Location": sc.get("redirect", base + "/blob")})
        if self.path == "/blob":
            return self.reply(200, zipped(sc.get("zip", {"image-ref.txt": f"{IMAGE}@{DIGEST}\n"})))
        self.reply(404)


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SERVER.server_port}"


def run_trigger(source, git_ref="feat/x", **scenario):
    Fake.scenario, Fake.seen = scenario, []
    d = pathlib.Path(tempfile.mkdtemp())
    out = d / "image_digest"
    src = (source.replace('API = "https://api.github.com"', f'API = "{BASE}"')
                 .replace("time.sleep(", "(lambda _s: None)(")
                 .replace("/tmp/image_digest", str(out))
                 .replace("{{workflow.name}}", "wf-abc")
                 # The stand-in serves plain http, so "https://" is narrowed to its own
                 # base URL: a redirect anywhere else stands for a non-https target.
                 .replace('location.startswith("https://")', f'location.startswith("{BASE}/")'))
    (d / "t.py").write_text(src)
    env = {**os.environ, "GITHUB_PAT": "test-token", "GITOPS_ORG": "mctlhq", "GITOPS_REPO": "mctl-gitops",
           "PARAM_DOCKERFILE_REPO": "mctlhq/foo", "PARAM_GIT_REF": git_ref, "PARAM_IMAGE_TAG": "1.0",
           "PARAM_DOCKERFILE_PATH": "Dockerfile", "PARAM_TEAM_NAME": "t", "PARAM_COMPONENT_NAME": "foo"}
    r = subprocess.run([sys.executable, "-I", str(d / "t.py")], env=env, capture_output=True, text=True, timeout=60)
    digest = out.read_text() if out.exists() else None
    blob_auth = [a for (m, p, a) in Fake.seen if p == "/blob" and a]
    return r.returncode, digest, len(Fake.seen), blob_auth


def deploy_check(source, digest):
    """Run the deploy script's digest check alone, from its own text."""
    start = source.index('DIGEST="$PARAM_IMAGE_DIGEST"')
    end = source.index('RELEASE="preview-', start)
    snippet = "set -eu\n" + source[start:end] + 'printf "%s" "$DIGEST"\n'
    return subprocess.run(["sh", "-c", snippet], env={**os.environ, "PARAM_IMAGE_DIGEST": digest},
                          capture_output=True, text=True).returncode


def cases(trigger, deploy, dag):
    bad = []

    def want(name, ok):
        if not ok:
            bad.append(name)

    code, digest, _, leak = run_trigger(trigger)
    want("reads the digest from the build's artifact", code == 0 and digest == DIGEST)
    want("never sends the token to the blob host", not leak)
    code, digest, calls, _ = run_trigger(trigger, git_ref="")
    want("no git_ref: empty digest, no API call", code == 0 and digest == "" and calls == 0)
    code, _, _, _ = run_trigger(trigger, artifacts=[])
    want("refuses a build without an image-digest artifact", code != 0)
    two = [{"name": "image-digest", "expired": False, "archive_download_url": "BASE" + ART}] * 2
    code, _, _, _ = run_trigger(trigger, artifacts=two)
    want("refuses two image-digest artifacts", code != 0)
    exp = [{"name": "image-digest", "expired": True, "archive_download_url": "BASE" + ART}]
    code, _, _, _ = run_trigger(trigger, artifacts=exp)
    want("refuses an expired artifact", code != 0)
    off = [{"name": "image-digest", "expired": False, "archive_download_url": "BASE/repos/evil/x/actions/artifacts/9/zip"}]
    code, _, _, _ = run_trigger(trigger, artifacts=off)
    want("refuses a download URL outside mctl-gitops", code != 0)
    code, _, _, _ = run_trigger(trigger, redirect=f"http://localhost:{SERVER.server_port}/blob")
    want("refuses a redirect to a non-https URL", code != 0)
    code, _, _, _ = run_trigger(trigger, zip={"image-ref.txt": f"ghcr.io/mctlhq/other@{DIGEST}\n"})
    want("refuses a digest of another image", code != 0)
    code, _, _, _ = run_trigger(trigger, zip={"image-ref.txt": f"{IMAGE}@sha256:{'AB' * 32}\n"})
    want("refuses a malformed digest", code != 0)
    code, _, _, _ = run_trigger(trigger, zip={"image-ref.txt": f"{IMAGE}@{DIGEST}\n", "x": "y"})
    want("refuses an artifact with extra files", code != 0)

    want("deploy accepts a digest", deploy_check(deploy, DIGEST) == 0)
    want("deploy accepts no digest", deploy_check(deploy, "") == 0)
    for label, d in [("short", DIGEST[:-1]), ("uppercase", "sha256:" + "AB" * 32), ("sha512", "sha512:" + "ab" * 32),
                     ("comma", DIGEST[:-1] + ","), ("bare hex", "ab" * 32)]:
        want(f"deploy refuses a {label} digest", deploy_check(deploy, d) != 0)
    want("helm always gets the digest, empty included",
         any(line.strip() == '--set-string image.digest="${DIGEST}" \\' for line in deploy.splitlines()))
    want("the build task always runs", "when" not in dag["build-image"])
    want("deploy gets the build's digest",
         {"name": "image_digest", "value": "{{tasks.build-image.outputs.parameters.digest}}"}
         in dag["deploy-preview"]["arguments"]["parameters"])
    return bad


def dag_of(doc):
    return {t["name"]: t for t in {x["name"]: x for x in doc["spec"]["templates"]}["preview-pipeline"]["dag"]["tasks"]}


MUTANTS_TRIGGER = [
    ("any artifact count", "if len(found) != 1:", "if not found:"),
    ("expired accepted", 'and not a.get("expired")', ""),
    ("URL not checked", 'if not url.startswith(f"{API}/repos/{GITOPS_ORG}/{GITOPS_REPO}/actions/artifacts/"):', "if False:"),
    ("redirect followed with the token", "opener = urllib.request.build_opener(_NoRedirect)",
     "opener = urllib.request.build_opener()"),
    ("image not checked", 're.escape(image_name) + r"@(sha256', 'r"[^@]+@(sha256'),
    ("digest charset loose", r'@(sha256:[0-9a-f]{64})"', r'@(sha256:[0-9a-fA-F]{64})"'),
    ("extra files accepted", 'if z.namelist() != ["image-ref.txt"]:', 'if "image-ref.txt" not in z.namelist():'),
    ("redirect scheme unchecked", 'if not location.startswith("https://"):', "if False:"),
    ("no early exit without git_ref", "if not git_ref:\n", "if False:\n"),
]
MUTANTS_DEPLOY = [
    ("deploy digest charset unchecked", 'case "${DIGEST#sha256:}" in', 'case "0" in'),
    ("deploy digest shape unchecked", "sha256:" + "?" * 64 + " )", "* )"),
    ("helm keeps the values digest", '--set-string image.digest="${DIGEST}"', '${DIGEST:+--set-string image.digest="${DIGEST}"}'),
]


def main():
    dag = dag_of(DOC)
    for name in cases(TRIGGER, DEPLOY, dag):
        check(name, False)
    if not failures:
        print("PASS all cases")
    survivors = []
    for name, old, new in MUTANTS_TRIGGER:
        if TRIGGER.count(old) != 1:
            survivors.append(f"{name}: anchor not found once")
        elif not cases(TRIGGER.replace(old, new), DEPLOY, dag):
            survivors.append(name)
    for name, old, new in MUTANTS_DEPLOY:
        if DEPLOY.count(old) != 1:
            survivors.append(f"{name}: anchor not found once")
        elif not cases(TRIGGER, DEPLOY.replace(old, new), dag):
            survivors.append(name)
    for s in survivors:
        print("MUTANT SURVIVED", s)
    n = len(MUTANTS_TRIGGER) + len(MUTANTS_DEPLOY)
    print(f"{n - len(survivors)}/{n} mutants killed")
    sys.exit(1 if failures or survivors else 0)


if __name__ == "__main__":
    main()
