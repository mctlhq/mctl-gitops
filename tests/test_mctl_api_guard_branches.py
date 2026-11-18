#!/usr/bin/env python3
"""Branch proofs of the mctl-api config guard at its REAL MIN_CHECKER_VERSION (mctl-gitops#2766).

tests/test_release_config_preflight.py overrides --min-version; this file does not. It runs the shipped
scripts with the shipped MIN against the REAL rendered bootstrap chart and the REAL fixture, with a stub
docker (no network), and proves both branches the release path depends on:

  A  live images (4.167.0, 4.168.0: below MIN, no --check-config) with the CURRENT config are SKIPPED
     safely: exit 0, the visible SKIPPED notice, and not a single docker call. The pin direction follows
     the REAL pinned tag: skipped below MIN, judged by the image (reject blocks, accept passes) at/above.
  B  a below-MIN tag with a service_subjects config is REFUSED by the legacy rule (and is never skipped).
  C  a candidate at/above MIN whose own --check-config rejects the config (the 4.166.0 incident shape)
     is BLOCKED, and the workflows run that check before the tag edit and before anything can push.
  D  a candidate at/above MIN that lacks the flag (boots instead) is BLOCKED.
  E  unreadable states (no docker, pull failure, unreadable or malformed fixture, bad tag, no tag, no
     helm) are errors, never "absent" and never a skip.

Every case is also run against mutants of the shipped scripts; a mutant that leaves the whole matrix
green is a failure of this file (the detector must be red when the fix is reverted).

Exit 0 green, 1 red, 2 UNKNOWN (PyYAML or helm missing: never green).
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("UNKNOWN: PyYAML missing")
    sys.exit(2)
if shutil.which("helm") is None:
    print("UNKNOWN: helm missing")
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_REL = "platform-gitops/helm-charts/zitadel-iac/iac/tests/fixtures/mctl-api-config-check.json"
BOOTSTRAP_REL = "platform-gitops/bootstrap"
IMAGE = "ghcr.io/mctlhq/mctl-api"
# Released mctl-api builds that have no --check-config (verified: cmd/api/check_config.go is absent at both tags).
FLAGLESS_LIVE = ["4.167.0", "4.168.0"]
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:300]}")


STUB = r"""#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$1" in
  image) [ "$FAKE_MODE" = pull_fail ] && exit 1; exit 0 ;;
  pull) exit 1 ;;
  rm) exit 0 ;;
  run)
    case "$FAKE_MODE" in
      ok) echo "mctl-api check-config: ok"; exit 0 ;;
      reject) echo "invalid configuration: may not combine service_subjects with customers_org_id" >&2; exit 1 ;;
      ok_but_fails) echo "mctl-api check-config: ok"; exit 1 ;;
      no_flag) echo '{"msg":"server started"}'; exit 0 ;;
    esac ;;
esac
exit 99
"""


def make_tree(base, check_text=None, wrapper_text=None, fixture_text=None, fixture_absent=False):
    """A tree shaped like the repo (scripts/, bootstrap chart, fixture) whose scripts are the shipped ones
    unless a mutant text is given. The bootstrap chart is linked, the fixture is copied (so it can vary)."""
    t = pathlib.Path(base)
    (t / "scripts").mkdir(parents=True)
    (t / "scripts/check-mctl-api-oidc-config.py").write_text(check_text or (ROOT / "scripts/check-mctl-api-oidc-config.py").read_text())
    (t / "scripts/release-config-preflight.py").write_text(wrapper_text or (ROOT / "scripts/release-config-preflight.py").read_text())
    (t / "platform-gitops").mkdir()
    (t / BOOTSTRAP_REL).symlink_to(ROOT / BOOTSTRAP_REL)
    fx = t / FIXTURE_REL
    fx.parent.mkdir(parents=True)
    if not fixture_absent:
        fx.write_text(fixture_text if fixture_text is not None else (ROOT / FIXTURE_REL).read_text())
    return t


def run_wrapper(tree, mode, tag, image=IMAGE, with_docker=True, with_helm=True):
    """Runs scripts/release-config-preflight.py (bump direction) with NO --min-version: the shipped MIN applies."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "bin").mkdir()
        if with_helm:
            (d / "bin/helm").symlink_to(shutil.which("helm"))
        if with_docker:
            (d / "bin/docker").write_text(STUB)
            (d / "bin/docker").chmod(0o755)
        log = d / "docker.log"
        log.write_text("")
        env = {"PATH": str(d / "bin"), "FAKE_LOG": str(log), "FAKE_MODE": mode, "CHECK_PULL_DELAY": "0", "HOME": str(d)}
        if image is not None:
            env["IMAGE_NAME"] = image
        if tag is not None:
            env["IMAGE_TAG"] = tag
        r = subprocess.run([sys.executable, str(tree / "scripts/release-config-preflight.py")], env=env, capture_output=True, text=True, cwd=str(tree))
        return r.returncode, r.stdout + r.stderr, log.read_text()


