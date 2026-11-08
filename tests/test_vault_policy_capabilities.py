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

class _MissingMutant:
    """Stand-in for a mutant whose target line is gone: every call returns a sentinel
    that equals nothing, and the missing target is reported as a FAIL by mutant()."""

    def __getattr__(self, name):
        return lambda *a, **k: "MUTATION-TARGET-MISSING"


def mutant(src_old, src_new, on_missing=None):
    """Load the checker with one source line deliberately changed. If the line is
    absent the mutation proves nothing: report a clean FAIL (no crash)."""
    text = pathlib.Path("scripts/check-vault-policy-capabilities.py").read_text()
    if src_old not in text:
        (on_missing or (lambda m: check(f"mutation target present: {m}", False, "line absent from the checker")))(
            src_old[:60].replace("\n", " "))
        return _MissingMutant()
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

# Malformed config shapes -> UNKNOWN (2) as a process exit, never a traceback (1).
def cfg_with(path_to_value):
    c = json.loads(json.dumps(FIX_CFG))
    for keys, val in path_to_value:
        node = c
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = val
    return c


FIXF = {"shared.hcl": FIX_ESO, "scoped.hcl": FIX_WRITER}
FIRST_ID = next(iter(FIX_CFG["identities"]))
SHAPES = {
    "identity is a list": cfg_with([(["expectations", 0, "identity"], ["shared"])]),
    "identity is a number": cfg_with([(["expectations", 0, "identity"], 7)]),
    "identity is an object": cfg_with([(["expectations", 0, "identity"], {"a": 1})]),
    "identity is empty": cfg_with([(["expectations", 0, "identity"], "")]),
    "effective element is a list": cfg_with([(["expectations", 0, "effective"], [["read"]])]),
    "effective element is an object": cfg_with([(["expectations", 0, "effective"], [{"a": 1}])]),
    "effective element is a number": cfg_with([(["expectations", 0, "effective"], [1])]),
    "effective is a string": cfg_with([(["expectations", 0, "effective"], "read")]),
    "effective is missing": cfg_with([(["expectations", 0, "effective"], None)]),
    "path is a list": cfg_with([(["expectations", 0, "path"], ["a"])]),
    "path is empty": cfg_with([(["expectations", 0, "path"], "")]),
    "expectation is a string": cfg_with([(["expectations", 0], "x")]),
    "expectation is a list": cfg_with([(["expectations", 0], [1, 2])]),
    "expectations is an object": cfg_with([(["expectations"], {"a": 1})]),
    "identities is a list": cfg_with([(["identities"], ["a"])]),
    "identity entry is a list": cfg_with([(["identities", FIRST_ID], ["x"])]),
    "identity entry is a string": cfg_with([(["identities", FIRST_ID], "x")]),
    "policies is a string": cfg_with([(["identities", FIRST_ID, "policies"], "shared.hcl")]),
    "policies element is a list": cfg_with([(["identities", FIRST_ID, "policies"], [["shared.hcl"]])]),
    "policies element is empty": cfg_with([(["identities", FIRST_ID, "policies"], [""])]),
    "base_dir is a list": cfg_with([(["base_dir"], ["p"])]),
    "base_dir is empty": cfg_with([(["base_dir"], "")]),
    "top level is a list": [1],
    "top level is a string": "x",
}
DEFENCE_IN_DEPTH = {"policies is a string", "policies element is empty", "base_dir is empty"}
M_NOVALID = mutant("    _validate_config(cfg)\n", "")
for label, cfg in SHAPES.items():
    d = fixture(FIXF, cfg)
    proc = subprocess.run([sys.executable, "scripts/check-vault-policy-capabilities.py", "--root", str(d),
                           "--config", str(d / "cfg.json")], capture_output=True, text=True)
    check(f"malformed config ({label}) exits 2 as a process, no traceback",
          proc.returncode == 2 and "Traceback" not in proc.stderr, (proc.returncode, proc.stderr[-200:]))
    try:
        r = M_NOVALID.run(d, d / "cfg.json")[0]
    except Exception:
        r = "traceback"
    if label in DEFENCE_IN_DEPTH:
        # Without the type validation these still end UNKNOWN, by accident (the
        # characters or the empty name are not readable files), so a mutant cannot
        # prove them; the exit-2 check above is the guard.
        continue
    check(f"mutation without type validation: ({label}) is no longer UNKNOWN", r != C.UNKNOWN, str(r))

