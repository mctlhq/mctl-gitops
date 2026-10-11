#!/usr/bin/env python3
"""Executable reproduction for gitops#992: parameters must reach sh as data.

Renders a template's env the way Argo does (text replacement of
{{inputs|workflow.parameters.X}}), runs the parameter-reading prelude of the
script under sh, and asserts an injected `touch $CANARY` never runs. A control
case on the old interpolated form proves the harness can detect injection.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CT = ROOT / "platform-gitops/argo-workflows/cluster-templates"
PH = re.compile(r"\{\{\s*(?:inputs|workflow)\.parameters\.([A-Za-z0-9_.-]+)\s*\}\}")

# (file, template, stop[, start]): `stop` is the text of the first line that is
# NOT part of the prelude; the optional `start` is the first prelude line, for
# templates that run something before they read their parameters.
CASES = [
    ("tpl-validate-tenant.yaml", "validate", "# ── 3. Clone"),
    ("tpl-git-commit.yaml", "commit-service", "apk add"),
    ("tpl-vault-write.yaml", "write-service-secrets", "echo \"🔐 Authenticating"),
    ("tpl-vault-write.yaml", "delete-service-secrets", "SA_TOKEN="),
    ("wft-smoke-test.yaml", "run-onboard", "WF_NAME=$(kubectl create"),
    ("wft-smoke-test.yaml", "check-pod-running", "check_missing_secret_reference()"),
    ("wft-create-tenant.yaml", "create-vault-policy", "echo \"Authenticating"),
    ("wft-delete-tenant-safe.yaml", "delete-vault-policy", "echo \"Authenticating"),
    ("wft-delete-tenant.yaml", "delete-vault-policy", "echo \"Authenticating"),
    ("wft-deploy-service.yaml", "refresh-apps-appset", "echo \"Triggering hard refresh"),
    ("wft-provision-database.yaml", "do-provision", "# ── Authenticate with Vault",
     "TEAM=\"$PARAM_TEAM_NAME\""),
    ("wft-retire-service.yaml", "cleanup-db-from-gitops", "# ── Set up SSH for git"),
]


def payloads(canary):
    return [
        f'"; touch {canary}; #',
        f"'; touch {canary}; #",
        f"$(touch {canary})",
        f"`touch {canary}`",
        f"x\nENVEOF\nSECRETEOF\nSECRETS_EOF\ntouch {canary}",
    ]


def template(fname, name):
    doc = yaml.safe_load((CT / fname).read_text())
    return next(t for t in doc["spec"]["templates"] if t["name"] == name)


def run_sh(script, env, cwd, shell="sh"):
    # dash has no pipefail; the prelude's strict-mode line is not under test.
    script = script.replace("set -euo pipefail", "set -eu")
    return subprocess.run([shell, "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True)


failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


with tempfile.TemporaryDirectory() as d:
    work = pathlib.Path(d)
    canary = work / "canary"
    base_env = {"PATH": os.environ["PATH"], "TMPDIR": str(work)}

    # Control: the old shape executes the payload.
    old = PH.sub(lambda m: f'"; touch {canary}; #', 'X="{{inputs.parameters.p}}"')
    run_sh(old, base_env, work)
    check("control: interpolated form runs the payload", canary.exists())
    canary.unlink(missing_ok=True)

    ONBOARD_NAMES = ["action", "team_name", "component_name", "component_type",
                     "dockerfile_repo", "git_tag", "port", "host", "env_vars",
                     "secret_env_vars", "provision_database", "skip_health_check",
                     "dockerfile_path", "image_tag"]
    have_jq = shutil.which("jq") is not None
    if not have_jq:
        print("SKIP  jq not installed: child-workflow.json assertions not run")

    for fname, name, stop, *rest in CASES:
        tmpl = template(fname, name)
        src = tmpl["script"]["source"]
        shell = (tmpl["script"].get("command") or ["sh"])[0]
        check(f"{name}: no placeholder in script.source", not PH.search(src))
        lines = src.split("\n")
        idx = next(i for i, l in enumerate(lines) if l.strip().startswith(stop))
        first = 0
        if rest:
            first = next(i for i, l in enumerate(lines) if l.strip().startswith(rest[0]))
        prelude = "\n".join(lines[:first] + lines[first:idx] if not rest
                             else ["set -e"] + lines[first:idx])
        for payload in payloads(canary):
            env = dict(base_env)
            for e in tmpl["script"].get("env") or []:
                env[e["name"]] = PH.sub(lambda m: payload, e.get("value", ""))
            # `set -e` in the prelude may stop it early on a validation
            # failure; that is fine, only the canary matters.
            r = run_sh(prelude, env, work, shell)
            check(f"{name}: payload {payload.splitlines()[0]!r} is data",
                  not canary.exists())
            canary.unlink(missing_ok=True)
            if name == "check-pod-running":
                check(f"{name}: non-numeric previous_generation rejected",
                      r.returncode != 0, r.stdout)
            if name == "run-onboard" and have_jq:
                try:
                    wf = json.loads((work / "child-workflow.json").read_text())
                    params = wf["spec"]["arguments"]["parameters"]
                    got = {p["name"]: p["value"] for p in params}
                    ok = ([p["name"] for p in params] == ONBOARD_NAMES
                          and all(got[k] == payload for k in
                                  ("team_name", "git_tag", "dockerfile_repo")))
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    r.stderr += repr(exc)
                check(f"{name}: payload {payload.splitlines()[0]!r} is verbatim "
                      "in child-workflow.json", ok, r.stderr)
                (work / "child-workflow.json").unlink(missing_ok=True)
        if name == "check-pod-running":
            for good in ("0", "7"):
                env = {**base_env, "PARAM_TEAM_NAME": "t", "PARAM_COMPONENT_NAME": "s",
                       "PARAM_PREVIOUS_GENERATION": good}
                r = run_sh(prelude, env, work, shell)
                check(f"{name}: previous_generation {good!r} accepted",
                      r.returncode == 0, r.stderr)

    # secret_env_vars loop of write-service-secrets, run with a terminator line.
    src = template("tpl-vault-write.yaml", "write-service-secrets")["script"]["source"]
    m = re.search(r'^(JSON_DATA="\{"\n.*?^SECRETS_EOF)$', src, re.S | re.M)
    check("extracted the secret loop", bool(m))
    if m:
        payload = f"A=1\nSECRETS_EOF\ntouch {canary}\nB=2"
        out = run_sh(m.group(1) + '\necho "$JSON_DATA"',
                     {**base_env, "PARAM_SECRET_ENV_VARS": payload}, work)
        check("secret loop: terminator line is data", not canary.exists(), out.stderr)
        check("secret loop: valid lines still parsed", '"A":"1"' in out.stdout, out.stdout)

    # write-platform-secret refuses an unsafe vault_path before any request.
    tmpl = template("tpl-vault-write.yaml", "write-platform-secret")
    src = tmpl["script"]["source"]
    m = re.search(r'^( *case "\$PARAM_VAULT_PATH" in.*?^ *esac)$', src, re.S | re.M)
    check("extracted the vault_path guard", bool(m))
    if m:
        for bad in ("../x", "/abs", "a\nb", "a b", "a;b", ""):
            r = run_sh(m.group(1), {**base_env, "PARAM_VAULT_PATH": bad}, work)
            check(f"vault_path {bad!r} rejected", r.returncode != 0)
        r = run_sh(m.group(1), {**base_env, "PARAM_VAULT_PATH": "teams/a/b-c_d"}, work)
        check("valid vault_path accepted", r.returncode == 0)

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