def run_pin(tree, mode):
    """Runs scripts/check-mctl-api-oidc-config.py (pin direction, the validate gate) on the REAL pinned tag."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "bin").mkdir()
        (d / "bin/helm").symlink_to(shutil.which("helm"))
        (d / "bin/docker").write_text(STUB)
        (d / "bin/docker").chmod(0o755)
        log = d / "docker.log"
        log.write_text("")
        env = {"PATH": str(d / "bin"), "FAKE_LOG": str(log), "FAKE_MODE": mode, "CHECK_PULL_DELAY": "0", "HOME": str(d)}
        r = subprocess.run([sys.executable, str(tree / "scripts/check-mctl-api-oidc-config.py")], env=env, capture_output=True, text=True, cwd=str(tree))
        return r.returncode, r.stdout + r.stderr, log.read_text()


def pinned_tag():
    """The image.tag the shipped script reads from the rendered bootstrap chart (what the pin direction judges)."""
    spec = importlib.util.spec_from_file_location("chk", ROOT / "scripts/check-mctl-api-oidc-config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_values()["image"]["tag"]


def read_min(check_text):
    import re
    return re.search(r'^MIN_CHECKER_VERSION = "(\d+\.\d+\.\d+)"', check_text, re.M).group(1)


def tup(v):
    return tuple(int(x) for x in v.split("."))


def fixture_with_service_subjects():
    fx = json.loads((ROOT / FIXTURE_REL).read_text())
    for p in fx["MCTL_OIDC_PROVIDERS"]:
        if "customers_org_id" in p:
            p["service_subjects"] = {"2": "3"}
    assert any("service_subjects" in p for p in fx["MCTL_OIDC_PROVIDERS"]), "fixture has no customers_org_id entry to extend"
    return json.dumps(fx)


def matrix(check_text=None, wrapper_text=None):
    """case name -> (ok, detail). Everything executes the (possibly mutated) scripts."""
    res = {}
    mn = read_min(check_text or (ROOT / "scripts/check-mctl-api-oidc-config.py").read_text())
    above = [mn, f"{tup(mn)[0]}.{tup(mn)[1] + 1}.0"]
    below_all = FLAGLESS_LIVE + ["4.0.0"]
    with tempfile.TemporaryDirectory() as base:
        base = pathlib.Path(base)
        n = [0]

        def tree(**kw):
            n[0] += 1
            return make_tree(base / f"t{n[0]}", check_text, wrapper_text, **kw)

        live = tree()
        # A: live images, current config
        for tag in FLAGLESS_LIVE:
            rc, out, log = run_wrapper(live, "reject", tag)   # worst case: the image would reject, but it must not even be asked
            res[f"A bump {tag} (live, below MIN) with the current config: SKIPPED, no docker call"] = (
                rc == 0 and "SKIPPED" in out and log.strip() == "", (rc, out[-160:], log))
        # Pin direction (the validate gate) on the REAL pinned tag. Which branch applies depends on that
        # tag: a release-bump PR that moves the pin to MIN or later must be judged by the image itself.
        # Asserting a skip unconditionally turned every such bump red (mctl-api 4.169.0, gitops#2798).
        pin = pinned_tag()
        if tup(pin) < tup(mn):
            rc, out, log = run_pin(live, "reject")
            res[f"A pin direction: the real pinned tag {pin} (below MIN) with the real config: SKIPPED, no docker call"] = (
                rc == 0 and "SKIPPED" in out and log.strip() == "", (rc, out[-160:], log))
        else:
            rc, out, log = run_pin(live, "reject")
            res[f"A pin direction: the real pinned tag {pin} (at/above MIN) whose image rejects the config: BLOCKED"] = (
                rc == 1 and "CONFIG REJECTED" in out and "run" in log.split() and "SKIPPED" not in out, (rc, out[-160:], log))
            rc, out, log = run_pin(live, "ok")
            res[f"A pin direction: the real pinned tag {pin} (at/above MIN) whose image accepts: allowed, --check-config ran"] = (
                rc == 0 and "--check-config" in log and "SKIPPED" not in out, (rc, out[-160:], log))
        # B: below MIN + service_subjects
        bad = tree(fixture_text=fixture_with_service_subjects())
        for tag in below_all:
            rc, out, log = run_wrapper(bad, "ok", tag)
            res[f"B bump {tag} (below MIN) with service_subjects: REFUSED by the legacy rule"] = (
                rc == 1 and "LEGACY RULE" in out and "SKIPPED" not in out and log.strip() == "", (rc, out[-160:], log))
        # C: at/above MIN, the image rejects the config
        for tag in above:
            rc, out, log = run_wrapper(live, "reject", tag)
            res[f"C bump {tag} (at/above MIN) whose --check-config rejects the config: BLOCKED"] = (
                rc == 1 and "CONFIG REJECTED" in out and "run" in log.split() and "SKIPPED" not in out, (rc, out[-160:], log))
            rc, out, log = run_wrapper(live, "ok_but_fails", tag)
            res[f"C bump {tag}: ok line printed but exit code non-zero: BLOCKED"] = (rc == 1, (rc, out[-160:], log))
            rc, out, log = run_wrapper(live, "ok", tag)
            res[f"C bump {tag} accepting image: allowed, its --check-config really ran"] = (
                rc == 0 and "--check-config" in log, (rc, out[-160:], log))
            rc, out, log = run_wrapper(bad, "reject", tag)
            res[f"C bump {tag} with a service_subjects config: the IMAGE decides (reject: blocked)"] = (rc == 1, (rc, out[-160:], log))
            rc, out, log = run_wrapper(bad, "ok", tag)
            res[f"C bump {tag} with a service_subjects config: the IMAGE decides (accept: allowed, legacy rule not applied)"] = (
                rc == 0 and "LEGACY RULE" not in out, (rc, out[-160:], log))
        # D: at/above MIN without the flag
        for tag in above:
            rc, out, log = run_wrapper(live, "no_flag", tag)
            res[f"D bump {tag} (at/above MIN) without the flag: BLOCKED"] = (rc == 1 and "SKIPPED" not in out, (rc, out[-160:], log))
        # E: unreadable states
        rc, out, _ = run_wrapper(live, "ok", above[0], with_docker=False)
        res["E no docker at/above MIN: error, not a skip"] = (rc == 1 and "RUNNER PROBLEM" in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(live, "pull_fail", above[0])
        res["E registry/pull failure at/above MIN: error, not a skip"] = (rc == 1 and "REGISTRY/PULL PROBLEM" in out, (rc, out[-160:]))
        rc, out, log = run_wrapper(live, "ok", FLAGLESS_LIVE[0], with_helm=False)
        res["E no helm (cannot render the config): error even below MIN"] = (rc == 1 and "SKIPPED" not in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(tree(fixture_text="{not json"), "ok", FLAGLESS_LIVE[0])
        res["E unparsable fixture below MIN: refused, never skipped"] = (rc == 1 and "LEGACY RULE" in out and "SKIPPED" not in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(tree(fixture_absent=True), "ok", FLAGLESS_LIVE[0])
        res["E absent fixture below MIN: refused, never skipped"] = (rc == 1 and "LEGACY RULE" in out and "SKIPPED" not in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(tree(fixture_text=json.dumps({"MCTL_OIDC_PROVIDERS": "x"})), "ok", FLAGLESS_LIVE[0])
        res["E fixture whose providers are not a list below MIN: refused, never skipped"] = (rc == 1 and "SKIPPED" not in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(tree(fixture_text=json.dumps({"other": 1})), "ok", FLAGLESS_LIVE[0])
        res["E fixture without MCTL_OIDC_PROVIDERS below MIN: refused, never skipped"] = (rc == 1 and "SKIPPED" not in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(live, "ok", "latest")
        res["E unparsable tag: blocked"] = (rc == 1 and "SKIPPED" not in out, (rc, out[-160:]))
        rc, out, _ = run_wrapper(live, "ok", None)
        res["E no tag: refused"] = (rc == 2, (rc, out[-160:]))
        rc, out, log = run_wrapper(live, "reject", FLAGLESS_LIVE[0], image="ghcr.io/mctlhq/mctl-agents")
        res["other image: not applicable, no docker call"] = (rc == 0 and log.strip() == "", (rc, out[-160:], log))
    return res


def mutants():
    chk = (ROOT / "scripts/check-mctl-api-oidc-config.py").read_text()
    wrp = (ROOT / "scripts/release-config-preflight.py").read_text()
    mn = read_min(chk)
    out = {}

    def sub(text, old, new, label):
        assert old in text, f"mutation does not apply: {label}"
        return text.replace(old, new, 1)
    out["legacy rule call removed (plain skip)"] = (sub(chk, "        legacy_rule(fixture_path, tag, min_version)\n", "", "legacy"), None)
    out["legacy rule ignores service_subjects"] = (sub(chk, 'if "service_subjects" in p:', "if False:", "ss"), None)
    out["legacy rule treats an unreadable fixture as clean"] = (
        sub(chk, "except (OSError, ValueError, KeyError, TypeError) as e:", "except ZeroDivisionError as e:", "unreadable"), None)
    out["MIN lowered to the live flagless build"] = (sub(chk, f'MIN_CHECKER_VERSION = "{mn}"', 'MIN_CHECKER_VERSION = "4.167.0"', "min"), None)
    out["skip also at MIN (< becomes <=)"] = (sub(chk, 'if semver(tag, "image.tag") < semver(min_version', 'if semver(tag, "image.tag") <= semver(min_version', "le"), None)
    out["at/above MIN: image never run (always ok)"] = (sub(chk, "    check_image(f\"{IMAGE_REPO}:{tag}\", env, docker)\n", "", "noimg"), None)
    out["image exit 0 without the ok line accepted"] = (sub(chk, "if not lines or lines[-1].strip() != OK_LINE:", "if False:", "okline"), None)
    out["non-zero exit of the image ignored"] = (sub(chk, "if res.returncode != 0:\n        out =", "if False:\n        out =", "rc"), None)
    out["missing docker treated as a skip"] = (
        sub(chk, '        raise Refuse(f"RUNNER PROBLEM, not a config rejection: {docker} not found, cannot run {image}")', "        return", "docker"), None)
    out["wrapper never runs the check (always ok)"] = (None, sub(wrp, "    rc = subprocess.run(cmd).returncode\n", "    rc = 0\n", "never"))
    out["wrapper ignores the candidate tag"] = (None, sub(wrp, 'cmd = [sys.executable, str(CHECK), "--image-tag", tag]', "cmd = [sys.executable, str(CHECK)]", "tag"))
    return out


def workflow_ordering():
    """The preflight sits before the tag edit; nothing in the bump job pushes; every pushing job needs `bump`."""
    spec = importlib.util.spec_from_file_location("trpc", ROOT / "tests/test_release_config_preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for wf, bump_step in mod.BUMP_STEP.items():
        text = (ROOT / ".github/workflows" / wf).read_text()
        check(f"{wf}: preflight wiring (before the tag edit, no swallowed failure)", mod.bump_wiring(text, bump_step) == [], mod.bump_wiring(text, bump_step))
        jobs = yaml.safe_load(text)["jobs"]
        bump_steps = jobs["bump"]["steps"]
        pushes_in_bump = [s.get("name") for s in bump_steps if "git push" in str(s.get("run", ""))]
        check(f"{wf}: the bump job itself never pushes", pushes_in_bump == [], pushes_in_bump)

        def needs(j):
            v = jobs[j].get("needs") or []
            return [v] if isinstance(v, str) else list(v)

        def reaches_bump(j, seen=()):
            return "bump" in needs(j) or any(reaches_bump(x, seen + (j,)) for x in needs(j) if x not in seen)
        pushers = [j for j, job in jobs.items() if j != "bump" and any("git push" in str(s.get("run", "")) for s in job.get("steps") or [])]
        check(f"{wf}: there is at least one pushing job (the claim is not vacuous)", bool(pushers), pushers)
        check(f"{wf}: every pushing job needs `bump` (a failed preflight stops the push)", all(reaches_bump(j) for j in pushers), pushers)
        # a ledger step must not be able to bypass the preflight: nothing that pushes may skip `bump`
        for j in pushers:
            cond = str(jobs[j].get("if", ""))
            check(f"{wf}: pushing job {j} does not run `if: always()` (would push past a failed bump)", "always()" not in cond, cond)


def main():
    res = matrix()
    for name, (ok, detail) in res.items():
        check(name, ok, detail)
    mn = read_min((ROOT / "scripts/check-mctl-api-oidc-config.py").read_text())
    check(f"MIN_CHECKER_VERSION {mn} is above every released build without --check-config ({', '.join(FLAGLESS_LIVE)})",
          all(tup(mn) > tup(v) for v in FLAGLESS_LIVE), mn)
    workflow_ordering()
    print("--- mutants: each reverted fix must turn the matrix red")
    from concurrent.futures import ThreadPoolExecutor

    def one(item):
        name, (c, w) = item
        try:
            return name, [k for k, (ok, _) in matrix(c, w).items() if not ok]
        except Exception as e:   # a mutant that crashes the detector is also red
            return name, [f"crash {type(e).__name__}"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, red in pool.map(one, list(mutants().items())):
            check(f"mutant red: {name}", bool(red), "matrix stayed green")
    print("\n" + ("FAILED:\n  " + "\n  ".join(failures) if failures else "all ok"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
