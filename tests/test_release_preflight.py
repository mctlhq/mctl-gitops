"""scripts/release-preflight.py, and where the release workflows run it."""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_TEXT = (ROOT / "scripts/release-preflight.py").read_text()
GATE = "platform-gitops/release-gates.yaml"
BIND = "platform-gitops/release-bindings.yaml"
SVC = "platform-gitops/services"
WORKERS = [f"{SVC}/admins/mctl-agents-worker{s}/values.yaml" for s in ("", "-exec", "-implement")]
AGENTS = "ghcr.io/mctlhq/mctl-agents"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:300]}")


def docker_stub(tmp, rc, stderr=""):
    b = tmp / "bin"
    b.mkdir(exist_ok=True)
    (b / "docker").write_text(f"#!/bin/sh\necho called >> '{tmp}/docker.log'\nprintf '%s\\n' '{stderr}' >&2\nexit {rc}\n")
    (b / "docker").chmod(0o755)


ABSENT = "manifest unknown"


def run(stage="preflight", script=SCRIPT_TEXT, prepare=None, docker=(1, ABSENT), **inputs):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "scripts").mkdir()
        (tmp / "scripts/release-preflight.py").write_text(script)
        shutil.copy(ROOT / "scripts/release-gate.py", tmp / "scripts/release-gate.py")
        (tmp / "platform-gitops").mkdir()
        shutil.copy(ROOT / GATE, tmp / GATE)
        shutil.copy(ROOT / BIND, tmp / BIND)
        for w in WORKERS:
            (tmp / w).parent.mkdir(parents=True)
            shutil.copy(ROOT / w, tmp / w)
        app = tmp / SVC / "labs/mctl-alice/values.yaml"
        app.parent.mkdir(parents=True)
        app.write_text("image:\n  repository: ghcr.io/mctlhq/mctl-alice\n  tag: \"1.0.0\"\n")
        if docker is not None:
            docker_stub(tmp, *docker)
        if prepare:
            prepare(tmp)
        env = {"REPO": "mctlhq/mctl-alice", "IMAGE_NAME": "ghcr.io/mctlhq/mctl-alice", "IMAGE_TAG": "2.0.0",
               "GIT_REF": "2.0.0", "TEAM": "labs", "SERVICE": "mctl-alice", "VALUES_PATH": "", "VALUES_GLOB": ""}
        env.update(inputs)
        path = f"{tmp}/bin:{os.environ['PATH']}" if docker is not None else os.environ["PATH"]
        r = subprocess.run([sys.executable, "scripts/release-preflight.py", *([stage] if stage else [])], cwd=tmp,
                           capture_output=True, text=True, env={**os.environ, **env, "PATH": path})
        called = (tmp / "docker.log").exists()
        return r.returncode, r.stdout + r.stderr, called


def rc(**kw):
    return run(**kw)[0]


WORKER_RELEASE = dict(REPO="mctlhq/mctl-agents", IMAGE_NAME=AGENTS, IMAGE_TAG="1.999.0", GIT_REF="1.999.0",
                      TEAM="admins", SERVICE="mctl-agents", VALUES_PATH=",".join(WORKERS))

# Ordinary releases pass.
check("an ordinary release passes preflight", rc() == 0)
check("an ordinary release passes publish", rc(stage="publish") == 0)
check("the worker group release passes", rc(**WORKER_RELEASE) == 0, run(**WORKER_RELEASE)[1])
check("newline-separated paths pass", rc(**{**WORKER_RELEASE, "VALUES_PATH": "\n".join(WORKERS)}) == 0)

# Every real caller's pair, read from each repository's default branch on 2026-11-06.
CALLERS = [("mctl-telegram", "mctl-telegram"), ("mctl-telegram", "agent-worker"), ("mctl-telegram", "agent-worker-preview"),
           ("mctl-academy", "mctl-academy"), ("mctl-web", "mctl-web"), ("mctl-docs", "mctl-docs"),
           ("mctl-design", "mctl-design"), ("portfolio", "portfolio"), ("seerrsense", "seerrsense"),
           ("mctl-alice", "mctl-alice"), ("mctl-api", "mctl-api"), ("mctl-agents", "mctl-agents"),
           ("mctl-agent", "mctl-agent"), ("mctl-portal", "mctl-portal")]
table = yaml.safe_load((ROOT / BIND).read_text())["bindings"]
check("the binding table is exactly the real callers",
      table == {f"ghcr.io/mctlhq/{i}": f"mctlhq/{r}" for r, i in CALLERS}, table)
SHA = "4ccb257" + "a" * 33
check("preview caller shape passes: main-<sha> from that sha",
      rc(REPO="mctlhq/mctl-telegram", IMAGE_NAME="ghcr.io/mctlhq/agent-worker-preview", IMAGE_TAG="main-4ccb257",
         GIT_REF=SHA) == 0)
