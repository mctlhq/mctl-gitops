"""Run tpl-git-commit's env_vars loop against fixtures, with real yq.

validate-yq-interpolation.py proves statically that no yq expression carries a
shell variable. That is necessary but not sufficient: it says nothing about
whether the shape that replaced the interpolation actually holds up. This
extracts the loop verbatim from the template and feeds it the two payload
classes that worked before the fix (gitops#997):

  * a key that closes the expression PATH — `.env.${key}` with a key of
    `x | .image.tag` rewrote the image a service runs and wiped `.env` with
    it. The key carries no `=`, so it survives the loop's own `IFS='='`
    split: this is reachable through env_vars as the loop actually reads it,
    not only against a bare yq call;
  * a value that closes the string literal — `a" | .image.tag = "pwned`.

strenv() covers the value; it does NOT substitute in a path, which is why the
key is both shape-checked and written through the `.env[strenv(KEY)]`
subscript. Both halves are exercised here.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import pathlib

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml")
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "commit-service"][0]["script"]["source"]

# The guard helper and the env_vars loop body, taken from the template rather
# than restated here — a copy would keep passing after the template changed.
def dedent(block, width):
    return "\n".join(ln[width:] if ln.startswith(" " * width) else ln
                     for ln in block.split("\n"))


m = re.search(r"^(reject_multiline\(\) \{\n.*?\n\})$", SOURCE, re.S | re.M)
assert m, "could not extract reject_multiline() from the template"
HELPER = m.group(1)

m = re.search(r"while IFS='=' read -r key rest; do\n(.*?)\n *done << 'ENVEOF'",
              SOURCE, re.S)
assert m, "could not extract the env_vars loop from the template"
BODY = dedent(m.group(1), 6)

VALUES = 'image:\n  tag: "1.0.0"\nenv:\n  EXISTING: "keep"\n'

SCRIPT = """set -e
DIR="$PWD"
%s
while IFS='=' read -r key rest; do
%s
done <<'ENVEOF'
%s
ENVEOF
"""


def run(payload):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "values.yaml").write_text(VALUES)
        proc = subprocess.run(
            ["sh", "-c", SCRIPT % (HELPER, BODY, payload)],
            cwd=tmp, capture_output=True, text=True,
        )
        tag = subprocess.run(
            ["yq", ".image.tag", "values.yaml"],
            cwd=tmp, capture_output=True, text=True).stdout.strip()
        env = subprocess.run(
            ["yq", "-o=json", ".env", "values.yaml"],
            cwd=tmp, capture_output=True, text=True).stdout.strip()
        return proc, tag, env


failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


if not shutil.which("yq"):
    print("yq not on PATH — this test needs the real binary", file=sys.stderr)
    sys.exit(2)

# 1. The ordinary case still works, or the rest proves nothing.
proc, tag, env = run("FOO=bar")
check("a normal KEY=value is written", proc.returncode == 0 and '"FOO": "bar"' in env,
      f"rc={proc.returncode} env={env} err={proc.stderr}")
check("the ordinary case leaves image.tag alone", tag == "1.0.0", tag)

# 2. Key in PATH position — the payload strenv() cannot defend against.
#    Verified against the pre-fix shape: `yq eval -i ".env.${key} = ..."` with
#    this key sets .image.tag to "pwned" and leaves .env null.
proc, tag, env = run("x | .image.tag=pwned")
check("an injecting key is rejected", proc.returncode != 0, f"rc={proc.returncode}")
check("an injecting key does not rewrite image.tag", tag == "1.0.0", tag)
check("an injecting key does not wipe .env", '"EXISTING": "keep"' in env, env)

# 3. Value in string-literal position.
proc, tag, env = run('OK=a" | .image.tag = "pwned2')
check("an injecting value does not rewrite image.tag", tag == "1.0.0", tag)
check("an injecting value is stored literally",
      'pwned2' in env and tag == "1.0.0", env)

# 4. An anchored `grep -E '^...$'` matches per line, so a newline smuggles a
#    second line past a check that looks correct (the bug fixed in 397fa765).
#    Here the loop reads line by line, so the guard's job is to ensure neither
#    line can inject regardless.
proc, tag, env = run("GOOD=1\nx | .image.tag=pwned3")
check("a multi-line payload does not rewrite image.tag", tag == "1.0.0", tag)

# 5. Keys that are legal env var names but awkward in a path.
proc, tag, env = run("_UNDERSCORE=1\nA1=2")
check("underscore and digit-bearing names are accepted",
      proc.returncode == 0 and '"_UNDERSCORE": "1"' in env and '"A1": "2"' in env,
      f"rc={proc.returncode} env={env} err={proc.stderr}")

# 6. A dotted key would silently create a nested map under `.env.${key}`;
#    the subscript form stores it flat, and the shape check rejects it first.
proc, tag, env = run("a.b=1")
check("a dotted key is rejected rather than nesting", proc.returncode != 0,
      f"rc={proc.returncode} env={env}")

# 7. The two layers are independent, and each needs its own evidence.
#    Nothing that passes the key shape-check above can inject, so the cases so
#    far only ever exercise the regex — reverting the yq call to
#    `.env.${key} = "${value}"` leaves them all green (that regression is what
#    scripts/validate-yq-interpolation.py catches instead). So exercise the
#    subscript form directly, with a hostile key the regex would have stopped:
#    the write itself must be safe, not merely unreachable.
YQ_LINE = "yq eval -i '.env[strenv(KEY)] = strenv(VALUE)' \"$DIR/values.yaml\""
SUBSCRIPT = YQ_LINE.split("'")[1]
# There are three env_vars loops (onboard, deploy, update-config). Assert on
# the ABSENCE of the vulnerable shape rather than the presence of the safe one:
# "some site uses strenv" stays true after one of the three regresses.
CODE = "\n".join(ln for ln in SOURCE.splitlines()
                  if not ln.lstrip().startswith("#"))
check("no env write interpolates the key into the path",
      ".env.${key}" not in CODE, "a loop still writes .env.${key}")
check("every env write uses the subscript form",
      SOURCE.count(SUBSCRIPT) == SOURCE.count("read -r key rest") - 3,
      f"{SOURCE.count(SUBSCRIPT)} subscript writes for "
      f"{SOURCE.count('read -r key rest')} key loops")

with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    (tmp / "values.yaml").write_text(VALUES)
    proc = subprocess.run(
        ["sh", "-c", 'set -e\nDIR="$PWD"\nexport KEY VALUE\n' + YQ_LINE],
        cwd=tmp, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "KEY": "x | .image.tag", "VALUE": "pwned4"},
    )
    tag = subprocess.run(["yq", ".image.tag", "values.yaml"], cwd=tmp,
                         capture_output=True, text=True).stdout.strip()
    env = subprocess.run(["yq", "-o=json", ".env", "values.yaml"], cwd=tmp,
                         capture_output=True, text=True).stdout.strip()
check("the subscript form itself resists a hostile key", tag == "1.0.0",
      f"tag={tag} env={env} err={proc.stderr}")
check("the hostile key is stored as a literal key", '"x | .image.tag": "pwned4"' in env, env)

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
