#!/usr/bin/env python3
"""Pins the job ids behind the required status checks of ruleset main-protection (mctl-agents#1007 B4).
Pins the three required check names of ruleset 18465404 after S1:
  validate-manifests.yml: jobs `validate` and `reserved-hosts` exist, have NO `name:`
  (check name = job id) and NO job-level `if:`; the `pull_request` trigger has no
  `paths`/`paths-ignore`.
  cloudflare-plan.yml: job `cloudflare-plan` exists, name == `cloudflare-plan`,
  `if: always()` (a verdict job that must always report), trigger has no paths filter.
Exit 0 green, 1 red, 2 UNKNOWN (input unreadable: never green).
Usage: python3 tests/test_required_check_job_ids.py [--repo DIR] [--vm FILE] [--cp FILE]
"""
import argparse, os, subprocess, sys
try:
    import yaml
except ImportError:
    print("UNKNOWN: PyYAML missing"); sys.exit(2)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Unknown(Exception):
    pass


def load(a, override, path):
    try:
        if override:
            txt = open(override).read()
        else:
            txt = open(os.path.join(a.repo, path)).read()
        d = yaml.safe_load(txt)
    except (OSError, subprocess.CalledProcessError, yaml.YAMLError) as e:
        raise Unknown("%s unreadable: %s" % (path, e))
    if not isinstance(d, dict) or not isinstance(d.get("jobs"), dict):
        raise Unknown(path + " has no jobs mapping")
    return d


def trigger_fails(d, label):
    on = d.get("on", d.get(True))  # PyYAML reads the key `on` as boolean True
    if not isinstance(on, dict) or "pull_request" not in on:
        return [(label, "no pull_request trigger")]
    pr = on["pull_request"] or {}
    return [(label, "pull_request has " + k) for k in ("paths", "paths-ignore", "branches", "branches-ignore") if k in pr]


def run(a):
    try:
        vm = load(a, a.vm, ".github/workflows/validate-manifests.yml")
        cp = load(a, a.cp, ".github/workflows/cloudflare-plan.yml")
    except Unknown as e:
        return 2, [str(e)]
    f = []
    for j in ("validate", "reserved-hosts"):
        job = vm["jobs"].get(j)
        if job is None:
            f.append(("validate-manifests", "job %s missing" % j)); continue
        if "name" in job:
            f.append(("validate-manifests", "job %s has name: %r (check name would change)" % (j, job["name"])))
        if "if" in job:
            f.append(("validate-manifests", "job %s has job-level if (a skipped required check passes)" % j))
    f += trigger_fails(vm, "validate-manifests")
    job = cp["jobs"].get("cloudflare-plan")
    if job is None:
        f.append(("cloudflare-plan", "job cloudflare-plan missing"))
    else:
        if job.get("name", "cloudflare-plan") != "cloudflare-plan":
            f.append(("cloudflare-plan", "name is %r" % job.get("name")))
        if str(job.get("if", "")).strip() != "always()":
            f.append(("cloudflare-plan", "if is %r, must be always()" % job.get("if")))
    f += trigger_fails(cp, "cloudflare-plan")
    return (1 if f else 0), f


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--vm"); ap.add_argument("--cp")
    code, f = run(ap.parse_args())
    for x in f:
        print("FAIL", x)
    print({0: "GREEN", 1: "RED", 2: "UNKNOWN (exit 2, not green)"}[code]); sys.exit(code)
