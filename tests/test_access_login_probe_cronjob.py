"""In-cluster Access login probe (#1329): the CronJob must probe what Git says.

The probe script lives in scripts/access-login-probe.py and reaches the
cluster as a ConfigMap, and the client id it expects is read from
infrastructure/cloudflare/account/zitadel-idp.tf when it runs from a checkout.
The CronJob has neither file, so it carries copies: the script inline in
blackbox/access-login-probe-script.yaml, the client id as an argument in
blackbox/access-login-probe.yaml. A copy that drifts would probe for a client
that no longer exists, or run yesterday's script, and stay green doing it.

P1. The ConfigMap holds scripts/access-login-probe.py byte for byte.
P2. The scheduled CronJob's --client-id equals the Cloudflare root's
    zitadel_access_client_id default, parsed by the script's own parser.
P3. The red-test CronJob probes a client id that is NOT the real one, is
    suspended, and pushes to its own job, so it can neither page nor overwrite
    the real series.
P4. Every probe container image is pinned by digest.
P5. The scheduled CronJob pushes to the job the alert rules select.

Regenerate the ConfigMap after editing the script:
    python3 tests/test_access_login_probe_cronjob.py --write

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_access_login_probe_cronjob.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "access-login-probe.py")
BLACKBOX = os.path.join(ROOT, "platform-gitops", "infra-components", "observability", "blackbox")
CONFIGMAP = os.path.join(BLACKBOX, "access-login-probe-script.yaml")
CRONJOBS = os.path.join(BLACKBOX, "access-login-probe.yaml")
TF = os.path.join(ROOT, "infrastructure", "cloudflare", "account", "zitadel-idp.tf")
RULES = os.path.join(
    ROOT, "platform-gitops", "infra-components", "observability", "vm-rules", "access-login-probe.yaml"
)

HEADER = """\
# GENERATED from scripts/access-login-probe.py -- do not edit by hand.
# Regenerate: python3 tests/test_access_login_probe_cronjob.py --write
# CI (validate-manifests.yml) fails when this copy differs from the script.
"""


def render_configmap(script: str) -> str:
    body = "".join(("    " + line) if line.strip() else "\n" for line in script.splitlines(keepends=True))
    return (
        HEADER
        + "apiVersion: v1\n"
        + "kind: ConfigMap\n"
        + "metadata:\n"
        + "  name: access-login-probe-script\n"
        + "  namespace: monitoring\n"
        + "  labels:\n"
        + "    app: access-login-probe\n"
        + "data:\n"
        + "  access-login-probe.py: |\n"
        + body
    )


def load_probe_module():
    spec = importlib.util.spec_from_file_location("access_login_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolves the class's module by name
    spec.loader.exec_module(mod)
    return mod


def cronjobs() -> dict[str, dict]:
    with open(CRONJOBS, encoding="utf-8") as f:
        docs = [d for d in yaml.safe_load_all(f) if d]
    return {d["metadata"]["name"]: d for d in docs if d.get("kind") == "CronJob"}


def container(cj: dict) -> dict:
    (c,) = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    return c


def arg(c: dict, name: str) -> str | None:
    args = c.get("args", [])
    return args[args.index(name) + 1] if name in args else None


def main() -> int:
    with open(SCRIPT, encoding="utf-8") as f:
        script = f.read()
    if "--write" in sys.argv[1:]:
        with open(CONFIGMAP, "w", encoding="utf-8") as f:
            f.write(render_configmap(script))
        print(f"wrote {os.path.relpath(CONFIGMAP, ROOT)}")
        return 0

    failures: list[str] = []

    def check(ok: bool, name: str, detail: str = "") -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail and not ok else ''}")
        if not ok:
            failures.append(name)

    # P1
    with open(CONFIGMAP, encoding="utf-8") as f:
        cm_text = f.read()
    cm = yaml.safe_load(cm_text)
    check(cm["data"]["access-login-probe.py"] == script,
          "P1 the ConfigMap holds the script byte for byte",
          "run: python3 tests/test_access_login_probe_cronjob.py --write")
    check(cm_text == render_configmap(script), "P1 the ConfigMap file is exactly the generated one",
          "run: python3 tests/test_access_login_probe_cronjob.py --write")

    probe = load_probe_module()
    with open(TF, encoding="utf-8") as f:
        want = probe.parse_client_id_default(f.read(), TF)
    jobs = cronjobs()
    real, red = jobs.get("access-login-probe"), jobs.get("access-login-probe-red")
    check(real is not None and red is not None, "both CronJobs exist", f"found {sorted(jobs)}")
    if real is None or red is None:
        return 1
    rc, dc = container(real), container(red)

    # P2
    check(arg(rc, "--client-id") == want, "P2 the scheduled probe expects the root's client id",
          f"CronJob {arg(rc, '--client-id')!r}, zitadel-idp.tf {want!r}")
    check(real["spec"].get("suspend") in (None, False), "P2 the scheduled probe is not suspended")

    # P3
    red_id = arg(dc, "--client-id")
    check(bool(red_id) and red_id.isdigit() and red_id != want,
          "P3 the red test expects a different, numeric client id", f"got {red_id!r}")
    check(red["spec"].get("suspend") is True, "P3 the red test is suspended (dispatch only)")
    check(arg(dc, "--push-job") not in (None, "access_login_probe"),
          "P3 the red test pushes to its own job", f"got {arg(dc, '--push-job')!r}")

    # P4
    for name, c in (("scheduled", rc), ("red", dc)):
        check(re.search(r"@sha256:[0-9a-f]{64}$", c["image"]) is not None,
              f"P4 the {name} image is pinned by digest", c["image"])

    # P5
    with open(RULES, encoding="utf-8") as f:
        rules = f.read()
    real_job = arg(rc, "--push-job") or "access_login_probe"
    check(real_job == "access_login_probe" and f'job="{real_job}"' in rules,
          "P5 the scheduled probe pushes to the job the rules select", f"got {real_job!r}")

    print(f"\n{'all checks passed' if not failures else f'{len(failures)} check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
