#!/usr/bin/env python3
"""The mctl-api config guard is part of the mandatory gates (mctl-gitops#2766).

Two directions, each proven green on the real input and red on a mutation:

  PIN direction  validate-manifests.yml runs the guard step in a validate-N
                 shard, unconditionally, so a red guard turns `validate`
                 (the required check) red.
  BUMP direction release-deploy.yaml and gitops-bump.yaml run
                 scripts/release-config-preflight.py in the `bump` job, before
                 the tag is edited. The 4.166.0 shape (a rule newer than the
                 pinned image) is simulated with a stub docker whose NEW image
                 rejects the current rendered config.

Exit 0 green, 1 red, 2 UNKNOWN (input unreadable or helm missing: never green).
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("UNKNOWN: PyYAML missing")
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows"
VM = "validate-manifests.yml"
GUARD_STEP = "mctl-api accepts the rendered OIDC configuration"
PREFLIGHT = "release-config-preflight.py"
EXPECTED_RUN = "python3 scripts/release-config-preflight.py"
BUMP_STEP = {"release-deploy.yaml": "Bump image tag(s)", "gitops-bump.yaml": "Bump image tags"}
WRAPPER = ROOT / "scripts" / PREFLIGHT
CHECK = ROOT / "scripts/check-mctl-api-oidc-config.py"
IMAGE = "ghcr.io/mctlhq/mctl-api"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:300]}")


# ------------------------------------------------------------- wiring checks
def jobs_of(text):
    d = yaml.safe_load(text)
    if not isinstance(d, dict) or not isinstance(d.get("jobs"), dict):
        raise ValueError("no jobs mapping")
    return d["jobs"]


def guard_wiring(text):
    """Problems with how the PIN-direction step sits in the required gate."""
    jobs = jobs_of(text)
    agg = jobs.get("validate") or {}
    needs = agg.get("needs") or []
    needs = [needs] if isinstance(needs, str) else list(needs)
    hits = [(j, s) for j, job in jobs.items() for s in (job.get("steps") or []) if GUARD_STEP in str(s.get("name", ""))]
    if len(hits) != 1:
        return [f"expected exactly one guard step, found {len(hits)}"]
    jname, step = hits[0]
    out = []
    if jname not in needs:
        out.append(f"guard step is in job {jname}, which is not in validate.needs")
    if "if" in step or "if" in jobs[jname]:
        out.append("guard step or its job has an `if` (skipped counts as passed)")
    if step.get("continue-on-error") or jobs[jname].get("continue-on-error"):
        out.append("guard step or its job is continue-on-error")
    if "check-mctl-api-oidc-config.py" not in step.get("run", ""):
        out.append("guard step does not run the script")
    return out


def bump_wiring(text, bump_step):
    """Problems with how the BUMP-direction preflight sits in the bump job."""
    steps = (jobs_of(text).get("bump") or {}).get("steps") or []
    names = [s.get("name", "") for s in steps]
    idx = [i for i, s in enumerate(steps) if PREFLIGHT in str(s.get("run", ""))]
    if len(idx) != 1:
        return [f"expected exactly one step running {PREFLIGHT} in job bump, found {len(idx)}"]
    i, s = idx[0], steps[idx[0]]
    out = []
    if bump_step not in names:
        return [f"bump step {bump_step!r} not found"]
    if i > names.index(bump_step):
        out.append("preflight runs after the tag edit")
    if "if" in s or "continue-on-error" in s or "shell" in s:
        out.append("preflight step has if/continue-on-error/shell (any value, expressions included)")
    job = jobs_of(text).get("bump") or {}
    if "continue-on-error" in job:
        out.append("bump job has continue-on-error")
    if str(s.get("run", "")).strip() != EXPECTED_RUN:
        out.append(f"preflight run is not exactly {EXPECTED_RUN!r} (a swallowed failure such as `|| true`, `; true`, `set +e` or a wrapper): {s.get('run')!r}")
    e = s.get("env") or {}
    if "inputs.image_name" not in str(e.get("IMAGE_NAME")) or "inputs.image_tag" not in str(e.get("IMAGE_TAG")):
        out.append("preflight env is not the dispatch image_name/image_tag")
    if not any("setup-helm" in str(x.get("uses", "")) for x in steps[:i]):
        out.append("no helm install before the preflight (the check renders the bootstrap chart)")
    return out


# ----------------------------------------------------------- behaviour checks
STUB = r"""#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$1" in
  image) exit 0 ;;
  rm|network) exit 0 ;;
  exec) exit 0 ;;
  logs) echo "boot log line"; exit 0 ;;
  inspect) echo true; exit 0 ;;
  run)
    case "$*" in
      *" -d "*) exit 0 ;;
      *curlimages*) if [ "$FAKE_READYZ" = store_failed ]; then
                      printf '{"status":"not ready","checks":{"stores":"init_failed"},"failed_stores":["glovo link consent"]}\n503'
                    else printf '{"status":"ready","checks":{"stores":"ok"}}\n200'; fi; exit 0 ;;
      *postgres:*) exit 0 ;;
    esac
    case "$FAKE_MODE" in
      ok) echo "mctl-api check-config: ok"; exit 0 ;;
      newer_rule) echo "invalid configuration: service_subjects with customers_org_id" >&2; exit 1 ;;
      no_flag) echo '{"msg":"server started"}'; exit 0 ;;
    esac ;;
