#!/usr/bin/env python3
"""Proof both ways for scripts/check-vault-policy-capabilities.py (#1033).

Green on the committed files and on a converged fixture, red on each
deliberate mutation, and UNKNOWN (2) for anything unreadable, never a pass.
Run from the repository root.
"""
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

spec = importlib.util.spec_from_file_location(
    "chk", pathlib.Path("scripts/check-vault-policy-capabilities.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


REAL_CFG = pathlib.Path("scripts/vault-policy-expectations.json")
CFG = json.loads(REAL_CFG.read_text())
BASE = pathlib.Path(CFG["base_dir"])

# Converged fixture for a prospective narrowly scoped read policy plus a
# deny on the new prefix; exercises the same rules on text not yet committed.
FIX_ESO = '''
path "secret/data/platform/*" { capabilities = ["read"] }
path "secret/metadata/platform/*" { capabilities = ["read", "list"] }
path "secret/data/writers/*" { capabilities = ["deny"] }
path "secret/metadata/writers/*" { capabilities = ["deny"] }
'''
FIX_WRITER = '''
path "secret/data/writers/gitops/*" { capabilities = ["read"] }
'''
FIX_CFG = {
    "base_dir": "p",
    "identities": {
        "shared": {"policies": ["shared.hcl"]},
        "scoped": {"policies": ["scoped.hcl"]},
    },
    "expectations": [
        {"identity": "shared", "path": "secret/data/writers/gitops/k", "effective": ["deny"]},
        {"identity": "shared", "path": "secret/data/platform/x", "effective": ["read"]},
        {"identity": "scoped", "path": "secret/data/writers/gitops/k", "effective": ["read"]},
        {"identity": "scoped", "path": "secret/data/platform/x", "effective": []},
    ],
}


def fixture(files, cfg=FIX_CFG):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "p").mkdir()
    for n, t in files.items():
        (d / "p" / n).write_text(t)
    (d / "cfg.json").write_text(json.dumps(cfg))
    return d


def run(d):
    try:
        return C.run(d, d / "cfg.json")[0]
    except C.Unknown:
        return C.UNKNOWN


def repo_copy(mutate=None, drop=None):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / BASE).mkdir(parents=True)
    for p in (pathlib.Path(".") / BASE).glob("*.hcl"):
        shutil.copy(p, d / BASE / p.name)
    if mutate:
        f, old, new = mutate
        t = (d / BASE / f).read_text()
        assert old in t, "mutation target missing"
        (d / BASE / f).write_text(t.replace(old, new))
    if drop:
        (d / BASE / drop).unlink()
    return d


ESO = "vault-policy-external-secrets-read.hcl"
ARGO = "vault-policy-argo-workflow-teams-rw.hcl"