check("design caller shape passes: bare sha", rc(REPO="mctlhq/mctl-design", IMAGE_NAME="ghcr.io/mctlhq/mctl-design",
      IMAGE_TAG=SHA[:12], GIT_REF=SHA) == 0)
check("repository comparison ignores case", rc(REPO="MctlHQ/Mctl-Alice") == 0)

# Binding.
r, out, _ = run(**{**WORKER_RELEASE, "REPO": "mctlhq/mctl-alice"})
check("another repository cannot publish the worker image", r == 8, out)
check("a lookalike repository cannot either", rc(REPO="mctlhq/mctl-alice-x") == 8)
check("another org's repository cannot either", rc(REPO="other/mctl-alice") == 8)
check("an image not in the table is refused", rc(IMAGE_NAME="ghcr.io/mctlhq/brand-new") == 8)
for label, text in {"missing": None, "empty": "", "no key": "x: 1\n", "empty table": "bindings: {}\n",
                    "a list": "bindings: []\n", "broken": "bindings: [\n", "a non-string": "bindings:\n  ghcr.io/mctlhq/mctl-alice: 7\n"}.items():
    def prep(tmp, text=text):
        if text is None:
            (tmp / BIND).unlink()
        else:
            (tmp / BIND).write_text(text)
    code = rc(prepare=prep)
    check(f"a binding file that is {label} refuses", code in (2, 8), code)

# Shapes.
for label, kw in {
    "tag with a newline": {"IMAGE_TAG": "1\nx", "GIT_REF": "1\nx"},
    "tag with a trailing newline": {"IMAGE_TAG": "1.0\n", "GIT_REF": "1.0\n"},
    "other registry": {"IMAGE_NAME": "docker.io/mctlhq/mctl-alice"},
    "other org image": {"IMAGE_NAME": "ghcr.io/other/mctl-alice"},
    "repo with a slash too many": {"REPO": "a/b/c"},
    "ref starting with a dash": {"GIT_REF": "--upload-pack=x", "IMAGE_TAG": "1.0"},
    "empty ref": {"GIT_REF": ""},
}.items():
    check(f"{label} is refused", rc(**kw) == 5, run(**kw)[1])

# The ref must fit the tag.
for label, kw in {
    "a branch": {"GIT_REF": "feature/x"},
    "main": {"GIT_REF": "main"},
    "another tag": {"GIT_REF": "1.9.9"},
    "a sha under a release tag": {"GIT_REF": SHA},
    "a sha not in the tag": {"IMAGE_TAG": "main-1234567", "GIT_REF": SHA},
    "a sha-shaped tag from a branch": {"IMAGE_TAG": "main-4ccb257", "GIT_REF": "main"},
    "a short sha": {"IMAGE_TAG": "main-4ccb257", "GIT_REF": "4ccb257aaa"},
    "a floating ref as its own tag": {"IMAGE_TAG": "main", "GIT_REF": "main"},
    "a word as its own tag": {"IMAGE_TAG": "feature-x", "GIT_REF": "feature-x"},
    "latest as its own tag": {"IMAGE_TAG": "latest", "GIT_REF": "latest"},
    "too short a sha": {"IMAGE_TAG": "main-abc", "GIT_REF": "abc" + "0" * 37},
}.items():
    check(f"{label} does not fit the tag", rc(**kw) == 9, run(**kw)[1])

# Gate before the build.
r, out, _ = run(**{**WORKER_RELEASE, "VALUES_PATH": WORKERS[0]})
check("a partial worker release is refused", r == 6, out)
check("a worker release below the floor is refused", rc(**{**WORKER_RELEASE, "IMAGE_TAG": "1.0.0", "GIT_REF": "1.0.0"}) == 6)
check("a v-prefixed version is a release tag", rc(IMAGE_TAG="v1.2.3", GIT_REF="v1.2.3") == 0)
check("a prerelease version is a release tag", rc(IMAGE_TAG="1.2.3-rc.1", GIT_REF="1.2.3-rc.1") == 0)
check("no files named falls back to the service's own, also for the gate",
      rc(REPO="mctlhq/mctl-agents", IMAGE_NAME=AGENTS, IMAGE_TAG="1.999.0", GIT_REF="1.999.0", TEAM="admins",
         SERVICE="mctl-agents-worker") == 6)
check("a glob's matches reach the gate",
      rc(**{**WORKER_RELEASE, "VALUES_PATH": "", "VALUES_GLOB": f"{SVC}/admins/mctl-agents-worker/values.*"}) == 6)


def no_gate(tmp):
    (tmp / GATE).unlink()


def crash_gate(tmp):
    (tmp / "scripts/release-gate.py").write_text("raise SystemExit(1)\n")


