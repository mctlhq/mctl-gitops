"""Run the shepherd commit-and-push staging block against a real git repo.

The block decides which pathspecs reach `git add`, and a `git add` pathspec
that matches nothing exits 128 — under `set -e` that kills commit-and-push,
which is the only step that writes agents-state back to git. So the failure
mode is not "the deletion was skipped", it is "the shepherd's entire durable
write was lost". This is the second pathspec bug in this script after the
`:(literal)` P1 on gitops#1046, and both reproduce in a scratch repo in a few
lines, so the script's own text is extracted from the template and exercised
here rather than restated.

The case that failed (agy P2 on gitops#1295): `git rm` stages a deletion, and
`git status --porcelain` keeps reporting it (`D `) while the path is already
gone from both the index and the worktree. A guard that only asks "does this
pathspec have changes?" therefore says yes and hands `git add` a pathspec
matching nothing. Trigger: removing the last remaining
`adopted-prs/*/.prref.yaml` in the clone — PR unadopted, proposal rejected or
closed, or cleanup — while a `.status.yaml` change is also present.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml")
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "commit-and-push"][0]["script"]["source"]


def dedent(block, width):
    return "\n".join(ln[width:] if ln.startswith(" " * width) else ln
                     for ln in block.split("\n"))


# Both halves come from the template. A copy restated here would keep passing
# after the template changed, which is exactly the regression this guards.
m = re.search(r"^( *PATH_STATUS=.*?EXCL_ADOPTED=[^\n]*)$", SOURCE, re.S | re.M)
assert m, "could not extract the pathspec definitions from the template"
DEFS = dedent(m.group(1), 10)

m = re.search(r"^( *needs_add\(\) \{\n.*?git add -- \"\$@\"\n *fi)$",
              SOURCE, re.S | re.M)
assert m, "could not extract the staging block from the template"
STAGING = dedent(m.group(1), 10)

STATUS = "platform-gitops/agents-state/mctl-agents/.status.yaml"
PRREF = "platform-gitops/agents-state/mctl-agents/adopted-prs/pr-1/.prref.yaml"

SCRIPT = """set -e
%s
%s
%s
git diff --cached --name-only
"""


def run(setup, seed=(STATUS, PRREF)):
    """Seed a repo with `seed` committed, apply `setup`, then stage."""
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"],
                       cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        for rel in seed:
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("seeded: true\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp, check=True)
        return subprocess.run(["sh", "-c", SCRIPT % (DEFS, setup, STAGING)],
                              cwd=tmp, capture_output=True, text=True)


FAILURES = []


def check(name, cond, proc):
    if cond:
        print("ok   - %s" % name)
        return
    FAILURES.append(name)
    print("FAIL - %s\n  rc=%d\n  stdout=%r\n  stderr=%r"
          % (name, proc.returncode, proc.stdout, proc.stderr))


# The regression. `git rm` removes the only adopted-prs record; a .status.yaml
# edit rides along, so the step does have something to commit and cannot take
# the "nothing to commit" exit.
proc = run("""git rm -q --ignore-unmatch -- ":(literal)%s"
printf 'changed: true\\n' > %s""" % (PRREF, STATUS))
check("a staged deletion of the last adopted-prs record does not abort staging",
      proc.returncode == 0, proc)
check("that deletion is still committed",
      PRREF in proc.stdout.split(), proc)
check("the .status.yaml change beside it is still staged",
      STATUS in proc.stdout.split(), proc)
check("no pathspec reached git add unmatched",
      "did not match any files" not in proc.stderr, proc)

# A deletion with nothing else changed: the block must survive it too, and the
# deletion `git rm` already staged must remain staged.
proc = run("""git rm -q --ignore-unmatch -- ":(literal)%s\"""" % PRREF)
check("a deletion with no other change does not abort staging",
      proc.returncode == 0, proc)
check("the lone deletion is still committed",
      PRREF in proc.stdout.split(), proc)

# The ordinary paths must keep working — the guard has to skip staged
# deletions without also skipping real work.
proc = run("printf 'changed: true\\n' > %s" % STATUS)
check("a .status.yaml flip alone still stages",
      proc.returncode == 0 and STATUS in proc.stdout.split(), proc)

proc = run("""mkdir -p platform-gitops/agents-state/mctl-gitops/adopted-prs/pr-9
printf 'pr: 9\\n' > platform-gitops/agents-state/mctl-gitops/adopted-prs/pr-9/.prref.yaml""",
           seed=(STATUS,))
check("a new adopted-prs record stages when none existed before",
      proc.returncode == 0
      and "platform-gitops/agents-state/mctl-gitops/adopted-prs/pr-9/.prref.yaml"
      in proc.stdout.split(), proc)

# A worktree deletion git has NOT been told about is real work for `git add`,
# not an already-staged one, so it must not be filtered out.
proc = run("rm -f %s" % PRREF)
check("an unstaged worktree deletion is still staged",
      proc.returncode == 0 and PRREF in proc.stdout.split(), proc)

# The exclude pathspecs are now derived rather than restated; pin what they
# must expand to, since nothing else in the script reads them back.
proc = subprocess.run(["sh", "-c", "set -e\n%s\nprintf '%%s\\n%%s\\n' "
                       "\"$EXCL_STATUS\" \"$EXCL_ADOPTED\"" % DEFS],
                      capture_output=True, text=True)
check("the derived exclude pathspecs match the literals they replaced",
      proc.stdout.split("\n")[:2] == [
          ":(exclude,glob)platform-gitops/agents-state/**/.status.yaml",
          ":(exclude,glob)platform-gitops/agents-state/*/adopted-prs/*/**"],
      proc)

if FAILURES:
    print("\n%d check(s) failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nall checks passed")
