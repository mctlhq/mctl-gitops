"""Render base-service's workContext gate both ways and assert it behaves.

mctlhq/mctl-telegram#443 shipped the Telegram work-context adapter and
mctlhq/mctl-gitops#1405 wires the config it reads (WORK_CONTEXT_ENABLED,
MCTL_WORK_ITEM_TENANT, MCTL_API_BASE_URL, MCTL_SURFACE_TELEGRAM_TOKEN) into
this chart, off by default. This test is the workContext sibling of
test_base_service_otel_env.py -- same defect class (a Deployment-only env
block is invisible to a blueGreen Rollout, mctlhq/mctl-gitops#1189), same
fix (one shared `base-service.env` partial), same test shape (render both
workload kinds from the same values and compare).

Run: python3 tests/test_base_service_work_context_env.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
WORK_CONTEXT_KEYS = {
    "WORK_CONTEXT_ENABLED",
    "MCTL_WORK_ITEM_TENANT",
    "MCTL_API_BASE_URL",
    "MCTL_SURFACE_TELEGRAM_TOKEN",
}

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values, name="test", namespace="labs"):
    """helm template the chart with `values` merged over the chart defaults."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(values, fh)
        path = fh.name
    proc = subprocess.run(
        ["helm", "template", name, str(CHART), "-f", path,
         "--namespace", namespace],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"helm template failed for {json.dumps(values)}:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def render_fail(values, name="test", namespace="labs"):
    """helm template the chart, asserting it fails, and return stderr."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(values, fh)
        path = fh.name
    proc = subprocess.run(
        ["helm", "template", name, str(CHART), "-f", path,
         "--namespace", namespace],
        capture_output=True, text=True)
    if proc.returncode == 0:
        raise AssertionError(
            f"expected helm template to fail for {json.dumps(values)}, "
            f"but it rendered successfully")
    return proc.stderr


def workload(docs):
    """The single Deployment or Rollout in a rendering, and its env list."""
    found = [d for d in docs if d.get("kind") in ("Deployment", "Rollout")]
    assert len(found) == 1, f"expected one workload, got {[d['kind'] for d in found]}"
    doc = found[0]
    container = doc["spec"]["template"]["spec"]["containers"][0]
    return doc["kind"], {e["name"]: e for e in container.get("env", [])}


def external_secret(docs, name):
    found = [d for d in docs
             if d.get("kind") == "ExternalSecret" and d["metadata"]["name"] == name]
    assert len(found) == 1, f"expected exactly one ExternalSecret {name!r}, got {len(found)}"
    return found[0]


BASE = {
    "image": {"repository": "ghcr.io/mctlhq/example", "tag": "1.0.0"},
}

WC_ON = {
    "enabled": True,
    "featureEnabled": True,
    "tenant": "acme",
    "apiBaseUrl": "https://api.mctl.ai",
    "tokenVaultKey": "secret/data/platform/mctl-api/surface-tokens",
    "tokenVaultProperty": "telegram-token",
}


# T1: gate off must render byte-identically whether or not a workContext key
# is present in the values file at all -- the whole point of a default-off
# wiring change is that it changes nothing until a service opts in.
docs_no_key = render({**BASE})
docs_key_present_off = render({**BASE, "workContext": {"enabled": False}})
for kind_docs, label in ((docs_no_key, "Deployment (no key)"),
                         (docs_key_present_off, "Deployment (key present, off)")):
    _, env = workload(kind_docs)
    check(not (WORK_CONTEXT_KEYS & set(env)),
          f"{label} carries work-context vars with the gate off: "
          f"{sorted(WORK_CONTEXT_KEYS & set(env))}")
    check(not any(d.get("kind") == "ExternalSecret"
                  and d["metadata"]["name"].endswith("-work-context")
                  for d in kind_docs),
          f"{label} renders a work-context ExternalSecret with the gate off")

# Also compare the two gate-off renders byte-for-byte via their raw docs list
# length and kinds -- the real byte-identical assertion (rendered YAML text)
# is exercised at the repo level (labs/mctl-telegram before/after); here we
# assert no extra document appears either way.
check(len(docs_no_key) == len(docs_key_present_off),
      "workContext key present-but-off renders a different document count "
      "than the key being absent entirely")

# T2: gate on renders the ExternalSecret + all 4 env vars, existing
# env/envFrom/extraExternalSecrets untouched.
docs_on = render({
    **BASE,
    "workContext": WC_ON,
    "env": {"APP_ENV": "production"},
    "envFrom": [{"secretRef": {"name": "some-other-secret"}}],
})
kind, env = workload(docs_on)
check(WORK_CONTEXT_KEYS <= set(env),
      f"gate on is missing {sorted(WORK_CONTEXT_KEYS - set(env))}")
check(env.get("APP_ENV", {}).get("value") == "production",
      "pre-existing env entry was disturbed by workContext wiring")
found_envfrom = [d for d in docs_on if d["kind"] == kind][0][
    "spec"]["template"]["spec"]["containers"][0].get("envFrom")
check(found_envfrom == [{"secretRef": {"name": "some-other-secret"}}],
      f"envFrom was disturbed: {found_envfrom}")

es = external_secret(docs_on, "test-base-service-work-context")
check(es["spec"]["target"]["name"] == "test-base-service-work-context",
      "ExternalSecret target name does not match its own metadata.name")
check(es["spec"]["target"]["creationPolicy"] == "Owner",
      "ExternalSecret target.creationPolicy is not Owner")
data = es["spec"]["data"]
check(len(data) == 1, f"expected exactly one data entry, got {len(data)}")
check(data[0]["secretKey"] == "MCTL_SURFACE_TELEGRAM_TOKEN",
      f"unexpected secretKey {data[0]['secretKey']!r}")
check(data[0]["remoteRef"]["key"] == "secret/data/platform/mctl-api/surface-tokens",
      f"unexpected remoteRef.key {data[0]['remoteRef']['key']!r}")
check(data[0]["remoteRef"]["property"] == "telegram-token",
      f"unexpected remoteRef.property {data[0]['remoteRef']['property']!r}")

check(env["WORK_CONTEXT_ENABLED"].get("value") == "true",
      f"WORK_CONTEXT_ENABLED={env['WORK_CONTEXT_ENABLED']!r}")
check(env["MCTL_WORK_ITEM_TENANT"].get("value") == "acme",
      f"MCTL_WORK_ITEM_TENANT={env['MCTL_WORK_ITEM_TENANT']!r}")
check(env["MCTL_API_BASE_URL"].get("value") == "https://api.mctl.ai",
      f"MCTL_API_BASE_URL={env['MCTL_API_BASE_URL']!r}")
token_entry = env["MCTL_SURFACE_TELEGRAM_TOKEN"]
check("valueFrom" in token_entry and "secretKeyRef" in token_entry["valueFrom"],
      f"MCTL_SURFACE_TELEGRAM_TOKEN is not a secretKeyRef: {token_entry}")
check(token_entry["valueFrom"]["secretKeyRef"].get("name") == "test-base-service-work-context",
      f"secretKeyRef.name does not match the ExternalSecret's target: {token_entry}")
check(token_entry["valueFrom"]["secretKeyRef"].get("optional") is True,
      f"secretKeyRef.optional is not true: {token_entry}")

# apiBaseUrl empty => MCTL_API_BASE_URL must not render at all (leave
# mctl-telegram's own default).
_, env_noapi = workload(render({
    **BASE,
    "workContext": {**WC_ON, "apiBaseUrl": ""},
}))
check("MCTL_API_BASE_URL" not in env_noapi,
      f"MCTL_API_BASE_URL rendered with apiBaseUrl empty: {env_noapi.get('MCTL_API_BASE_URL')}")
check({"WORK_CONTEXT_ENABLED", "MCTL_WORK_ITEM_TENANT", "MCTL_SURFACE_TELEGRAM_TOKEN"} <= set(env_noapi),
      "the other 3 work-context vars should still render with apiBaseUrl empty")

# T4: both Deployment and Rollout (blueGreen) get the same 4 env entries.
_, dep_env = workload(render({**BASE, "workContext": WC_ON}))
_, rol_env = workload(render({
    **BASE, "blueGreen": {"enabled": True}, "workContext": WC_ON}))
dep_wc = {k: v for k, v in dep_env.items() if k in WORK_CONTEXT_KEYS}
rol_wc = {k: v for k, v in rol_env.items() if k in WORK_CONTEXT_KEYS}
check(dep_wc == rol_wc,
      f"Deployment and Rollout work-context env differ:\n  only in Deployment: "
      f"{sorted(set(dep_wc) - set(rol_wc))}\n  only in Rollout: "
      f"{sorted(set(rol_wc) - set(dep_wc))}")
check(WORK_CONTEXT_KEYS <= set(rol_wc),
      f"Rollout is missing {sorted(WORK_CONTEXT_KEYS - set(rol_wc))}")

# T5a: an explicit env: entry wins over the workContext default, and no
# duplicate name is rendered.
docs = render({
    **BASE,
    "workContext": WC_ON,
    "env": {"MCTL_WORK_ITEM_TENANT": "explicit-tenant", "WORK_CONTEXT_ENABLED": "false"},
})
kind, env = workload(docs)
check(env["MCTL_WORK_ITEM_TENANT"].get("value") == "explicit-tenant",
      f"explicit env did not win: {env['MCTL_WORK_ITEM_TENANT']}")
check(env["WORK_CONTEXT_ENABLED"].get("value") == "false",
      f"explicit env did not win: {env['WORK_CONTEXT_ENABLED']}")
names = [e["name"] for e in
         [d for d in docs if d["kind"] == kind][0]
         ["spec"]["template"]["spec"]["containers"][0]["env"]]
check(len(names) == len(set(names)),
      f"duplicate env names rendered: "
      f"{sorted(n for n in set(names) if names.count(n) > 1)}")

# T5a-bis: the same, through envValueFrom -- the harder-to-spot duplicate.
docs = render({
    **BASE,
    "workContext": WC_ON,
    "envValueFrom": {
        "MCTL_WORK_ITEM_TENANT": {"fieldRef": {"fieldPath": "metadata.namespace"}}},
})
kind, _ = workload(docs)
entries = ([d for d in docs if d["kind"] == kind][0]
           ["spec"]["template"]["spec"]["containers"][0]["env"])
names = [e["name"] for e in entries]
check(names.count("MCTL_WORK_ITEM_TENANT") == 1,
      f"MCTL_WORK_ITEM_TENANT rendered {names.count('MCTL_WORK_ITEM_TENANT')} times "
      f"when set via envValueFrom")
check(all("valueFrom" in e for e in entries if e["name"] == "MCTL_WORK_ITEM_TENANT"),
      "the service's valueFrom was overridden by the workContext default")

# T5b: empty tokenVaultKey/tokenVaultProperty must fail the render with a
# named error, not silently emit an ExternalSecret with an empty remoteRef.
err = render_fail({**BASE, "workContext": {**WC_ON, "tokenVaultKey": ""}})
check("tokenVaultKey" in err, f"error does not name tokenVaultKey: {err}")

err = render_fail({**BASE, "workContext": {**WC_ON, "tokenVaultProperty": ""}})
check("tokenVaultProperty" in err, f"error does not name tokenVaultProperty: {err}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("base-service workContext env: Deployment and Rollout agree, default-off holds")