check("a missing gate file refuses", rc(prepare=no_gate) == 6)
check("a gate that fails refuses", rc(prepare=crash_gate) == 6)

# Paths.
for label, kw in {
    "traversal": {"VALUES_PATH": f"{SVC}/../../etc/passwd"},
    "absolute": {"VALUES_PATH": "/etc/passwd"},
    "outside the prefixes": {"VALUES_PATH": ".github/workflows/release-deploy.yaml"},
    "missing": {"VALUES_PATH": f"{SVC}/labs/none/values.yaml"},
    "a glob with no match": {"VALUES_GLOB": f"{SVC}/labs/none*/values.yaml"},
    "a glob outside the prefixes": {"VALUES_GLOB": "*"},
}.items():
    check(f"a path that is {label} is refused", rc(**kw) == 4, run(**kw)[1])


def link(tmp):
    d = tmp / SVC / "labs/link"
    d.mkdir()
    (d / "values.yaml").symlink_to(tmp / WORKERS[0])


check("a symlink to a gated file is refused", rc(prepare=link, VALUES_PATH=f"{SVC}/labs/link/values.yaml") == 4)

# Replacing a tag.
# The images are private, and preflight holds no registry login: it must not ask.
r, out, called = run(stage="preflight", docker=(1, "unauthorized: authentication required"))
check("preflight does not call the registry", r == 0 and not called, (r, out))
for stage in ("publish",):
    r, out, called = run(stage=stage, docker=(0, ""))
    check(f"{stage}: an existing release tag is refused", r == 10 and called, (r, out))
    r, out, _ = run(stage=stage, docker=(1, "unauthorized: authentication required"))
    check(f"{stage}: an anonymous answer is not read as absent", r == 11, (r, out))
    r, out, _ = run(stage=stage, docker=(1, "denied: denied"))
    check(f"{stage}: a registry refusal is not read as absent", r == 11, (r, out))
    r, out, _ = run(stage=stage, docker=(1, "toomanyrequests: rate limit"))
    check(f"{stage}: a rate limit is not read as absent", r == 11, (r, out))
    r, out, _ = run(stage=stage, docker=(1, ""))
    check(f"{stage}: silence is not read as absent", r == 11, (r, out))
    r, out, _ = run(stage=stage, docker=(1, "no such manifest: x"))
    check(f"{stage}: the other absent wording is accepted", r == 0, (r, out))
r, out, called = run(stage="publish", docker=(0, ""), REPO="mctlhq/mctl-telegram", IMAGE_NAME="ghcr.io/mctlhq/agent-worker-preview",
                     IMAGE_TAG="main-4ccb257", GIT_REF=SHA)
check("a tag carrying the commit's sha may be rebuilt", r == 0 and not called, (r, out))


# Direct dispatch.
check("direct: the gated image is refused", rc(stage="publish-direct", IMAGE_NAME=AGENTS) == 8)
r, out, called = run(stage="publish-direct", IMAGE_NAME="ghcr.io/mctlhq/grafana-iac", REPO="x/y", GIT_REF="any", docker=(0, ""))
check("direct: an image outside the table passes, with no registry call", r == 0 and not called, (r, out))
r, out, _ = run(stage="publish-direct", GIT_REF="any-branch", docker=(0, ""))
check("direct: a bound image's existing tag is not replaced", r == 10, (r, out))
r, out, _ = run(stage="publish-direct", GIT_REF="any-branch", docker=(1, ABSENT))
check("direct: a bound image's new tag passes", r == 0, (r, out))
r, out, _ = run(stage="publish-direct", GIT_REF="any-branch", docker=(1, "denied"))
check("direct: a bound image with no registry answer refuses", r == 11, (r, out))
r, out, _ = run(stage="publish-direct", IMAGE_TAG="main-4ccb257", GIT_REF=SHA, docker=(0, ""))
check("direct: a sha tag from its own commit may be rebuilt", r == 0, (r, out))
check("direct: an unreadable gate refuses", rc(stage="publish-direct", prepare=no_gate) == 2)
check("no stage refuses", rc(stage="") == 2)
check("an unknown stage refuses", rc(stage="nonsense") == 2)

# Where it runs.
rd = yaml.safe_load((ROOT / ".github/workflows/release-deploy.yaml").read_text())
bi = yaml.safe_load((ROOT / ".github/workflows/build-image.yaml").read_text())
jobs = rd["jobs"]
check("order: validate, preflight, build, bump",
      jobs["preflight"]["needs"] == "validate-inputs" and jobs["build"]["needs"] == "preflight"
      and jobs["bump"]["needs"] == "build")