# Converged inputs
check("committed policy files match the table", C.run(".", REAL_CFG)[0] == C.OK)
check("converged fixture is clean", run(fixture({"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER})) == C.OK)

# Mutations -> finding (1)
check("dropping a deny line is detected",
      run(fixture({"shared.hcl": FIX_ESO.replace('path "secret/data/writers/*" { capabilities = ["deny"] }', ""),
                   "scoped.hcl": FIX_WRITER})) == C.FINDING)
check("widening the scoped read to a broader prefix is detected",
      run(fixture({"shared.hcl": FIX_ESO,
                   "scoped.hcl": FIX_WRITER.replace("writers/gitops/*", "platform/*")})) == C.FINDING)
check("narrowing the scoped read away from its path is detected",
      run(fixture({"shared.hcl": FIX_ESO,
                   "scoped.hcl": FIX_WRITER.replace("writers/gitops/*", "writers/other/*")})) == C.FINDING)
check("the longest matching glob wins over a shorter one",
      C.effective([("secret/data/a/*", {"deny"}), ("secret/data/a/b/*", {"read"})], "secret/data/a/b/c") == ["read"])
check("an exact path beats a glob",
      C.effective([("secret/data/a/*", {"deny"}), ("secret/data/a/b", {"read"})], "secret/data/a/b") == ["read"])
check("same-pattern capabilities merge and deny wins across policies",
      C.effective([("secret/data/a/*", {"read"}), ("secret/data/a/*", {"deny"})], "secret/data/a/x") == ["deny"])
for label, mut in (
    ("removing the committed narrow deny", (ESO, 'path "secret/data/platform/github-app-agents*" {\n  capabilities = ["deny"]', 'path "secret/data/platform/github-app-agents*" {\n  capabilities = ["read"]')),
    ("granting the shared identity a tenant prefix", (ESO, 'path "secret/data/platform/*" {\n  capabilities = ["read"]', 'path "secret/data/platform/*" {\n  capabilities = ["read"]\n}\npath "secret/data/teams/*" {\n  capabilities = ["read"]')),
    ("dropping write from the workflow policy", (ARGO, '"create", "read", "update", "delete", "list"]\n}\n\npath "secret/metadata/teams', '"read"]\n}\n\npath "secret/metadata/teams')),
):
    check(f"committed-file mutation detected: {label}", C.run(repo_copy(mutate=mut), REAL_CFG)[0] == C.FINDING)

# Could not observe -> UNKNOWN (2), outranking a finding
check("absent policy file is UNKNOWN, not clean", C.run(repo_copy(drop=ESO), REAL_CFG)[0] == C.UNKNOWN)
check("absent policy file outranks a finding elsewhere",
      C.run(repo_copy(drop=ESO, mutate=(ARGO, '"create", "read", "update", "delete", "list"]\n}\n\npath "secret/metadata/teams', '"read"]\n}\n\npath "secret/metadata/teams')), REAL_CFG)[0] == C.UNKNOWN)
check("empty policy file is UNKNOWN", run(fixture({"shared.hcl": "# nothing\n", "scoped.hcl": FIX_WRITER})) == C.UNKNOWN)
check("garbage policy file is UNKNOWN", run(fixture({"shared.hcl": "not hcl {{", "scoped.hcl": FIX_WRITER})) == C.UNKNOWN)
check("unsupported attribute is UNKNOWN",
      run(fixture({"shared.hcl": 'path "secret/data/x/*" {\n capabilities = ["read"]\n allowed_parameters = {"a" = []}\n}\n', "scoped.hcl": FIX_WRITER})) == C.UNKNOWN)
check("unknown capability name is UNKNOWN",
      run(fixture({"shared.hcl": 'path "secret/data/x/*" { capabilities = ["reed"] }', "scoped.hcl": FIX_WRITER})) == C.UNKNOWN)
check("templated path is UNKNOWN",
      run(fixture({"shared.hcl": 'path "secret/data/{{x}}/*" { capabilities = ["read"] }', "scoped.hcl": FIX_WRITER})) == C.UNKNOWN)
check("truncated file (missing brace) is UNKNOWN",
      run(fixture({"shared.hcl": 'path "secret/data/x/*" { capabilities = ["read"]', "scoped.hcl": FIX_WRITER})) == C.UNKNOWN)
check("commented-out rule is not counted",
      C.parse_policy('# path "secret/data/a/*" { capabilities = ["deny"] }\npath "secret/data/b/*" { capabilities = ["read"] }', "t") == [("secret/data/b/*", {"read"})])
check("missing config is UNKNOWN", C.main(["--config", "/nonexistent/cfg.json"]) == C.UNKNOWN)
bad = fixture({"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER}, cfg={"base_dir": "p", "identities": {}, "expectations": []})
check("empty config is UNKNOWN", run(bad) == C.UNKNOWN)
bad2 = json.loads(json.dumps(FIX_CFG)); bad2["expectations"][0]["identity"] = "nobody"
check("expectation naming an unknown identity is UNKNOWN", run(fixture({"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER}, bad2)) == C.UNKNOWN)

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nall checks passed")
