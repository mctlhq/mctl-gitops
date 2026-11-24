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
import shutil

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



def trust_policy(tmp):
    """The bump steps read the gate policy from origin/main (--policy-rev): give the
    scratch checkout an origin/main that carries its policy file."""
    def git(*a):
        subprocess.run(["git", "-C", str(tmp), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                       check=True, capture_output=True)
    git("init", "-q")
    git("add", "platform-gitops/release-gates.yaml")
    git("commit", "-qm", "policy", "--no-gpg-sign")
    git("update-ref", "refs/remotes/origin/main", "HEAD")


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
    # The bump step now runs the release gate (mctl-agents#1007) from the
    # checkout, and fails closed without it. These fixtures exercise the
    # rewriter, not the gate, so they carry the real script and a gate over
    # an unrelated group; tests/test_release_gate.py covers the gate itself.
    (tmp / "scripts").mkdir()
    shutil.copy(pathlib.Path("scripts/release-gate.py"), tmp / "scripts/release-gate.py")
    (tmp / "platform-gitops/release-gates.yaml").write_text(
        "version_holds: []\ngates:\n  - name: unrelated\n    paths: [platform-gitops/services/none/values.yaml]\n"
        '    min_tag: "0.0.1"\n'
    )
    trust_policy(tmp)


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

# 12-14: protections gitops-bump.yaml already had and release-deploy lacked
# (mctl-gitops#2652). Each is also run with the protection removed, and must
# then go wrong: a check that cannot fail is no check.
SPLIT_VALUES = """image:
  registry: ghcr.io
  repository: mctlhq/mctl-agents
  tag: 1.34.0
"""
SYMLINK_OFF = 'if os.path.realpath(path) != os.path.join(os.path.realpath(os.curdir), normalized):'
EDIT_CHECK_OFF = "if not only_tags_changed(content, out):"
SPLIT_QUOTE_OFF = """out, n3 = p3.subn(lambda m: m.group(1) + ' "' + new_tag + '"', out)"""
TAG_CHECK_OFF = "if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]{0,127}', new_tag):"
for anchor in (SYMLINK_OFF, EDIT_CHECK_OFF, SPLIT_QUOTE_OFF, TAG_CHECK_OFF):
    check(f"anchor present once: {anchor[:50]}", SCRIPT.count(anchor) == 1)


def run_script(tmp, script, vpath, tag="1.35.0"):
    return subprocess.run(
        [sys.executable, "-c", script], cwd=tmp,
        env={**os.environ, "TEAM": "admins", "SERVICE": "mctl-agents-worker",
             "VALUES_PATH": vpath, "VALUES_GLOB": "",
             "IMAGE_NAME": "ghcr.io/mctlhq/mctl-agents", "NEW_TAG": tag,
             "GITHUB_ENV": str(tmp / "e"), "GITHUB_OUTPUT": str(tmp / "o")},
        capture_output=True, text=True,
    )


def symlink_case(script):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        outside = tmp / "outside.yaml"
        outside.write_text(VALUES)
        link = tmp / "platform-gitops/services/admins/linked"
        link.mkdir()
        (link / "values.yaml").symlink_to(outside)
        r = run_script(tmp, script, "platform-gitops/services/admins/linked/values.yaml")
        return r.returncode, outside.read_text() != VALUES


rc, wrote = symlink_case(SCRIPT)
check("a symlinked values file is refused before writing", rc == 4 and not wrote, (rc, wrote))
rc, wrote = symlink_case(SCRIPT.replace(SYMLINK_OFF, "if False:"))
check("mutant caught: symlink check off, the file behind the link is written", wrote, rc)


def split_case(script, tag):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        (tmp / P1).write_text(SPLIT_VALUES)
        r = run_script(tmp, script, P1, tag)
        import yaml
        return r.returncode, yaml.safe_load((tmp / P1).read_text())["image"]["tag"]


for tag in ("1042", "1e5", "1.10"):
    rc, got = split_case(SCRIPT, tag)
    check(f"a split-style file takes tag {tag} as a string", rc == 0 and got == tag, (rc, got))
rc, got = split_case(SCRIPT.replace(SPLIT_QUOTE_OFF, "out, n3 = p3.subn(lambda m: m.group(1) + ' ' + new_tag, out)"), "1042")
check("mutant caught: unquoted split tag turns 1042 into a number", got != "1042", (rc, got))


def edit_case(script):
    # With the tag check off, a tag carrying YAML reaches the rewriter: only the
    # edit check is left to stop it.
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        r = run_script(tmp, script.replace(TAG_CHECK_OFF, "if False:"), P1, INJECTION)
        return r.returncode, "privileged" in (tmp / P1).read_text()


rc, wrote = edit_case(SCRIPT)
check("an edit beyond image tags is refused before writing", rc == 7 and not wrote, (rc, wrote))
rc, wrote = edit_case(SCRIPT.replace(EDIT_CHECK_OFF, "if False:"))
check("mutant caught: edit check off, the injected YAML is written", wrote, rc)

# An Argo CD Application that parses as YAML and keeps its Helm values inline
# (mctl-platform/mctl-agent.yaml). The 2.9.6 bump was refused with exit 7 on
# 2026-11-23: the tag sits inside the values string.
APP = "platform-gitops/bootstrap/templates/mctl-platform/mctl-app.yaml"
APP_TEXT = (
    "apiVersion: argoproj.io/v1alpha1\nkind: Application\nspec:\n  source:\n    helm:\n      values: |\n"
    "        image:\n          repository: ghcr.io/mctlhq/mctl-agents\n          tag: \"1.0.0\"\n"
    "        env:\n          A: b\n")
INNER_ON = 'if isinstance(a, str) and isinstance(b, str) and "\\n" in a:'
INNER_RULE = "return isinstance(inner_a, (dict, list)) and same_but_tags(inner_a, inner_b)"
TAMPER = "n = n1 + n2 + n3 + n4\n"
for anchor in (INNER_ON, INNER_RULE, TAMPER):
    check(f"anchor present once: {anchor[:50]}", SCRIPT.count(anchor) == 1)


def app_case(script, tag="1.35.0"):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        (tmp / APP).parent.mkdir(parents=True, exist_ok=True)
        (tmp / APP).write_text(APP_TEXT)
        r = run_script(tmp, script, APP, tag)
        return r.returncode, (tmp / APP).read_text()


rc, text = app_case(SCRIPT)
check("an Application with inline Helm values bumps",
      rc == 0 and text == APP_TEXT.replace('"1.0.0"', '"1.35.0"'), (rc, text))
rc, text = app_case(SCRIPT.replace(INNER_ON, "if False:"))
check("mutant caught: without the inline rule the Application bump is refused", rc == 7 and text == APP_TEXT, rc)
# An unrelated value inside the inline values that merely contains a short tag.
SHORT = SCRIPT.replace(TAMPER, "out = out.replace('A: b', 'A: x1y')\n    " + TAMPER, 1)
rc, text = app_case(SHORT, tag="1")
check("inside inline values, a value merely containing a short tag is refused", rc == 7 and text == APP_TEXT, rc)
rc, text = app_case(SHORT.replace(INNER_RULE, "return True"), tag="1")
check("mutant caught: block strings accepted blind, the unrelated value is written", "A: x1y" in text, rc)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