check("preflight holds no secret and no environment",
      "secrets." not in str(jobs["preflight"]) and "environment" not in jobs["preflight"]
      and jobs["preflight"]["permissions"] == {"contents": "read"})
co = [s for s in jobs["preflight"]["steps"] if "checkout" in s.get("uses", "")][0]["with"]
check("preflight reads policy from main with no credentials", co["ref"] == "main" and co["persist-credentials"] is False)
check("the build receives the files", {"values_path", "values_glob"} <= set(jobs["build"]["with"]))
steps = bi["jobs"]["build"]["steps"]
names = [s.get("name", "") for s in steps]
i = names.index("Build and push")
check("the publish check is directly before the push", names[i - 1] == "Check the release before publishing", names[i - 1])
check("the policy checkout is from main", steps[i - 2]["with"]["ref"] == "main" and steps[i - 2]["with"]["persist-credentials"] is False)
check("the policy is removed before the build context is used", "rm -rf .release-policy" in steps[i - 1]["run"])
check("the check has no condition", "if" not in steps[i - 1])
check("the policy checkout names this repository, not the caller's",
      steps[i - 2]["with"]["repository"] == "mctlhq/mctl-gitops")
check("a policy path from the source is refused first", names[i - 3] == "Refuse a release policy path from the source")
# A check that cannot fail is no check.
for label, step in (("publish check", steps[i - 1]), ("policy path check", steps[i - 3]),
                    ("preflight", [s for s in jobs["preflight"]["steps"] if s.get("name") == "Release preflight"][0])):
    check(f"{label}: nothing lets a failure through",
          "continue-on-error" not in step and "|| true" not in step["run"] and "if" not in step)
for job in ("preflight", "build", "bump"):
    check(f"{job}: no job-level condition can skip its dependency", "if" not in jobs[job] and "continue-on-error" not in jobs[job])
py = re.findall(r'"([^"]+/)"', re.search(r"ALLOWED_PREFIXES = \((.*?)\)", SCRIPT_TEXT, re.S).group(1))
shell = re.findall(r'"([^"]+)"', re.search(r"ALLOWED_PREFIXES=\((.*?)\)",
                   (ROOT / ".github/workflows/release-deploy.yaml").read_text(), re.S).group(1))
check("the prefix list matches release-deploy", py == shell, (py, shell))


# Mutants.
def cut(line):
    assert line in SCRIPT_TEXT, line
    return SCRIPT_TEXT.replace(line, line.replace(line.strip(), "pass"))


M = {
    "binding off, another repository publishes the worker image":
        lambda: rc(script=cut("        check_binding()\n"), **{**WORKER_RELEASE, "REPO": "mctlhq/mctl-alice"}) == 0,
    "ref rule off, a branch builds a release":
        lambda: rc(script=cut("        check_ref()\n"), GIT_REF="feature/x") == 0,
    "gate off, a partial worker release passes":
        lambda: rc(script=cut("        check_gate()\n"), **{**WORKER_RELEASE, "VALUES_PATH": WORKERS[0]}) == 0,
    "tag check off, an existing tag is replaced":
        lambda: rc(stage="publish", script=cut("            check_tag_free()\n"), docker=(0, "")) == 0,
    "tag check back in preflight, every private image is refused":
        lambda: rc(script=SCRIPT_TEXT.replace('        if stage == "publish":\n            check_tag_free()', '        check_tag_free()'),
                   docker=(1, "unauthorized")) == 11,
    "direct tag check off, a bound tag is replaced":
        lambda: rc(stage="publish-direct", script=cut("        check_tag_free()\n"), docker=(0, "")) == 0,
    "release tag shape off, main stands in for a version":
        lambda: rc(script=SCRIPT_TEXT.replace(' and re.fullmatch(RELEASE_TAG_RE, env("IMAGE_TAG"))', ""), IMAGE_TAG="main", GIT_REF="main") == 0,
    "any failure read as absent":
        lambda: rc(script=SCRIPT_TEXT.replace("if not ABSENT_RE.search(r.stderr):", "if False:"), docker=(1, "denied")) == 0,
    "symlink check off":
        lambda: rc(script=SCRIPT_TEXT.replace("if os.path.relpath(os.path.realpath(f)) != os.path.normpath(f):", "if False:"),
                   prepare=link, VALUES_PATH=f"{SVC}/labs/link/values.yaml") != 4,
    "direct check off":
        lambda: rc(stage="publish-direct", script=cut("        check_direct()\n"), IMAGE_NAME=AGENTS) == 0,
    "sha rule loose, any sha allowed":
        lambda: rc(script=SCRIPT_TEXT.replace('and env("GIT_REF").startswith(m.group(1))', ""), IMAGE_TAG="main-1234567", GIT_REF=SHA) == 0,
}
for label, fn in M.items():
    check(f"mutant caught: {label}", fn())

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
