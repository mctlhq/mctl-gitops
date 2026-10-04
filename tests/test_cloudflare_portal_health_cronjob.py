"""In-cluster MCP portal health check: the CronJob must run what Git says.

scripts/cloudflare-portal-health.py reaches the cluster as a generated
ConfigMap (blackbox/cloudflare-portal-health-script.yaml), and its token as a
Secret written by an ExternalSecret. A copy that drifts would run an old
script and stay green doing it; a Secret name or key that drifts would leave
the Job unable to start, which the staleness alert catches, but later.

C1. The ConfigMap holds scripts/cloudflare-portal-health.py byte for byte.
C2. The image is pinned by digest.
C3. The token reaches the container only through a secretKeyRef, and that
    reference names exactly the Secret and key the ExternalSecret writes.
C4. The account is the one cloudflare-portal-health.yml checks.
C5. The CronJob pushes to the job the alert rules select.

Regenerate the ConfigMap after editing the script:
    python3 tests/test_cloudflare_portal_health_cronjob.py --write

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_cloudflare_portal_health_cronjob.py
"""
from __future__ import annotations

import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = os.path.join(ROOT, "platform-gitops", "infra-components", "observability")
SCRIPT = os.path.join(ROOT, "scripts", "cloudflare-portal-health.py")
CONFIGMAP = os.path.join(OBS, "blackbox", "cloudflare-portal-health-script.yaml")
CRONJOB = os.path.join(OBS, "blackbox", "cloudflare-portal-health.yaml")
EXTERNALSECRET = os.path.join(OBS, "secrets", "cloudflare-portal-health-externalsecret.yaml")
RULES = os.path.join(OBS, "vm-rules", "cloudflare-portal-health.yaml")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "cloudflare-portal-health.yml")

HEADER = """\
# GENERATED from scripts/cloudflare-portal-health.py -- do not edit by hand.
# Regenerate: python3 tests/test_cloudflare_portal_health_cronjob.py --write
# CI (validate-manifests.yml) fails when this copy differs from the script.
"""


def render_configmap(script: str) -> str:
    body = "".join(("    " + line) if line.strip() else "\n" for line in script.splitlines(keepends=True))
    return (
        HEADER
        + "apiVersion: v1\n"
        + "kind: ConfigMap\n"
        + "metadata:\n"
        + "  name: cloudflare-portal-health-script\n"
        + "  namespace: monitoring\n"
        + "  labels:\n"
        + "    app: cloudflare-portal-health\n"
        + "data:\n"
        + "  cloudflare-portal-health.py: |\n"
        + body
    )


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        (doc,) = [d for d in yaml.safe_load_all(f) if d]
    return doc


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

    with open(CONFIGMAP, encoding="utf-8") as f:
        cm_text = f.read()
    hint = "run: python3 tests/test_cloudflare_portal_health_cronjob.py --write"
    check(yaml.safe_load(cm_text)["data"]["cloudflare-portal-health.py"] == script,
          "C1 the ConfigMap holds the script byte for byte", hint)
    check(cm_text == render_configmap(script), "C1 the ConfigMap file is exactly the generated one", hint)

    cj = load(CRONJOB)
    (c,) = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    check(re.search(r"@sha256:[0-9a-f]{64}$", c["image"]) is not None, "C2 the image is pinned by digest", c["image"])

    es = load(EXTERNALSECRET)
    es_secret = es["spec"]["target"]["name"]
    es_keys = {d["secretKey"] for d in es["spec"]["data"]}
    env = {e["name"]: e for e in c.get("env", [])}
    tok = env.get("CLOUDFLARE_API_TOKEN", {})
    ref = (tok.get("valueFrom") or {}).get("secretKeyRef") or {}
    check("value" not in tok and ref.get("name") == es_secret and ref.get("key") in es_keys,
          "C3 the token comes only from the ExternalSecret's Secret and key",
          f"secretKeyRef {ref!r}, ExternalSecret writes {es_secret!r} {sorted(es_keys)}")
    check(not ref.get("optional"), "C3 the token reference is not optional")

    with open(WORKFLOW, encoding="utf-8") as f:
        wf_account = yaml.safe_load(f)["env"]["CLOUDFLARE_ACCOUNT_ID"]
    check(arg(c, "--account") == wf_account, "C4 the account is the one the workflow checks",
          f"CronJob {arg(c, '--account')!r}, workflow {wf_account!r}")

    with open(RULES, encoding="utf-8") as f:
        rules = f.read()
    job = arg(c, "--push-job") or "cloudflare_portal_health"
    check(f'job="{job}"' in rules, "C5 the CronJob pushes to the job the rules select", f"got {job!r}")

    print(f"\n{'all checks passed' if not failures else f'{len(failures)} check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
