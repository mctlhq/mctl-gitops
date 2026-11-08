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
import subprocess
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

def mutant(src_old, src_new):
    """Load the checker with one source line deliberately changed."""
    text = pathlib.Path("scripts/check-vault-policy-capabilities.py").read_text()
    assert src_old in text, "mutation target missing"
    m = importlib.util.module_from_spec(importlib.util.spec_from_file_location("mut", "scripts/x.py"))
    exec(compile(text.replace(src_old, src_new), "mutant", "exec"), m.__dict__)
    return m


GLOB_OLD = "globs.setdefault(pattern, set()).update(caps)"
EXACT_OLD = "exact.setdefault(pattern, set()).update(caps)"
GP, EP = "secret/data/a/*", "secret/data/a/b"
MERGE_CASES = [  # (rules, request path, expected under merge)
    ("glob deny then read", [(GP, {"deny"}), (GP, {"read"})], "secret/data/a/x", ["deny"]),
    ("glob read then deny", [(GP, {"read"}), (GP, {"deny"})], "secret/data/a/x", ["deny"]),
    ("glob read then list", [(GP, {"read"}), (GP, {"list"})], "secret/data/a/x", ["list", "read"]),
    ("glob list then read", [(GP, {"list"}), (GP, {"read"})], "secret/data/a/x", ["list", "read"]),
    ("exact deny then read", [(EP, {"deny"}), (EP, {"read"})], EP, ["deny"]),
    ("exact read then deny", [(EP, {"read"}), (EP, {"deny"})], EP, ["deny"]),
    ("exact read then list", [(EP, {"read"}), (EP, {"list"})], EP, ["list", "read"]),
    ("exact list then read", [(EP, {"list"}), (EP, {"read"})], EP, ["list", "read"]),
]
for label, rules, req, want in MERGE_CASES:
    check(f"same-pattern merge: {label}", C.effective(rules, req) == want)

# Replace merge with last-writer-wins / first-writer-wins: every kind of rule
# (glob and exact) must turn at least the discriminating cases red, and the
# deny-then-read order must be red under last-writer-wins, the reverse order
# under first-writer-wins.
for kind, old, last, first in (
    ("glob", GLOB_OLD, "globs[pattern] = set(caps)", "globs.setdefault(pattern, set(caps))"),
    ("exact", EXACT_OLD, "exact[pattern] = set(caps)", "exact.setdefault(pattern, set(caps))"),
):
    for mname, repl in (("overwrite (last wins)", last), ("keep first", first)):
        M = mutant(old, repl)
        red = {lab for lab, rules, req, want in MERGE_CASES
               if kind in lab and M.effective(rules, req) != want}
        check(f"mutation {kind} {mname} turns cases red", len(red) >= 3, str(sorted(red)))
        for lab in (f"{kind} read then list", f"{kind} list then read"):
            check(f"mutation {kind} {mname}: union case '{lab}' red", lab in red)
    check(f"mutation {kind} overwrite: deny-then-read order red",
          f"{kind} deny then read" in {lab for lab, r, q, w in MERGE_CASES
                                       if mutant(old, last).effective(r, q) != w})
    check(f"mutation {kind} keep-first: read-then-deny order red",
          f"{kind} read then deny" in {lab for lab, r, q, w in MERGE_CASES
                                       if mutant(old, first).effective(r, q) != w})
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

# Present but not valid UTF-8 -> UNKNOWN (2), never a traceback, never 1
def raw_fixture(name, data, cfg=FIX_CFG, other=None):
    d = fixture({"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER}, cfg)
    (d / "p" / name).write_bytes(data)
    return d


BAD_UTF8 = b'path "secret/data/x/*" { capabilities = ["read"] }\n# \xff\xfe\n'
d = raw_fixture("shared.hcl", BAD_UTF8)
check("non-UTF-8 policy file is UNKNOWN (run)", run(d) == C.UNKNOWN)
check("non-UTF-8 policy file exits 2 via main", C.main(["--root", str(d), "--config", str(d / "cfg.json")]) == 2)
check("non-UTF-8 policy file exits 2 as a process",
      subprocess.run([sys.executable, "scripts/check-vault-policy-capabilities.py", "--root", str(d),
                      "--config", str(d / "cfg.json")], capture_output=True).returncode == 2)
d = raw_fixture("shared.hcl", b"\xff\xfe\x00")
check("non-UTF-8 binary policy file exits 2", C.main(["--root", str(d), "--config", str(d / "cfg.json")]) == 2)
d = fixture({"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER})
(d / "cfg.json").write_bytes(b"\xff\xfe{")
check("non-UTF-8 config exits 2", C.main(["--root", str(d), "--config", str(d / "cfg.json")]) == 2)
d = fixture({"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER}, cfg={"base_dir": "p", "identities": FIX_CFG["identities"],
            "expectations": [dict(FIX_CFG["expectations"][0], effective=["read"])] + FIX_CFG["expectations"][1:]})
check("actual mismatch exits 1 via main", C.main(["--root", str(d), "--config", str(d / "cfg.json")]) == 1)
(d / "p" / "scoped.hcl").write_bytes(BAD_UTF8)
check("non-UTF-8 file outranks a mismatch (exit 2, not 1)",
      C.main(["--root", str(d), "--config", str(d / "cfg.json")]) == 2)
# Mutation: catch only OSError -> non-UTF-8 must stop being UNKNOWN
src_old = "except (OSError, ValueError) as e:\n                # ValueError includes"
M = mutant(src_old, "except OSError as e:\n                # ValueError includes")
try:
    r = M.run(raw_fixture("shared.hcl", BAD_UTF8), raw_fixture("shared.hcl", BAD_UTF8) / "cfg.json")[0]
except Exception:
    r = "traceback"
check("mutation: catching only OSError turns the non-UTF-8 case red", r != C.UNKNOWN, str(r))

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nall checks passed")