# A mutant whose target line is absent is a clean FAIL, not an AssertionError crash.
seen = []
res = mutant("this line is not in the checker", "x", on_missing=seen.append)
check("mutant() reports an absent target line instead of crashing", len(seen) == 1)
check("mutant() returns an inert stand-in that cannot pass a red-expected check silently",
      res.effective([], "x") == "MUTATION-TARGET-MISSING")
_real_check, _collected = check, []
check = lambda name, cond, detail="": _collected.append((name, cond))  # noqa: E731
mutant("this line is not in the checker", "x")
check = _real_check
check("mutant() with the default reporter records a FAIL, not an exception",
      len(_collected) == 1 and _collected[0][1] is False)

# ---- Strict capability-list parsing: anything but quoted strings is UNKNOWN ----
def _caps_policy(body):
    return 'path "secret/data/x/*" { capabilities = %s }' % body


def _parse_state(body):
    try:
        C.parse_policy(_caps_policy(body), "t")
        return "parsed"
    except C.Unknown:
        return "unknown"


BAD_CAP_LISTS = {
    "bare word": '["read", list]',
    "missing comma": '["read" "deny"]',
    "doubled comma": '["read",,"list"]',
    "leading comma": '[,"read"]',
    "number element": '["read", 5]',
    "semicolon separator": '["read"; "list"]',
    "trailing junk after quoted": '["read" x]',
}
GOOD_CAP_LISTS = {
    "single": '["read"]',
    "two": '["read", "list"]',
    "trailing comma": '["read", "list",]',
    "multi-line": '[\n  "read",\n  "list",\n]',
    "no spaces": '["read","list"]',
}
M_LOOSE = mutant("        if not _CAP_LIST_RE.fullmatch(raw):\n", "        if False:\n")
for label, body in BAD_CAP_LISTS.items():
    check(f"capability list ({label}) is UNKNOWN", _parse_state(body) == "unknown")
    try:
        M_LOOSE.parse_policy(_caps_policy(body), "t")
        loose = "parsed"
    except Exception:
        loose = "unknown"
    check(f"mutation without the strict list check: ({label}) is silently accepted", loose == "parsed")
for label, body in GOOD_CAP_LISTS.items():
    check(f"capability list ({label}) still parses", _parse_state(body) == "parsed")
check("a trailing comma yields exactly the listed capabilities",
      C.parse_policy(_caps_policy('["read", "list",]'), "t") == [("secret/data/x/*", {"read", "list"})])
check("empty capability list stays UNKNOWN", _parse_state("[]") == "unknown")
d = fixture({"shared.hcl": _caps_policy('["read", list]'), "scoped.hcl": FIX_WRITER})
check("a bad capability list exits 2 via main, not a pass",
      C.main(["--root", str(d), "--config", str(d / "cfg.json")]) == 2)

# ---- Explicit UTF-8 decoding: independent of the process locale ----
LATIN1_ONLY = b'path "secret/data/x/*" { capabilities = ["read"] }\n# caf\xe9\n'  # valid Latin-1, invalid UTF-8
LATIN1_CFG = {"base_dir": "p", "identities": {"i": {"policies": ["a.hcl"]}},
              "expectations": [{"identity": "i", "path": "secret/data/x/y", "effective": ["read"]}]}
d = fixture({}, LATIN1_CFG)
(d / "p" / "a.hcl").write_bytes(LATIN1_ONLY)
check("Latin-1-only policy bytes are UNKNOWN (run)", run(d) == C.UNKNOWN)
d_cfg = fixture({"a.hcl": FIX_WRITER}, LATIN1_CFG)
(d_cfg / "cfg.json").write_bytes(json.dumps(LATIN1_CFG).replace('"i"', '"i\xe9"').encode("latin-1"))
check("Latin-1-only config bytes are UNKNOWN (run)", run(d_cfg) == C.UNKNOWN)
# Mutation: decode with Latin-1, as a Latin-1 locale default would -> the file is read as clean text.
M_LAT = mutant('p.read_text(encoding="utf-8", errors="strict")', 'p.read_text(encoding="latin-1")')
check("mutation decoding policy files as Latin-1 turns the Latin-1-only case green (red test)",
      M_LAT.run(d, d / "cfg.json")[0] == C.OK)
