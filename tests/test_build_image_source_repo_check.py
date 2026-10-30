"""build-image.yaml "Check source repository": the branch for a repository
that is not registered, not public and has no Vault PAT (gitops#2146).

That branch asks mctl-api (GET /api/v1/ci/build-repo-binding, OIDC) whether
the team's GitHub App installation binds the repository, and builds only on a
200 whose `bound` is the boolean true and whose team/repo echo the request.
Every other answer refuses: "could not observe" is never "not bound", and
never "bound" either.

This runs the step's own script, extracted from the workflow, under bash with
a fake `curl` on PATH that plays GitHub, the Actions OIDC endpoint and
mctl-api from per-case JSON, and records every call.
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
WF = REPO / ".github/workflows/build-image.yaml"
STEP = "Check source repository"

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


wf = yaml.safe_load(WF.read_text())
steps = [s for job in wf["jobs"].values() for s in job.get("steps", []) if s.get("name") == STEP]
if len(steps) != 1:
    print(f"FAIL: expected one {STEP!r} step in {WF.name}, found {len(steps)}", file=sys.stderr)
    sys.exit(1)
step = steps[0]
SCRIPT = step["run"]
check(step["env"].get("MCTL_API_URL") == "https://api.mctl.ai", f"MCTL_API_URL: {step['env'].get('MCTL_API_URL')}")
check(step["env"].get("MCTL_API_AUDIENCE") == "https://api.mctl.ai",
      f"MCTL_API_AUDIENCE: {step['env'].get('MCTL_API_AUDIENCE')}")

# The fake curl. It writes the body to the -o file and prints the status for
# -w, the way the step calls it; the OIDC request (-f, no -o) gets its JSON on
# stdout. Every call is appended to $FAKE_LOG.
FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
spec = json.loads(os.environ["FAKE_SPEC"])
out = None; url = None; headers = []; data = []
i = 0
while i < len(args):
    a = args[i]
    if a == "-o": out = args[i + 1]; i += 2; continue
    if a == "-w": i += 2; continue
    if a == "-H": headers.append(args[i + 1]); i += 2; continue
    if a == "--data-urlencode": data.append(args[i + 1]); i += 2; continue
    if a.startswith("http"): url = a
    i += 1
auth = any(h.startswith("Authorization: Bearer gh-job-token") for h in headers)
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"url": url, "headers": headers, "data": data}) + "\n")
if url.startswith("https://oidc.example/"):
    if spec.get("oidc") is None:
        sys.exit(22)
    print(json.dumps({"value": spec["oidc"]}))
    sys.exit(0)
if url.startswith("https://api.github.com/repos/"):
    code, body = spec["gh_auth" if auth else "gh_anon"]
elif url == "https://api.mctl.ai/api/v1/ci/build-repo-binding":
    if spec.get("api") is None:
        sys.exit(7)
    code, body = spec["api"]
else:
    sys.exit(6)
with open(out, "w") as f:
    f.write(body if isinstance(body, str) else json.dumps(body))
sys.stdout.write(str(code))
'''

PRIVATE = (404, {"message": "Not Found"})
BOUND = {"team": "acme", "repo": "Acme/private-app", "bound": True}


def run(spec, oidc_env=True):
    d = pathlib.Path(tempfile.mkdtemp())
    try:
        (d / ".image-name-policy/platform-gitops/services/other").mkdir(parents=True)
        bindir = d / "bin"
        bindir.mkdir()
        curl = bindir / "curl"
        curl.write_text(FAKE_CURL)
        curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
        log = d / "calls.log"
        log.touch()
        env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "INPUT_REPO": "Acme/private-app", "INPUT_TEAM_NAME": "acme",
            "INPUT_COMPONENT_NAME": "private-app", "HAS_PAT": "false",
            "GH_TOKEN": "gh-job-token", "GITHUB_REPOSITORY": "mctlhq/mctl-gitops",
            "MCTL_API_URL": step["env"]["MCTL_API_URL"], "MCTL_API_AUDIENCE": step["env"]["MCTL_API_AUDIENCE"],
            "FAKE_SPEC": json.dumps(spec), "FAKE_LOG": str(log),
        }
        if oidc_env:
            env["ACTIONS_ID_TOKEN_REQUEST_URL"] = "https://oidc.example/token?x=1"
            env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = "req-token"
        p = subprocess.run(["bash", "-c", SCRIPT], cwd=d, env=env, capture_output=True, text=True, timeout=60)
        calls = [json.loads(l) for l in log.read_text().splitlines()]
        check(not (d / ".image-name-policy").exists(), "the step must remove .image-name-policy on exit")
        return p.returncode, p.stdout + p.stderr, calls
    finally:
        shutil.rmtree(d)


def api_calls(calls):
    return [c for c in calls if c["url"] == "https://api.mctl.ai/api/v1/ci/build-repo-binding"]


def base(**over):
    spec = {"gh_auth": PRIVATE, "gh_anon": PRIVATE, "oidc": "oidc-token", "api": (200, BOUND)}
    spec.update(over)
    return spec


# A public repository builds without asking mctl-api.
rc, out, calls = run(base(gh_auth=(200, {"visibility": "public"})))
check(rc == 0 and "(not registered; public)" in out, f"public repository: rc={rc}\n{out}")
check(not api_calls(calls), "a public repository must not reach mctl-api")

# The job token is scoped to mctl-gitops: a 403 for another repository is
# asked again anonymously.
rc, out, calls = run(base(gh_auth=(403, {}), gh_anon=(200, {"visibility": "public"})))
check(rc == 0 and "(not registered; public)" in out, f"403 then anonymous public: rc={rc}\n{out}")

# Not public, bound through the App: builds, and the request is what
# mctl-api's route expects.
rc, out, calls = run(base())
check(rc == 0 and "bound to acme through the GitHub App" in out, f"bound: rc={rc}\n{out}")
a = api_calls(calls)
check(len(a) == 1, f"bound: expected one mctl-api call, got {len(a)}")
if a:
    check("Authorization: Bearer oidc-token" in a[0]["headers"], f"mctl-api call headers: {a[0]['headers']}")
    check("User-Agent: mctl-gitops-build-image" in a[0]["headers"],
          "mctl-api call must set a User-Agent (Cloudflare refuses some defaults)")
    check(sorted(a[0]["data"]) == ["repo=Acme/private-app", "team=acme"], f"mctl-api query: {a[0]['data']}")
oidc = [c for c in calls if c["url"].startswith("https://oidc.example/")]
check(oidc and oidc[0]["url"].endswith("&audience=https://api.mctl.ai"), f"OIDC audience: {oidc}")
check(oidc and "Authorization: Bearer req-token" in oidc[0]["headers"], "OIDC request must carry the request token")
check("oidc-token" not in out.replace("::add-mask::oidc-token", ""), "the OIDC token leaked into the log")

# A repo answer that differs only in case is the same repository.
rc, out, _ = run(base(api=(200, {**BOUND, "repo": "acme/PRIVATE-app"})))
check(rc == 0, f"case-insensitive repo echo: rc={rc}\n{out}")

# Every answer but a matching boolean true refuses.
REFUSE = [
    ("not bound", base(api=(200, {**BOUND, "bound": False})), "does not bind it"),
    ("bound as a string", base(api=(200, {**BOUND, "bound": "true"})), "malformed binding answer"),
    ("bound missing", base(api=(200, {"team": "acme", "repo": "Acme/private-app"})), "malformed binding answer"),
    ("bound null", base(api=(200, {**BOUND, "bound": None})), "malformed binding answer"),
    ("another team echoed", base(api=(200, {**BOUND, "team": "other"})), "mctl-api answered for other/"),
    ("another repo echoed", base(api=(200, {**BOUND, "repo": "Acme/other"})), "mctl-api answered for acme/Acme/other"),
    ("no echo", base(api=(200, {"bound": True})), "mctl-api answered for ?/?"),
    ("not JSON", base(api=(200, "<html>")), "unreadable binding answer"),
    ("403 from mctl-api", base(api=(403, {"code": "ci_build_binding_denied"})), "(HTTP 403)"),
    ("503 from mctl-api", base(api=(503, {})), "(HTTP 503)"),
    ("401 from mctl-api", base(api=(401, {})), "(HTTP 401)"),
    ("mctl-api unreachable", base(api=None), "(HTTP 000)"),
    ("no OIDC token minted", base(oidc=None), "could not mint an OIDC token"),
    ("empty OIDC token", base(oidc=""), "could not mint an OIDC token"),
    ("GitHub 500", base(gh_auth=(500, {})), "could not read the visibility"),
    ("anonymous rate limit", base(gh_auth=(403, {}), gh_anon=(403, {})), "could not read the visibility"),
]
for label, spec, want in REFUSE:
    rc, out, calls = run(spec)
    check(rc != 0 and want in out and "(not registered;" not in out,
          f"{label}: rc={rc}, want a refusal with {want!r}\n{out}")

rc, out, calls = run(base(), oidc_env=False)
check(rc != 0 and "no OIDC token available" in out, f"no OIDC env: rc={rc}\n{out}")
check(not api_calls(calls), "without an OIDC token mctl-api must not be called")

# The App-bound verdict is the only way past a non-public repository without
# a PAT: the job asks for id-token: write so the OIDC token can be minted.
job = next(j for j in wf["jobs"].values() if any(s.get("name") == STEP for s in j.get("steps", [])))
perms = job.get("permissions", wf.get("permissions", {})) or {}
check(perms.get("id-token") == "write", f"the build job needs id-token: write, has {perms}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"build-image source check: public, 403 retry, bound, case-insensitive echo, {len(REFUSE) + 1} refusals")
