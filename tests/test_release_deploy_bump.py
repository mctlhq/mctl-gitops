"""Run release-deploy.yaml's embedded bump script against fixtures.

The script only ever executes during a real release, so this extracts it
from the workflow and exercises it locally: two named paths, one of them
without the image (must fail), and the glob combination.
"""
import os
import re
import subprocess
import sys
import tempfile
import pathlib

WF = pathlib.Path(".github/workflows/release-deploy.yaml").read_text()

# The bump step's heredoc.
m = re.search(r"- name: Bump image tag\(s\).*?python3 <<'PYEOF'\n(.*?)\n\s*PYEOF", WF, re.S)
assert m, "could not extract the bump script"
body = m.group(1)
# Strip the YAML block indentation (10 spaces).
lines = [ln[10:] if ln.startswith(" " * 10) else ln for ln in body.split("\n")]
SCRIPT = "\n".join(lines)

VALUES = """replicaCount: 1
image:
  repository: ghcr.io/mctlhq/mctl-agents
  tag: "1.34.0"
"""
CWFT = """      - name: agent_image
        value: ghcr.io/mctlhq/mctl-agents:1.34.0
"""
UNRELATED = """replicaCount: 1
image:
  repository: ghcr.io/mctlhq/something-else
  tag: "0.1.0"
"""


def run(tmp, vpath, vglob=""):
    env = {
        **os.environ,
        "TEAM": "admins",
        "SERVICE": "mctl-agents-worker",
        "VALUES_PATH": vpath,
        "VALUES_GLOB": vglob,
        "IMAGE_NAME": "ghcr.io/mctlhq/mctl-agents",
        "NEW_TAG": "1.35.0",
        "GITHUB_ENV": str(tmp / "gh_env"),
        "GITHUB_OUTPUT": str(tmp / "gh_out"),
    }
    (tmp / "gh_env").touch()
    (tmp / "gh_out").touch()
    return subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=tmp, env=env,
        capture_output=True, text=True,
    )


def fixture(tmp, *, exec_values=True, exec_has_image=True):
    base = tmp / "platform-gitops/services/admins"
    (base / "mctl-agents-worker").mkdir(parents=True)
    (base / "mctl-agents-worker/values.yaml").write_text(VALUES)
    if exec_values:
        (base / "mctl-agents-worker-exec").mkdir(parents=True)
        (base / "mctl-agents-worker-exec/values.yaml").write_text(
            VALUES if exec_has_image else UNRELATED
        )
    cw = tmp / "platform-gitops/argo-workflows/cluster-templates"
    cw.mkdir(parents=True)
    (cw / "cwft-mctl-agents-investigate.yaml").write_text(CWFT)


P1 = "platform-gitops/services/admins/mctl-agents-worker/values.yaml"
P2 = "platform-gitops/services/admins/mctl-agents-worker-exec/values.yaml"
GLOB = "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml"

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


# 1. One path — the behaviour every other repo already relies on.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    r = run(tmp, P1)
    check("single path still works", r.returncode == 0, r.stderr)
    check("single path bumped", '1.35.0' in (tmp / P1).read_text(), r.stdout)

# 2. Two paths, comma-separated — both must be bumped.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    r = run(tmp, f"{P1},{P2}")
    check("two paths accepted", r.returncode == 0, r.stderr)
    check("first bumped", "1.35.0" in (tmp / P1).read_text(), r.stdout)
    check("second bumped", "1.35.0" in (tmp / P2).read_text(), r.stdout)

# 3. Newline-separated, the shape a YAML block scalar produces.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    r = run(tmp, f"{P1}\n{P2}\n")
    check("newline-separated accepted", r.returncode == 0, r.stderr)
    check("both bumped (newlines)",
          "1.35.0" in (tmp / P1).read_text() and "1.35.0" in (tmp / P2).read_text(),
          r.stdout)

