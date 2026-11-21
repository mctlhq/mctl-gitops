"""creator_user_id is spliced UNQUOTED into the tenant values.yaml members block
(`- userId: <value>`), so its grammar must also hold at the first character:
`@` and `-` are YAML indicators at the start of a plain scalar and made the
tenant document unparseable (gitops#999). The guard block is extracted from the
template, not restated.
"""
import pathlib
import re
import subprocess
import sys

import yaml

TPL = pathlib.Path("platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml")
doc = yaml.safe_load(TPL.read_text())
COMMIT = [t for t in doc["spec"]["templates"] if t["name"] == "commit-tenant-to-git"][0]["script"]["source"]
m = re.search(r"^(# creator_user_id is the most exposed.*?)^# creator_principal_id is spliced",
              COMMIT, re.S | re.M)
assert m, "could not extract the creator_user_id guard"
SCRIPT = 'set -e\nCREATOR_USER_ID="$V"\n' + m.group(1) + 'echo accepted\n'

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def run(value):
    return subprocess.run(["sh", "-c", SCRIPT], env={"V": value, "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)


for good in ("octocat", "a.b-c_d", "_x", "9lives", "user@example", ""):
    p = run(good)
    check(f"accepted: {good!r}", p.returncode == 0 and "accepted" in p.stdout, p.stderr)
for bad in ("@foo", "-foo", ".foo", "a b", "a\nb", 'a"b', "$(id)"):
    p = run(bad)
    check(f"rejected: {bad!r}", p.returncode != 0 and "accepted" not in p.stdout, p.stdout)

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
