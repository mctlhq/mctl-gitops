"""gitops-bump.yaml: what a dispatch may write to main.

Both scripts are extracted from the workflow, since a restated copy would keep
passing after it changed. The bump runs against fixtures with the real
release-gate.py; nothing leaves the temporary directory.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF_TEXT = (ROOT / ".github/workflows/gitops-bump.yaml").read_text()
WF = yaml.safe_load(WF_TEXT)
VALIDATE = [s for s in WF["jobs"]["validate-inputs"]["steps"] if s.get("name") == "Validate dispatch inputs"][0]["run"]
BUMP_STEP = [s for s in WF["jobs"]["bump"]["steps"] if s.get("name") == "Bump image tags"][0]["run"]
BUMP = re.search(r"python3 <<'PYEOF'\n(.*?)\nPYEOF", BUMP_STEP, re.S).group(1)
GATE = "platform-gitops/release-gates.yaml"
OTHER = "platform-gitops/services/labs/app/values.yaml"
WORKER = "platform-gitops/services/admins/mctl-agents-worker/values.yaml"
CWFT = "platform-gitops/argo-workflows/cluster-templates/cwft-x.yaml"
TEMPLATE = "platform-gitops/bootstrap/templates/mctl-platform/mctl-x.yaml"
OTHER_IMAGE = "ghcr.io/mctlhq/app"
VALUES = f'replicaCount: 1\nimage:\n  repository: {OTHER_IMAGE}\n  tag: "1.0.0"\nenv:\n  A: b\n'
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:300]}")


def fixture(tmp):
    def w(rel, text):
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_text(text)
    w(OTHER, VALUES)
    w(CWFT, f"      - name: agent_image\n        value: {OTHER_IMAGE}:1.0.0\n      - image: {OTHER_IMAGE}:1.0.0\n")
    w(TEMPLATE, "{{- if .Values.x }}\n" + f"image: {OTHER_IMAGE}:1.0.0\n" + "{{- end }}\n")
    (tmp / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/release-gate.py", tmp / "scripts/release-gate.py")
    gate = yaml.safe_load((ROOT / GATE).read_text())
    (tmp / GATE).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / GATE, tmp / GATE)
    for g in gate["gates"]:
        for p in g["paths"]:
            (tmp / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / p, tmp / p)


def bump(tag="1.2.3", image=OTHER_IMAGE, path=OTHER, glob="", script=BUMP, prepare=None):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fixture(tmp)
        if prepare:
            prepare(tmp)
        src = script.replace("/tmp/gitops-bump-changed-files.txt", str(tmp / "changed.txt"))
        before = {str(p.relative_to(tmp)): p.read_bytes() for p in tmp.rglob("*") if p.is_file()}
        r = subprocess.run([sys.executable, "-c", src], cwd=tmp, capture_output=True, text=True,
                           env={**os.environ, "IMAGE_NAME": image, "NEW_TAG": tag,
                                "VALUES_PATH": path, "VALUES_GLOB": glob})
        changed = sorted(k for k, v in before.items() if (tmp / k).read_bytes() != v and k != "changed.txt")
        contents = {k: (tmp / k).read_text() for k in changed}
        return r.returncode, changed, contents, r.stdout + r.stderr


def validate(**kw):
    env = {"INPUT_IMAGE_NAME": OTHER_IMAGE, "INPUT_IMAGE_TAG": "1.2.3",
           "INPUT_VALUES_PATH": OTHER, "INPUT_VALUES_GLOB": ""}
    env.update({f"INPUT_{k.upper()}": v for k, v in kw.items()})
    return subprocess.run(["bash", "-e", "-c", VALIDATE], env={**os.environ, **env},
                          capture_output=True, text=True).returncode


INJECT = '1.0.0"\nfullnameOverride: PROBE\nx: "y'
BAD_TAGS = {
    "yaml through a newline": INJECT,
    "a carriage return": "1.0\rx",
    "a quote": '1.0"',
    "a space": "1.0 x",
    "a colon": "1.0:x",
    "a backslash group": "1.0\\1",
    "a group reference": "1.0\\g<0>",
    "a dollar": "1.$x",
    "empty": "",
    "a leading dot": ".1",
    "a leading dash": "-1",
    "too long": "a" * 129,
    "trailing newline": "1.0\n",
}
for label, tag in BAD_TAGS.items():
    rc, changed, _, out = bump(tag=tag)
    check(f"bump refuses a tag with {label}, writing nothing", rc == 5 and not changed, (rc, changed, out))
    check(f"validate refuses a tag with {label}", validate(image_tag=tag) != 0)

BAD_IMAGES = {
    "another registry": "docker.io/mctlhq/app",
    "another org": "ghcr.io/other/app",
    "a regex": "ghcr.io/mctlhq/.*",
    "a newline": "ghcr.io/mctlhq/app\nx",
    "a nested path": "ghcr.io/mctlhq/a/b",
    "uppercase": "ghcr.io/mctlhq/App",
    "empty": "",
}
for label, image in BAD_IMAGES.items():
    rc, changed, _, _ = bump(image=image)
    check(f"bump refuses an image with {label}", rc == 5 and not changed, rc)
    check(f"validate refuses an image with {label}", validate(image_name=image) != 0)

for label, path in {
    "traversal": "platform-gitops/services/../../etc/passwd",
    "an absolute path": "/etc/passwd",
    "a disallowed prefix": ".github/workflows/gitops-bump.yaml",
    "a prefix lookalike": "platform-gitops/services-x/a/values.yaml",
    "a newline": OTHER + "\nx",
    "a list": OTHER + "," + OTHER,
}.items():
    check(f"validate refuses a path with {label}", validate(values_path=path) != 0)
    rc, changed, _, _ = bump(path=path)
    check(f"bump refuses a path with {label}", rc != 0 and not changed, rc)
for label, glob in {
    "traversal": "platform-gitops/services/../../*",
    "a disallowed prefix": ".github/workflows/*",
    "a bare star": "*",
    "brackets": "platform-gitops/services/[a-z]*",
}.items():
    check(f"validate refuses a glob with {label}", validate(values_path="", values_glob=glob) != 0)
    if label != "brackets":
        rc, changed, _, _ = bump(path="", glob=glob)
        check(f"bump refuses a glob with {label}", rc != 0 and not changed, rc)
check("validate refuses neither path nor glob", validate(values_path="") != 0)
check("validate refuses both path and glob", validate(values_glob="platform-gitops/services/*") != 0)


def link(tmp):
    d = tmp / "platform-gitops/services/labs/link"
    d.mkdir()
    (d / "values.yaml").symlink_to(tmp / WORKER)


rc, changed, _, out = bump(path="platform-gitops/services/labs/link/values.yaml", image="ghcr.io/mctlhq/mctl-agents",
                           tag="1.999.0", prepare=link)
check("bump refuses a symlink to a gated file", rc == 4 and not changed, (rc, out))

# The gate: a partial bump, and a crash, both refuse before any write.
rc, changed, _, _ = bump(path=WORKER, image="ghcr.io/mctlhq/mctl-agents", tag="1.999.0")
check("a partial bump of the gated group is refused, writing nothing", rc == 6 and not changed, rc)


def broken_gate(tmp):
    (tmp / "scripts/release-gate.py").write_text("raise SystemExit(1)\n")


def no_gate(tmp):
    (tmp / GATE).unlink()


rc, changed, _, _ = bump(prepare=broken_gate)
check("a gate that fails refuses an ordinary bump", rc == 6 and not changed, rc)
rc, changed, _, _ = bump(prepare=no_gate)
check("a missing gate file refuses an ordinary bump", rc == 6 and not changed, rc)

# A named file that does not carry the image.
rc, changed, _, _ = bump(image="ghcr.io/mctlhq/absent")
check("a named file without the image fails, not a silent skip", rc == 3 and not changed, rc)

# Ordinary bumps still work, on every file shape.
rc, changed, contents, out = bump()
check("a values file bumps", rc == 0 and changed == [OTHER] and 'tag: "1.2.3"' in contents[OTHER], out)
check("only the tag changed", contents.get(OTHER) == VALUES.replace('"1.0.0"', '"1.2.3"'))
rc, changed, contents, out = bump(path="", glob="platform-gitops/argo-workflows/cluster-templates/cwft-*.yaml")
check("a CWFT glob bumps both forms", rc == 0 and contents[CWFT].count(":1.2.3") == 2, out)
rc, changed, contents, out = bump(path=TEMPLATE)
check("a Helm template that is not YAML bumps", rc == 0 and f"{OTHER_IMAGE}:1.2.3" in contents[TEMPLATE], out)
for good in ("1.35.0", "1.35.0-rc.1", "main-4ccb257", "0.1.0-r2", "staging-110", "v1.2.3", "a" * 128):
    check(f"an ordinary tag ({good[:20]}) is accepted", bump(tag=good)[0] == 0 and validate(image_tag=good) == 0)
check("validate accepts a glob alone", validate(values_path="", values_glob="platform-gitops/argo-workflows/cluster-templates/cwft-*.yaml") == 0)
check("validate accepts a tag and path of real shape", validate() == 0)

# Structure.
m = re.search(r"ALLOWED_PREFIXES=\((.*?)\)", VALIDATE, re.S)
shell_prefixes = re.findall(r'"([^"]+)"', m.group(1))
py_prefixes = re.findall(r'"([^"]+/)"', re.search(r"ALLOWED_PREFIXES = \((.*?)\)", BUMP, re.S).group(1))
check("the two prefix lists match", shell_prefixes == py_prefixes, (shell_prefixes, py_prefixes))
check("bump waits for validation", WF["jobs"]["bump"]["needs"] == "validate-inputs")
check("validation holds no permissions", WF["jobs"]["validate-inputs"]["permissions"] == {})
check("validation has no environment or checkout",
      "environment" not in WF["jobs"]["validate-inputs"] and "uses" not in str(WF["jobs"]["validate-inputs"]["steps"]))
check("no replacement string carries the tag", "subn(r'" not in BUMP)
# A check that cannot fail is no check.
bump_job = WF["jobs"]["bump"]
validate_step = WF["jobs"]["validate-inputs"]["steps"][0]
check("validation cannot be let through", "continue-on-error" not in validate_step and "|| true" not in VALIDATE)
check("bump has no condition that skips validation", "if" not in bump_job and "continue-on-error" not in bump_job)
check("the bump step cannot be let through",
      "continue-on-error" not in [s for s in bump_job["steps"] if s.get("name") == "Bump image tags"][0])
check("a gate refusal stops the bump", re.search(r"if _gate\.returncode != 0:\n\s+print\([^\n]*\n\s+sys\.exit\(6\)", BUMP) is not None)


# Mutants: remove each layer, the matching behaviour must go.
def drop(src, start, n=3):
    lines = src.split("\n")
    i = next(k for k, l in enumerate(lines) if start in l)
    return "\n".join(lines[:i] + lines[i + n:])


NO_TAG = drop(BUMP, "if not re.fullmatch(r'[A-Za-z0-9_]")
NO_IMAGE = drop(BUMP, "if not re.fullmatch(r'ghcr")
NO_EDIT_CHECK = BUMP.replace("elif not only_tags_changed(content, out):", "elif False:")
NO_LAMBDA_TAG = NO_TAG.replace("lambda m: m.group(1) + ' \"' + new_tag + '\"'", "r'\\1 \"' + new_tag + '\"'")
assert NO_EDIT_CHECK != BUMP and NO_LAMBDA_TAG != NO_TAG
rc, changed, contents, _ = bump(tag=INJECT, script=NO_TAG)
check("mutant caught: tag check off, the edit check still refuses", rc == 7 and not changed, rc)
rc, changed, contents, _ = bump(tag=INJECT, script=NO_TAG.replace("elif not only_tags_changed(content, out):", "elif False:"))
check("mutant caught: both off, the injection lands (the checks are what stop it)",
      rc == 0 and "fullnameOverride: PROBE" in contents.get(OTHER, ""), rc)
rc, changed, _, _ = bump(tag="1.0\\1", script=NO_LAMBDA_TAG)
check("mutant caught: a replacement string reads a group reference", rc != 0, rc)
rc, changed, _, _ = bump(image="ghcr.io/other/absent", script=NO_IMAGE)
check("mutant caught: image check off, this image reaches the file scan", rc == 3, rc)
rc, changed, _, _ = bump(path="platform-gitops/services/labs/link/values.yaml", image="ghcr.io/mctlhq/mctl-agents",
                         tag="1.999.0", prepare=link,
                         script=BUMP.replace("if os.path.relpath(os.path.realpath(path)) != normalized:", "if False:"))
check("mutant caught: symlink check off, the worker file is reached", rc != 4, rc)
# An edit that adds a key without a newline-bearing tag.
EVIL = BUMP.replace("n = n1 + n2 + n3 + n4\n", "out = out + 'extra: 1\\n'\n    n = n1 + n2 + n3 + n4\n", 1)
assert EVIL != BUMP
rc, changed, _, _ = bump(script=EVIL)
check("the edit check catches an added line from any cause", rc == 7 and not changed, rc)
SWAP = BUMP.replace("n = n1 + n2 + n3 + n4\n", "out = out.replace('A: b', 'A: c')\n    n = n1 + n2 + n3 + n4\n", 1)
assert SWAP != BUMP
rc, changed, _, _ = bump(script=SWAP)
check("the edit check catches a changed unrelated value", rc == 7 and not changed, rc)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
