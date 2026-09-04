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
from shlex import quote as shlex_quote

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

# --- config_patch ----------------------------------------------------------
# config_patch is the one parameter that IS an expression, so it has no
# strenv() shape and is defended by an allowlist instead. Extracted and run
# the same way, because a prefix-only check looks correct and is not: `|`
# chains independent top-level assignments, an idiom this very file uses.
m = re.search(r"^(validate_config_patch\(\) \{\n.*?\n\})$", SOURCE, re.S | re.M)
assert m, "could not extract validate_config_patch() from the template"
VALIDATOR = m.group(1)

# What mctl-api's openClawConfigPatch() actually emits — the only producer.
REAL_PATCH = ('.resources.requests.cpu = "500m" | .resources.requests.memory = "1Gi" | '
              '.resources.limits.cpu = "2" | .resources.limits.memory = "4Gi" | '
              '.env.NODE_OPTIONS = "--max-old-space-size=3072"')


def validate_patch(patch):
    script = f"set -e\n{HELPER}\n{VALIDATOR}\nvalidate_config_patch \"$1\"\n"
    return subprocess.run(["sh", "-c", script, "sh", patch],
                          capture_output=True, text=True)


check("the real OpenClaw resource-profile patch is accepted",
      validate_patch(REAL_PATCH).returncode == 0,
      validate_patch(REAL_PATCH).stdout + validate_patch(REAL_PATCH).stderr)

# The bypass a prefix-only check allows: it DOES start with an allowed root.
for hostile in (
    '.configMaps[0].x = "y" | .image.tag = "pwned"',
    '.resources.requests.cpu = "1" | .image.tag = "pwned"',
    '.resources.requests.cpu = "1" | .externalSecret.targetSecret = "theirs"',
    '.image.tag = "pwned"',
    '.env.A = strenv(HOME)',
    '.env.A = "$(id)"',
    # Re-rooting operators inside a segment that opens with an allowed
    # prefix. Both are proven below to rewrite .image.tag when unguarded.
    '.env.bypass = (.image.tag = "pwned")',
    '.env.a = "x", .image.tag = "pwned"',
):
    check(f"config_patch rejects: {hostile[:46]}",
          validate_patch(hostile).returncode != 0, hostile)

# A guard is only worth its lines if what it rejects would otherwise land.
# Run the two re-rooting payloads through real yq and confirm each one does
# rewrite .image.tag — otherwise the checks above pass vacuously.
for payload in ('.env.bypass = (.image.tag = "pwned")',
                '.env.a = "x", .image.tag = "pwned"'):
    with tempfile.TemporaryDirectory() as d:
        values = pathlib.Path(d) / "values.yaml"
        values.write_text('image:\n  tag: "1.0.0"\nenv:\n  EXISTING: "1"\n')
        subprocess.run(["yq", "eval", "-i", payload, str(values)], check=True)
        check(f"unguarded, this payload DOES rewrite .image.tag: {payload[:40]}",
              'pwned' in values.read_text(), values.read_text())

check("config_patch rejects a multi-line payload",
      validate_patch('.resources.requests.cpu = "1"\n.image.tag = "pwned"').returncode != 0)

# --- sed-bound parameters --------------------------------------------------
# Not every sink in this file is yq. PORT, DEFAULT_MODEL and the telegram
# owner ids are interpolated into a `sed` PROGRAM whose substitution delimiter
# is `|`, so a value carrying one closes the s/// and the remainder is read as
# further sed commands — `s|.*|x|g` rewrites the whole rendered manifest.
# `port` carries no Pattern in the operations registry (agy P1 on this PR).
GUARDS = re.search(r"^(# The values below reach a `sed` PROGRAM.*?"
                   r"Invalid telegram_owner_ids_json.*?\n)",
                   SOURCE, re.S | re.M)
assert GUARDS, "could not extract the sed-bound parameter guards"


def validate_sed_params(port="8080", model="", owner="", owners="[]"):
    script = (f"set -e\n{HELPER}\n"
              f'PORT={shlex_quote(port)}\nDEFAULT_MODEL={shlex_quote(model)}\n'
              f'TELEGRAM_OWNER_ID={shlex_quote(owner)}\n'
              f'TELEGRAM_OWNER_IDS_EFFECTIVE={shlex_quote(owners)}\n'
              + GUARDS.group(1))
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True)


check("a normal port is accepted", validate_sed_params().returncode == 0,
      validate_sed_params().stderr)
check("a port that closes the sed substitution is rejected",
      validate_sed_params(port='8080|g; s|.*|pwned|g').returncode != 0)
check("a non-numeric port is rejected", validate_sed_params(port="80a").returncode != 0)
check("a real default_model is accepted",
      validate_sed_params(model="openai-codex/gpt-5.4").returncode == 0,
      validate_sed_params(model="openai-codex/gpt-5.4").stderr)
check("a default_model carrying a sed delimiter is rejected",
      validate_sed_params(model="a|g; s|.*|pwned|g").returncode != 0)
check("a real owner id list is accepted",
      validate_sed_params(owners='["123","456"]').returncode == 0,
      validate_sed_params(owners='["123","456"]').stderr)
check("an owner id list carrying a sed delimiter is rejected",
      validate_sed_params(owners='["1"]|g; s|.*|pwned|g').returncode != 0)

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