M_LATC = mutant('pathlib.Path(path).read_text(encoding="utf-8", errors="strict")',
                'pathlib.Path(path).read_text(encoding="latin-1")')
try:
    M_LATC.load_config(d_cfg / "cfg.json")
    _lat_cfg = "accepted"
except C.Unknown:
    _lat_cfg = "unknown"
check("mutation decoding the config as Latin-1 accepts the Latin-1-only config (red test)", _lat_cfg == "accepted")
# Real locale: run the script under a Latin-1 locale when the host has one.
_probe = subprocess.run([sys.executable, "-X", "utf8=0", "-c", "import locale;print(locale.getpreferredencoding(False))"],
                        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "en_US.ISO8859-1"})
if _probe.stdout.strip().upper().replace("-", "").replace("_", "") in ("ISO88591", "LATIN1"):
    pr = subprocess.run([sys.executable, "-X", "utf8=0", "scripts/check-vault-policy-capabilities.py", "--root", str(d),
                         "--config", str(d / "cfg.json")], capture_output=True, text=True,
                        env={"PATH": "/usr/bin:/bin", "LC_ALL": "en_US.ISO8859-1"})
    check("under a Latin-1 locale, Latin-1-only policy bytes still exit 2", pr.returncode == 2, pr.stdout + pr.stderr)
else:
    print("SKIP  Latin-1 locale not available on this host; covered by the Latin-1 decode mutation above")

# ---- Capabilities merge across several policy files under one identity ----
MF_CFG = {
    "base_dir": "p",
    "identities": {"multi": {"policies": ["one.hcl", "two.hcl"]},
                   "first-only": {"policies": ["one.hcl"]},
                   "second-only": {"policies": ["two.hcl"]}},
    "expectations": [
        {"identity": "multi", "path": "secret/data/m/a", "effective": ["list", "read"]},
        {"identity": "first-only", "path": "secret/data/m/a", "effective": ["read"]},
        {"identity": "second-only", "path": "secret/data/m/a", "effective": ["list"]},
        {"identity": "multi", "path": "secret/data/m/b/c", "effective": ["deny"]},
        {"identity": "multi", "path": "secret/data/n/x", "effective": ["update"]},
    ],
}
MF_ONE = 'path "secret/data/m/*" { capabilities = ["read"] }\npath "secret/data/m/b/*" { capabilities = ["read"] }\n'
MF_TWO = ('path "secret/data/m/*" { capabilities = ["list"] }\npath "secret/data/m/b/*" { capabilities = ["deny"] }\n'
          'path "secret/data/n/*" { capabilities = ["update"] }\n')
MF_FILES = {"one.hcl": MF_ONE, "two.hcl": MF_TWO}
check("capabilities merge across files listed under one identity", run(fixture(MF_FILES, MF_CFG)) == C.OK)
check("merge fixture turns red when the second file drops its deny",
      run(fixture({"one.hcl": MF_ONE, "two.hcl": MF_TWO.replace('["deny"]', '["read"]')}, MF_CFG)) == C.FINDING)
check("merge fixture turns red when the second file is not listed for the identity",
      run(fixture(MF_FILES, dict(MF_CFG, identities=dict(MF_CFG["identities"], multi={"policies": ["one.hcl"]})))) == C.FINDING)
# Mutation: keep only the last file's rules per identity (replace instead of accumulate).
M_REPLACE = mutant("rules.extend(parse_policy(text, str(p)))", "rules = list(parse_policy(text, str(p)))")
d = fixture(MF_FILES, MF_CFG)
check("mutation replacing rules per file turns the multi-file merge red", M_REPLACE.run(d, d / "cfg.json")[0] == C.FINDING)
# Mutation: keep only the first file.
M_FIRST = mutant("rules.extend(parse_policy(text, str(p)))", "rules = rules or list(parse_policy(text, str(p)))")
check("mutation keeping only the first file turns the multi-file merge red", M_FIRST.run(d, d / "cfg.json")[0] == C.FINDING)

# ---- The recorded-state note is present and the real table still holds ----
check("expectations file carries the recorded-state note",
      isinstance(CFG.get("note"), str) and "deployed today" in CFG["note"])
check("the note field does not change evaluation", C.run(".", REAL_CFG)[0] == C.OK)

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nall checks passed")
