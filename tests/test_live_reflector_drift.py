#!/usr/bin/env python3
"""Offline proof for scripts/check-live-reflector-drift.py (D2, the MANUAL live drift check).

D2 needs a metadata listing taken from the cluster, so it is not run in CI. This
test feeds it synthetic recorded input (tests/fixtures/reflector-live/*.txt plus
rows derived from them in memory) and shows it both ways:
  GREEN on the converged listing, RED on each deliberate mutation,
  UNKNOWN (rc 2) on unreadable / partial / malformed input and on any
  combination where an unobservable part could hide drift,
  and every rule load-bearing: reverted (REVERT test seam), its mutation stops being detected.
It also drives scripts/collect-reflector-metadata.sh against a stub kubectl to
pin its output shape and its failure behaviour. No cluster, no network.

Run: python3 tests/test_live_reflector_drift.py   (stdlib only; exit 0 all pass, 1 failure)
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-live-reflector-drift.py"
COLLECT = ROOT / "scripts" / "collect-reflector-metadata.sh"
FIX = ROOT / "tests" / "fixtures" / "reflector-live"
spec = importlib.util.spec_from_file_location("d2", SCRIPT)
d2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d2)

TMP = pathlib.Path(tempfile.mkdtemp(prefix="d2-proof-"))
failures, counter = [], [0]
CONVERGED = FIX / "converged.txt"
ANCHOR = ["--anchor", "database/postgres-credentials"]


def rows_of(path):
    return [l for l in pathlib.Path(path).read_text().splitlines() if l and not l.startswith("#")]


def listing(name, rows, trailer=True):
    p = TMP / (name + ".txt")
    p.write_text("\n".join(rows) + "\n" + (f"#END rows={len(rows)}\n" if trailer else ""))
    return p


def row(ns="", name="", allowed="", auto="", reflects="", autoref="", ver="", at=""):
    return "|".join([ns, name, allowed, auto, reflects, autoref, ver, at])


BASE = rows_of(CONVERGED)


def report(label, ok, detail=""):
    counter[0] += 1
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        failures.append(f"{label}: {detail}")


def run(args, revert=()):
    buf = io.StringIO()
    d2.REVERT.clear()
    d2.REVERT.update(revert)
    try:
        with contextlib.redirect_stdout(buf):
            rc = d2.main([str(a) for a in args])
    finally:
        d2.REVERT.clear()
    return rc, buf.getvalue()


def expect(label, args, want, revert=()):
    rc, out = run(args, revert)
    report(label, rc == want, f"rc={rc} want={want}\n{out[-500:]}")


def not_detected(label, args, detecting_rc, rule):
    rc, out = run(args, set(rule.split(",")))
    report(f"{label}  [revert {rule}]", rc != detecting_rc, f"still rc={rc} with {rule} reverted")


# ---------------------------------------------------------------- GREEN
print("== GREEN: converged recorded listing ==")
expect("G0 converged fixture, explicit anchor", [CONVERGED] + ANCHOR, 0)
expect("G1 converged fixture, default anchor", [CONVERGED], 0)
G2 = listing("g_unrelated", BASE + [row("database", "other-secret")])
expect("G2 unrelated Secret in the source namespace is GREEN", [G2], 0)
G3 = listing("g_nosrc", BASE + [row("yy", "foo")])
expect("G3 control: unregistered name in another namespace is GREEN", [G3], 0)
rc, out = run([CONVERGED])
report("G4 GREEN output states its scope (Secrets, metadata only, name-based copies)", rc == 0 and "scope: Secrets only" in out, out)
post_row5 = listing("g_post_row5", [r for r in BASE if not r.startswith("database|postgres-credentials")])
expect("G5 sources deleted: --no-anchor GREEN", [post_row5, "--no-anchor"], 0)

# ---------------------------------------------------------------- RED
print("== RED: deliberate mutations ==")
RED = {}
def red(name, label, rows, extra=()):
    p = listing("m_" + name, rows)
    RED[name] = (label, [p] + list(extra))
    expect(f"{name} {label}", RED[name][1], 1)

red("N1", "mirror survivor (all markers)", BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="1234", at="2026-11-09T10:00:00Z")], ANCHOR)
red("N2", "mirror with only reflects", BASE + [row("admins", "object-storage-credentials", reflects="database/object-storage-credentials")], ANCHOR)
red("N3", "mirror with reflects + auto-reflects", BASE + [row("tenant-x", "tenant-bootstrap-secret", reflects="database/tenant-bootstrap-secret", autoref="True")], ANCHOR)
red("N4", "new Secret allowed=true", BASE + [row("zz", "new-secret", allowed="true")], ANCHOR)
red("N5", "auto-enabled=true only", BASE + [row("zz", "new-secret", auto="true")], ANCHOR)
red("N6", "allowed=TRUE", BASE + [row("zz", "new-secret", allowed="TRUE")], ANCHOR)
red("N7", "allowed=' true'", BASE + [row("zz", "new-secret", allowed=" true")], ANCHOR)
red("N8", "a source flipped back to true/true", [r.replace("|false|false|", "|true|true|") if r.startswith("database|postgres-credentials") else r for r in BASE], ANCHOR)
red("N9", "mirror whose NAME is not a source (mirror rule alone)", BASE + [row("admins", "copy-of-x", reflects="database/postgres-credentials", autoref="True")], ANCHOR)
red("N10", "non-annotated copy of postgres-credentials", BASE + [row("zz", "postgres-credentials")])
red("N11", "non-annotated copy of object-storage-credentials", BASE + [row("tenant-x", "object-storage-credentials")])
red("N12", "non-annotated copy of tenant-bootstrap-secret", BASE + [row("tenant-x", "tenant-bootstrap-secret")])
red("N13", "--source generalises the copy rule", BASE + [row("yy", "foo")], ["--source", "zz/foo"])
expect("N14 committed mirror-survivor fixture", [FIX / "mirror-survivor.txt"] + ANCHOR, 1)

# ---------------------------------------------------------------- UNKNOWN
print("== UNKNOWN: could not observe (rc 2, never green) ==")
expect("V1 mirror markers but no reflects (source unreadable)", [listing("u1", BASE + [row("zz", "x", at="2026-11-09T10:00:00Z")])] + ANCHOR, 2)
expect("V2 reflects malformed", [listing("u2", BASE + [row("zz", "x", reflects="not-a-ref", autoref="True")])] + ANCHOR, 2)
empty = TMP / "u_empty.txt"; empty.write_text("")
expect("V3 empty file", [empty] + ANCHOR, 2)
expect("V4 kubectl rc != 0", [CONVERGED, 1] + ANCHOR, 2)
expect("V5 truncated listing (no trailer)", [FIX / "truncated.txt"] + ANCHOR, 2)
cnt = TMP / "u_count.txt"; cnt.write_text("\n".join(BASE[:8]) + "\n#END rows=384\n")
expect("V6 trailer count mismatch (partial)", [cnt] + ANCHOR, 2)
mal = TMP / "u_mal.txt"; mal.write_text("\n".join(BASE[:3] + ["a|b|c"]) + "\n#END rows=4\n")
expect("V7 malformed row (3 fields)", [mal] + ANCHOR, 2)
no_anchor = listing("u_anc", [r for r in BASE if not r.startswith("database|postgres-credentials")])
expect("V8 anchor Secret missing from listing", [no_anchor] + ANCHOR, 2)
zero = TMP / "u_zero.txt"; zero.write_text("#END rows=0\n")
expect("V9 zero rows with trailer", [zero] + ANCHOR, 2)
expect("V10 missing file", [TMP / "none.txt"] + ANCHOR, 2)
BOTH = listing("u_both", BASE + [row("zz", "new-secret", allowed="true"), row("zz", "x", reflects="not-a-ref", autoref="True")])
expect("V11 unknown outranks red (red + unreadable mirror => 2)", [BOTH] + ANCHOR, 2)
copy_trunc = TMP / "u_copy_trunc.txt"; copy_trunc.write_text("\n".join(BASE + [row("zz", "postgres-credentials")]) + "\n")
expect("V12 copy present but listing truncated => UNKNOWN, not RED/GREEN", [copy_trunc], 2)
expect("V13 bad rc argument (not an int)", [CONVERGED, "notanint"], 2)
expect("V14 --anchor and --no-anchor together", [CONVERGED, "--anchor", "database/postgres-credentials", "--no-anchor"], 2)
expect("V15 --anchor missing its value", [CONVERGED, "--anchor"], 2)
expect("V16 default anchor missing (post-delete state without --no-anchor)", [no_anchor], 2)
expect("V17 --source without ns/name", [CONVERGED, "--source", "bare"], 2)
expect("V18 no arguments", [], 2)
rc, out = run([TMP / "none.txt"] + ANCHOR)
report("V19 unreadable input never prints GREEN", "GREEN" not in out, out)

# ---------------------------------------------------------------- revert-the-fix
print("== revert-the-fix: rule removed => its mutation must stop being detected ==")
for n in ("N1", "N2", "N3"): not_detected(f"{n} {RED[n][0]}", RED[n][1], 1, "mirror_rule,copy_rule")
not_detected(f"N9 {RED['N9'][0]}", RED["N9"][1], 1, "mirror_rule")
for n in ("N10", "N11", "N12", "N13"): not_detected(f"{n} {RED[n][0]}", RED[n][1], 1, "copy_rule")
for n in ("N5", "N6", "N7"): not_detected(f"{n} {RED[n][0]}", RED[n][1], 1, "source_flags")
not_detected("V5 truncated listing", [FIX / "truncated.txt"] + ANCHOR, 2, "trailer")
not_detected("V6 trailer count mismatch", [cnt] + ANCHOR, 2, "trailer")
not_detected("V11 unknown outranks red", [BOTH] + ANCHOR, 2, "unknown_outranks")
not_detected("V16 default anchor", [no_anchor], 2, "default_anchor")

# ---------------------------------------------------------------- no outside lever
print("== no outside lever on the check ==")
env = dict(os.environ, SA_DET_REVERT="mirror_rule,copy_rule,source_flags,trailer", SA_DET_PROOF_NONCE="x")
r = subprocess.run([sys.executable, str(SCRIPT), str(RED["N1"][1][0])] + ANCHOR, env=env, capture_output=True, text=True)
report("H1 env var cannot weaken the check (CLI still RED on N1)", r.returncode == 1, r.stdout[-300:] + r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(CONVERGED)] + ANCHOR, capture_output=True, text=True)
report("H2 CLI on the converged fixture: rc 0, prints GREEN", r.returncode == 0 and "GREEN" in r.stdout, r.stdout + r.stderr)

# ---------------------------------------------------------------- collector against a stub kubectl
print("== collect-reflector-metadata.sh against a stub kubectl ==")
bindir = TMP / "bin"; bindir.mkdir()
stub = bindir / "kubectl"
def set_stub(body):
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
def collect():
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
    return subprocess.run(["bash", str(COLLECT)], env=env, capture_output=True, text=True)
rows = "\n".join(BASE)
set_stub(f"cat <<'EOT'\n{rows}\nEOT\n")
r = collect()
report("C1 collector: rows pass through and the trailer counts them", r.returncode == 0 and r.stdout.rstrip().endswith(f"#END rows={len(BASE)}") and r.stdout.count("|") == 7 * len(BASE), r.stdout[-200:] + r.stderr)
(TMP / "c1.txt").write_text(r.stdout)
expect("C2 collector output is accepted by the checker as GREEN", [TMP / "c1.txt"], 0)
set_stub("echo boom >&2; exit 3\n")
r = collect()
report("C3 kubectl failure: collector exits with kubectl's rc and prints NO trailer (so the checker says UNKNOWN)", r.returncode == 3 and "#END" not in r.stdout, f"rc={r.returncode} out={r.stdout!r}")
set_stub("exit 0\n")
r = collect()
(TMP / "c4.txt").write_text(r.stdout)
report("C4 kubectl returns nothing: trailer says 0 rows", r.returncode == 0 and "#END rows=0" in r.stdout, r.stdout)
expect("C5 ...and the checker reads that as UNKNOWN, never GREEN", [TMP / "c4.txt"], 2)
script_text = "\n".join(l for l in COLLECT.read_text().splitlines() if not l.lstrip().startswith("#"))
report("C6 collector code never reads Secret data (no .data, no get -o yaml/json; comments excluded)", not re.search(r"\.data\b|-o\s*(yaml|json)\b|--output", script_text) and "-o jsonpath" in script_text, "")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nchecks={counter[0]} failures={len(failures)}")
for f in failures:
    print("FAILED:", f)
sys.exit(1 if failures else 0)
