"""pip installs in workflows that run beside credentials are hash-pinned (mctlhq/mctl-gitops#1033).

Static checks: each listed workflow installs only through `--require-hashes -r` on the
shared requirements file, and that file pins every requirement with ==, with well
formed sha256 hashes on every entry.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ("gitops-bump.yaml", "release-deploy.yaml", "release-gate-watch.yml")
REQ = "scripts/requirements-ci-hashed.txt"
PIP = re.compile(r"pip3?\s+install\b[^\n]*")
GOOD = re.compile(r"--require-hashes\s+-r\s+" + re.escape(REQ) + r"(\s|$)")
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:500]}")


def unhashed_installs(text):
    return [m for m in PIP.findall(text) if not GOOD.search(m)]


def bad_requirements(text):
    problems = []
    entries = re.sub(r"\\\n", " ", "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#")))
    lines = [l.strip() for l in entries.split("\n") if l.strip()]
    if not lines:
        return ["no requirements"]
    for l in lines:
        if not re.match(r"^[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9.]*\s", l):
            problems.append(f"not pinned with ==: {l[:60]}")
        hashes = re.findall(r"--hash=sha256:([^\s]+)", l)
        if not hashes or any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes):
            problems.append(f"missing or malformed hash: {l[:60]}")
    return problems


# Detector self-test.
check("flags a bare install", len(unhashed_installs("run: python3 -m pip install --quiet pyyaml")) == 1)
check("flags a version-only pin", len(unhashed_installs("pip install pyyaml==6.0.2")) == 1)
check("accepts the hashed form",
      unhashed_installs(f"python3 -m pip install --quiet --require-hashes -r {REQ}") == [])
check("requirements check flags a missing hash", bad_requirements("pyyaml==6.0.2\n") != [])
check("requirements check flags a short hash", bad_requirements("pyyaml==6.0.2 --hash=sha256:abc\n") != [])
check("requirements check flags an unpinned entry", bad_requirements("pyyaml --hash=sha256:" + "a" * 64 + "\n") != [])

for w in WORKFLOWS:
    p = ROOT / ".github/workflows" / w
    try:
        text = p.read_text()
    except OSError as e:
        check(f"{w} readable", False, e)
        continue
    installs = PIP.findall(text)
    check(f"{w} has a pip install to check", len(installs) > 0)
    check(f"{w} installs only with hashes", unhashed_installs(text) == [], unhashed_installs(text))

try:
    req = (ROOT / REQ).read_text()
    check("requirements file is fully pinned and hashed", bad_requirements(req) == [], bad_requirements(req))
except OSError as e:
    check("requirements file readable", False, e)

if failures:
    print("\n".join(failures))
    sys.exit(1)