esac
exit 99
"""


def run_pre(script, mode, tag="4.168.0", image=IMAGE, min_version="4.167.0", with_docker=True, extra_env=None):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        bindir = d / "bin"
        bindir.mkdir()
        helm = shutil.which("helm")
        if helm is None:
            raise RuntimeError("helm missing")
        (bindir / "helm").symlink_to(helm)
        if with_docker:
            (bindir / "docker").write_text(STUB)
            (bindir / "docker").chmod(0o755)
        log = d / "docker.log"
        log.write_text("")
        env = {"PATH": str(bindir), "FAKE_LOG": str(log), "FAKE_MODE": mode, "CHECK_PULL_DELAY": "0",
               "HOME": str(d)}
        if image is not None:
            env["IMAGE_NAME"] = image
        if tag is not None:
            env["IMAGE_TAG"] = tag
        env.update(extra_env or {})
        r = subprocess.run([sys.executable, str(script), "--min-version", min_version],
                           env=env, capture_output=True, text=True, cwd=str(ROOT))
        return r.returncode, r.stdout + r.stderr, log.read_text()


def behaviour(script):
    """name -> (returncode matches, detail). The 4.166.0 shape is `newer_rule`."""
    res = {}
    rc, out, _ = run_pre(script, "newer_rule")
    res["new image rejects the current config: bump blocked"] = (rc == 1, (rc, out[-200:]))
    rc, out, log = run_pre(script, "ok")
    res["new image accepts: bump allowed, image actually run"] = (rc == 0 and "--check-config" in log, (rc, out[-200:]))
    rc, out, _ = run_pre(script, "ok", extra_env={"FAKE_READYZ": "store_failed"})
    res["new image accepts the config but a store fails init: bump blocked"] = (rc == 1 and "glovo link consent" in out, (rc, out[-300:]))
    rc, out, _ = run_pre(script, "no_flag")
    res["image at/above MIN without the flag: blocked (a placeholder cannot hide it)"] = (rc == 1, (rc, out[-200:]))
    rc, out, log = run_pre(script, "newer_rule", tag="4.166.0")
    # The real config lists the consent reader under service_subjects, which a flagless
    # image cannot parse: refused by the legacy rule, never skipped, docker not run.
    res["candidate below MIN with the real config (service_subjects): refused by the legacy rule, docker not run"] = (
        rc == 1 and "LEGACY RULE" in out and "SKIPPED" not in out and "run" not in log.split(), (rc, out[-200:]))
    rc, out, log = run_pre(script, "newer_rule", image="ghcr.io/mctlhq/mctl-agents")
    res["other image: not applicable, docker not run"] = (rc == 0 and not log.strip(), (rc, out[-200:]))
    rc, out, _ = run_pre(script, "ok", with_docker=False)
    res["docker missing: blocked, not skipped"] = (rc == 1, (rc, out[-200:]))
    rc, out, _ = run_pre(script, "ok", tag="latest")
    res["unparsable tag: blocked"] = (rc == 1, (rc, out[-200:]))
    rc, out, _ = run_pre(script, "ok", tag=None)
    res["missing IMAGE_TAG: refused"] = (rc == 2, (rc, out[-200:]))
    return res


LEGACY_BAD = {"MCTL_OIDC_PROVIDERS": [{"name": "zitadel", "customers_org_id": "1", "service_subjects": {"2": "3"}}]}
LEGACY_LIVE = {"MCTL_OIDC_PROVIDERS": [{"name": "zitadel", "customers_org_id": "1"}]}


def legacy_outcomes(script_path):
    """Calls guard() of the given copy of the script below MIN with fixtures. No docker, no helm:
    below MIN the guard decides before either is needed."""
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("chk_legacy", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    vals = lambda tag: {"image": {"repository": IMAGE, "tag": tag}}
    out = {}
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        for name, body in (("bad", json.dumps(LEGACY_BAD)), ("live", json.dumps(LEGACY_LIVE)), ("junk", "{nope")):
            (d / f"{name}.json").write_text(body)

        def call(fx, tag):
            try:
                return mod.guard(vals(tag), d / fx, min_version="4.167.0")
            except mod.Refuse as e:
                return "refused:" + str(e)
        out["4.166.0 + service_subjects"] = call("bad.json", "4.166.0")
        out["4.165.0 + service_subjects"] = call("bad.json", "4.165.0")
        out["4.166.0 + live config"] = call("live.json", "4.166.0")
        out["4.166.0 + junk fixture"] = call("junk.json", "4.166.0")
        out["4.166.0 + absent fixture"] = call("absent.json", "4.166.0")
    return out


def legacy_green(o):
    return "LEGACY RULE" in o["4.166.0 + service_subjects"] \
        and "LEGACY RULE" in o["4.165.0 + service_subjects"] \
        and o["4.166.0 + live config"] == "skipped" \
        and "LEGACY RULE" in o["4.166.0 + junk fixture"] and "LEGACY RULE" in o["4.166.0 + absent fixture"]


def legacy_checks():
    o = legacy_outcomes(CHECK)
    check("LEGACY: tag below MIN + service_subjects refused; live config still skipped; unreadable fixture refused", legacy_green(o), o)
    src = CHECK.read_text()
    call = "legacy_rule(fixture_path, tag, min_version)\n        print("
    mutants = {
        "legacy rule call removed (plain skip)": src.replace(call, "print(", 1),
        "legacy rule ignores service_subjects": src.replace('if "service_subjects" in p:', "if False:", 1),
        "legacy rule treats an unreadable fixture as clean": src.replace("except (OSError, ValueError, KeyError, TypeError) as e:", "except ZeroDivisionError as e:", 1),
    }
    for mname, text in mutants.items():
        assert text != src, f"mutation did not apply: {mname}"
        with tempfile.TemporaryDirectory() as d:
            mp = pathlib.Path(d) / "chk.py"
            mp.write_text(text)
            try:
                mo = legacy_outcomes(mp)
                red = not legacy_green(mo)
            except Exception as e:  # a mutant that crashes the detector is also a red
                red = True
        check(f"mutant red: {mname}", red, "mutant passed every case")


def main():
    vm_text = (WF / VM).read_text()
    problems = guard_wiring(vm_text)
    check("PIN: guard step is unconditional, in a job listed in validate.needs", not problems, problems)
    for f, step in BUMP_STEP.items():
        problems = bump_wiring((WF / f).read_text(), step)
        check(f"BUMP: {f} runs the preflight in `bump` before the tag edit", not problems, problems)

    # Mutations of the wiring: every one must turn the check red.
    def must_fail(name, problems):
        check(f"mutant red: {name}", bool(problems), "mutation not detected")

    must_fail("guard step removed", guard_wiring(vm_text.replace(GUARD_STEP, "renamed step")))
    must_fail("guard step made conditional", guard_wiring(vm_text.replace(
        f"      - name: {GUARD_STEP}", f"      - if: false\n        name: {GUARD_STEP}", 1)))
    must_fail("guard step continue-on-error", guard_wiring(vm_text.replace(
        f"      - name: {GUARD_STEP}", f"      - continue-on-error: true\n        name: {GUARD_STEP}", 1)))
    for f, step in BUMP_STEP.items():
        t = (WF / f).read_text()
        must_fail(f"{f}: preflight removed", bump_wiring(t.replace(PREFLIGHT, "true  # removed"), step))
        must_fail(f"{f}: preflight made conditional", bump_wiring(t.replace(
            "      - name: New image accepts the rendered configuration (config preflight)\n",
            "      - name: New image accepts the rendered configuration (config preflight)\n        if: false\n"), step))
        for label, new in (("`|| true`", EXPECTED_RUN + " || true"), ("`; true`", EXPECTED_RUN + "; true"),
                           ("`set +e`", "set +e\n          " + EXPECTED_RUN)):
            mt = t.replace(f"run: {EXPECTED_RUN}", "run: |\n          " + new if "\n" in new or label != "`|| true`" else f"run: {new}", 1)
            assert mt != t, label
            must_fail(f"{f}: preflight run swallows failure with {label}", bump_wiring(mt, step))
        for label, line in (("continue-on-error: true", "true"), ("continue-on-error expression", "${{ always() }}"),
                            ("continue-on-error: false string expr", "${{ inputs.image_tag == 'x' }}")):
            mt = t.replace(f"        run: {EXPECTED_RUN}", f"        continue-on-error: {line}\n        run: {EXPECTED_RUN}", 1)
            assert mt != t, label
            must_fail(f"{f}: preflight step has {label}", bump_wiring(mt, step))
        must_fail(f"{f}: preflight step has shell override", bump_wiring(t.replace(
            f"        run: {EXPECTED_RUN}", f"        shell: bash {{0}} || true\n        run: {EXPECTED_RUN}", 1), step))
        must_fail(f"{f}: preflight moved after the tag edit", bump_wiring(
            t.replace("      - name: New image accepts the rendered configuration (config preflight)",
                      "      - name: moved\n        run: echo\n      - name: New image accepts the rendered configuration (config preflight)", 1)
             .replace(f"      - name: {step}\n", "      - name: pre-edit\n        run: echo\n", 1)
             .replace("      - name: moved\n", f"      - name: {step}\n        run: echo\n      - name: moved\n", 1), step))

    # Behaviour on the real wrapper.
    try:
        res = behaviour(WRAPPER)
    except RuntimeError as e:
        print(f"UNKNOWN: {e}")
        return 2
    for name, (ok, detail) in res.items():
        check(name, ok, detail)

    # Behaviour mutants: a wrapper that does not block must be seen failing.
    src = WRAPPER.read_text()
    mutants = {
        "wrapper never runs the check (always ok)": src.replace("rc = subprocess.run(cmd).returncode", "rc = 0"),
        "wrapper skips mctl-api (treats it as not applicable)": src.replace("if name != IMAGE:", "if True:"),
        "wrapper ignores the candidate tag": src.replace('"--image-tag", tag, "--readyz"]', '"--image-tag", "4.0.0", "--readyz"]'),
        "wrapper drops the readyz stage": src.replace('"--image-tag", tag, "--readyz"]', '"--image-tag", tag]'),
    }
    for mname, text in mutants.items():
        assert text != src, f"mutation did not apply: {mname}"
        with tempfile.TemporaryDirectory() as d:
            sd = pathlib.Path(d) / "scripts"
            sd.mkdir()
            (sd / PREFLIGHT).write_text(text)
            (sd / CHECK.name).symlink_to(CHECK)
            mres = behaviour(sd / PREFLIGHT)
        check(f"mutant red: {mname}", not all(ok for ok, _ in mres.values()), "mutant passed every case")


    # Legacy rule (below-MIN skip must not pair an old image with service_subjects).
    legacy_checks()

    # Placeholder cannot sit at or below a release known to lack the flag.
    m = re.search(r'^MIN_CHECKER_VERSION = "(\d+\.\d+\.\d+)"', CHECK.read_text(), re.M)
    if not m:
        print("UNKNOWN: MIN_CHECKER_VERSION not found in the script")
        return 2
    ns = {"MIN_CHECKER_VERSION": m.group(1)}
    tup = lambda s: tuple(int(x) for x in s.split("."))
    check("MIN_CHECKER_VERSION is above 4.168.0, the last RELEASED mctl-api known to lack --check-config (no cmd/api/check_config.go at the tags 4.167.0 and 4.168.0)",
          tup(ns["MIN_CHECKER_VERSION"]) > tup("4.168.0"), ns["MIN_CHECKER_VERSION"])
    print("\n%s" % ("FAILED:\n  " + "\n  ".join(failures) if failures else "all ok"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