# 4. THE POINT: a named path that does not carry the image is an ERROR,
#    even when the other named path matched. Silence here is what pins a
#    worker forever.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp, exec_has_image=False)
    r = run(tmp, f"{P1},{P2}")
    check("a non-matching second path fails the run", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    check("the error names the offending path", P2 in r.stderr, r.stderr)

# 5. A named path that does not exist at all.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp, exec_values=False)
    r = run(tmp, f"{P1},{P2}")
    check("a missing second path fails the run", r.returncode == 2, f"rc={r.returncode} {r.stdout}")

# 6. Combined with the glob, which is how mctl-agents actually calls it.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    r = run(tmp, f"{P1},{P2}", GLOB)
    check("glob + two paths", r.returncode == 0, r.stderr)
    check("cwft bumped too",
          "1.35.0" in (tmp / "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml").read_text(),
          r.stdout)

# 7. Traversal is still refused inside the list, not just as a lone value.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    r = run(tmp, f"{P1},platform-gitops/services/../../etc/passwd")
    check("traversal in the list is refused", r.returncode == 4, f"rc={r.returncode} {r.stderr}")

# 8. An out-of-allowlist path inside the list.
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    r = run(tmp, f"{P1},.github/workflows/release-deploy.yaml")
    check("out-of-allowlist path in the list is refused", r.returncode == 4, f"rc={r.returncode} {r.stderr}")

# 9. THE TAG IS AN INPUT. It ends up inside manifests this job commits with
#    a token that bypasses main's protection, so a newline in it would append
#    arbitrary YAML to a Deployment and land it unreviewed (agy P1 on #962).
INJECTION = '1.35.0"\n  securityContext:\n    privileged: true\n  #'
with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    fixture(tmp)
    env_tag = INJECTION
    r = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=tmp,
        env={**os.environ, "TEAM": "admins", "SERVICE": "mctl-agents-worker",
             "VALUES_PATH": P1, "VALUES_GLOB": "",
             "IMAGE_NAME": "ghcr.io/mctlhq/mctl-agents", "NEW_TAG": env_tag,
             "GITHUB_ENV": str(tmp / "e"), "GITHUB_OUTPUT": str(tmp / "o")},
        capture_output=True, text=True,
    )
    check("a tag carrying YAML is refused", r.returncode == 5, f"rc={r.returncode} {r.stdout}")
    check("nothing was written", "privileged" not in (tmp / P1).read_text(), "manifest was modified")

# 10. A backslash escape in the tag must be inserted, not expanded as a
#     group reference — a string replacement would duplicate text or fail
#     the release with re.error.
for bad in ('1.35.0\\1', '1.35.0\\g<0>'):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        r = subprocess.run(
            [sys.executable, "-c", SCRIPT], cwd=tmp,
            env={**os.environ, "TEAM": "admins", "SERVICE": "mctl-agents-worker",
                 "VALUES_PATH": P1, "VALUES_GLOB": "",
                 "IMAGE_NAME": "ghcr.io/mctlhq/mctl-agents", "NEW_TAG": bad,
                 "GITHUB_ENV": str(tmp / "e"), "GITHUB_OUTPUT": str(tmp / "o")},
            capture_output=True, text=True,
        )
        check(f"a backslash tag ({bad!r}) is refused, not expanded",
              r.returncode == 5, f"rc={r.returncode} {r.stdout} {r.stderr}")

# 11. Ordinary tags, including pre-release and build-ish forms, still pass.
for good in ("1.35.0", "1.35.0-rc.1", "sha-abc123", "v1.2.3"):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        r = subprocess.run(
            [sys.executable, "-c", SCRIPT], cwd=tmp,
            env={**os.environ, "TEAM": "admins", "SERVICE": "mctl-agents-worker",
                 "VALUES_PATH": P1, "VALUES_GLOB": "",
                 "IMAGE_NAME": "ghcr.io/mctlhq/mctl-agents", "NEW_TAG": good,
                 "GITHUB_ENV": str(tmp / "e"), "GITHUB_OUTPUT": str(tmp / "o")},
            capture_output=True, text=True,
        )
        check(f"an ordinary tag ({good}) is accepted", r.returncode == 0, r.stderr)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
