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
# templates that run something before they read their parameters. Both must be
# executed lines, not comments: comments get reworded in passing (#1966 did it
# to commit-service) and a moved marker silently changes what the case covers.
CASES = [
    ("tpl-validate-tenant.yaml", "validate", "echo \"📥 Cloning mctl-gitops for validation"),
    ("tpl-git-commit.yaml", "commit-service", "mkdir -p ~/.ssh"),
    ("tpl-vault-write.yaml", "write-service-secrets", "echo \"🔐 Authenticating",
     "TEAM=\"$PARAM_TEAM_NAME\""),
    ("tpl-vault-write.yaml", "delete-service-secrets",
     "SA_NS=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)",
     "TEAM=\"$PARAM_TEAM_NAME\""),
    ("wft-smoke-test.yaml", "run-onboard", "WF_NAME=$(kubectl create"),
    ("wft-smoke-test.yaml", "check-pod-running", "check_missing_secret_reference()"),
    ("wft-create-tenant.yaml", "create-vault-policy", "echo \"Authenticating"),
    ("wft-delete-tenant-safe.yaml", "delete-vault-policy", "echo \"Authenticating"),
    ("wft-delete-tenant.yaml", "delete-vault-policy", "echo \"Authenticating"),
    ("wft-deploy-service.yaml", "refresh-apps-appset", "echo \"Triggering hard refresh"),
    ("wft-deploy-service.yaml", "check-image-user", "git clone --depth=1"),
    ("wft-provision-database.yaml", "do-provision", "echo \"🔐 Authenticating with Vault",
     "TEAM=\"$PARAM_TEAM_NAME\""),
    ("wft-retire-service.yaml", "cleanup-db-from-gitops", "mkdir -p ~/.ssh",
     "TEAM=\"$PARAM_TEAM_NAME\""),
]


# Valid values per parameter for the liveness run below; anything not listed
# gets BENIGN_DEFAULT. A prelude must reach its end with these, which proves the
# payload runs actually execute the parameter reads instead of dying on an
# earlier command (an `apk add` before the first PARAM_* line made three cases
# pass without reading a single parameter, #1838).
BENIGN_DEFAULT = "okname"
BENIGN = {"dockerfile_repo": "org/repo", "host": "svc.example.com", "port": "8080", "previous_generation": "7",
          "git_tag": "v1.2.3", "image_tag": "auto", "min_replicas": "1",
          "max_replicas": "2", "cpu_threshold": "80"}
SENTINEL = "__PRELUDE_END__"


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
    # run-onboard's prelude needs jq; without it the case would silently stop
    # before the child-workflow.json assertions, so a missing jq is a failure.
    if shutil.which("jq") is None:
        sys.exit("jq is required: run-onboard's child-workflow.json checks need it")
    have_jq = True

    for fname, name, stop, *rest in CASES:
        check(f"{name}: prelude markers are executed lines, not comments",
              not any(m.lstrip().startswith("#") for m in [stop] + rest), f"{[stop] + rest}")
        tmpl = template(fname, name)
        src = tmpl["script"]["source"]
        shell = (tmpl["script"].get("command") or ["sh"])[0]
        check(f"{name}: no placeholder in script.source", not PH.search(src))
        lines = src.split("\n")
        idx = next(i for i, l in enumerate(lines) if l.strip().startswith(stop))
        first = 0
        if rest:
            first = next(i for i, l in enumerate(lines) if l.strip().startswith(rest[0]))
        body = lines[first:idx]
        prelude = "\n".join(["set -e"] + body if rest else body)

        benign = dict(base_env)
        for e in tmpl["script"].get("env") or []:
            benign[e["name"]] = PH.sub(lambda m: BENIGN.get(m.group(1), BENIGN_DEFAULT),
                                       e.get("value", ""))
        r = run_sh(prelude + f"\necho {SENTINEL}", benign, work, shell)
        check(f"{name}: prelude reaches its end with valid values (case is live)",
              SENTINEL in r.stdout, f"rc={r.returncode} {r.stderr.strip()[-300:]}")
        (work / "child-workflow.json").unlink(missing_ok=True)
        for payload in payloads(canary):
            env = dict(base_env)
            for e in tmpl["script"].get("env") or []:
                env[e["name"]] = PH.sub(lambda m: payload, e.get("value", ""))
            # Render the source the way Argo does, so a placeholder that comes
            # back into the script text trips the canary, not only the static
            # check above. `set -e` may stop the prelude early on a validation
            # failure; that is fine, only the canary matters.
            r = run_sh(PH.sub(lambda m: payload, prelude), env, work, shell)
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

    # write-service-secrets parses secret_env_vars in a quoted here-document
    # program that reads the value from the environment; it is exercised
    # against a fake Vault, terminator line and code-shaped values included,
    # by tests/test_tpl_vault_write_parse.py. Here: the value is never in the
    # program text.
    src = template("tpl-vault-write.yaml", "write-service-secrets")["script"]["source"]
    m = re.search(r"^python3 - <<'PY'\n(.*?)\n^PY$", src, re.S | re.M)
    check("extracted the secret program", bool(m))
    if m:
        check("secret program reads secret_env_vars from the environment",
              'os.environ["PARAM_SECRET_ENV_VARS"]' in m.group(1)
              and "$PARAM_SECRET_ENV_VARS" not in m.group(1))

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
