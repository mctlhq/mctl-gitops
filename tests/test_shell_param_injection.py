#!/usr/bin/env python3
"""Executable reproduction for gitops#992: parameters must reach sh as data.

Renders a template's env the way Argo does (text replacement of
{{inputs|workflow.parameters.X}}), runs the parameter-reading prelude of the
script under sh, and asserts an injected `touch $CANARY` never runs. A control
case on the old interpolated form proves the harness can detect injection.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CT = ROOT / "platform-gitops/argo-workflows/cluster-templates"
PH = re.compile(r"\{\{(?:inputs|workflow)\.parameters\.([A-Za-z0-9_.-]+)\}\}")

# (file, template, text of the first line that is NOT part of the prelude)
CASES = [
    ("tpl-validate-tenant.yaml", "validate", "# ── 3. Clone"),
    ("tpl-git-commit.yaml", "commit-service", "apk add"),
    ("tpl-vault-write.yaml", "write-service-secrets", "echo \"🔐 Authenticating"),
    ("tpl-vault-write.yaml", "delete-service-secrets", "SA_TOKEN="),
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


def run_sh(script, env, cwd):
    return subprocess.run(["sh", "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True)


failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


with tempfile.TemporaryDirectory() as d:
    work = pathlib.Path(d)
    canary = work / "canary"
    base_env = {"PATH": os.environ["PATH"]}

    # Control: the old shape executes the payload.
    old = PH.sub(lambda m: f'"; touch {canary}; #', 'X="{{inputs.parameters.p}}"')
    run_sh(old, base_env, work)
    check("control: interpolated form runs the payload", canary.exists())
    canary.unlink(missing_ok=True)

    for fname, name, stop in CASES:
        tmpl = template(fname, name)
        src = tmpl["script"]["source"]
        check(f"{name}: no placeholder in script.source", not PH.search(src))
        lines = src.split("\n")
        idx = next(i for i, l in enumerate(lines) if l.strip().startswith(stop))
        prelude = "\n".join(lines[:idx])
        for payload in payloads(canary):
            env = dict(base_env)
            for e in tmpl["script"].get("env") or []:
                env[e["name"]] = PH.sub(lambda m: payload, e.get("value", ""))
            # `set -e` in the prelude may stop it early on a validation
            # failure; that is fine, only the canary matters.
            run_sh(prelude, env, work)
            check(f"{name}: payload {payload.splitlines()[0]!r} is data",
                  not canary.exists())
            canary.unlink(missing_ok=True)

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
