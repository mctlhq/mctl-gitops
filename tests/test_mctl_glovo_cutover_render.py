#!/usr/bin/env python3
"""The C2 cutover wiring is dark by default and exact when lit (mctl-gitops#2777).

Pins, on the bootstrap render:
  - the default render has no Ingress, no link variables, no consent variables
    on mctl-api and the cohort size is 10 on the service;
  - capacity is ONE value: the service and mctl-api read the same number, and
    anything outside 1..20 or not a whole number fails the render;
  - linkLogin sets exactly the two optional link variables (and nothing when
    off), with the audience derived from the host and a bounded login age;
  - ingress needs c2, a host owned by the service namespace in
    reservedPlatformHosts, and trusted proxies; it renders ONE Ingress with the
    three public paths (never the kill switch path or the health paths) and a
    Traefik-only source in the server policy, and it adds nothing else;
  - apiConsent adds exactly the consent env and the reader Secret to mctl-api,
    and a Secret named in envFromOptionalSecrets, with no literal identifier.

Run: python3 tests/test_mctl_glovo_cutover_render.py   (needs helm, pyyaml)
"""
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
SVC = "templates/mctl-platform/mctl-glovo.yaml"
API = "templates/mctl-platform/mctl-api.yaml"
API_SECRETS = "templates/mctl-platform/mctl-api-c2-consent.yaml"
BASE = ["--set", "mctlGlovo.deploy=true", "--set", "mctlGlovo.c2=true", "--set", "mctlGlovo.allowlist=true",
        "--set", "mctlGlovo.consent=true", "--set", "mctlGlovo.control=true"]
HOSTS = "reservedPlatformHosts:\n  glovo.mctl.ai: [mctl-glovo]\n"
PROXIES = ["--set", "mctlGlovo.trustedProxies=10.42.0.0/16"]
failures: list[str] = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def helm(show, *args, extra_values=None):
    cmd = ["helm", "template", "t", str(CHART), "--show-only", show, *args]
    tmp = None
    if extra_values:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        tmp.write(extra_values)
        tmp.close()
        cmd += ["-f", tmp.name]
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    finally:
        if tmp:
            pathlib.Path(tmp.name).unlink()


def docs(r):
    return [d for d in yaml.safe_load_all(r.stdout) if d]


def server_env(ds):
    dep = [d for d in ds if d["kind"] == "Deployment"][0]
    c = [c for c in dep["spec"]["template"]["spec"]["containers"] if c["name"] == "server"][0]
    return {e["name"]: e.get("value") for e in c["env"]}


def api_values(*args, extra_values=None):
    r = helm(API, *args, extra_values=extra_values)
    if r.returncode:
        return None, r
    app = [d for d in docs(r) if d["kind"] == "Application"][0]
    return yaml.safe_load(app["spec"]["sources"][0]["helm"]["values"]), r


def fails(show, *args, why, extra_values=None):
    r = helm(show, *args, extra_values=extra_values)
    check(r.returncode != 0 and why in r.stderr, f"expected a render failure containing {why!r}, got rc={r.returncode} {r.stderr[-160:]!r}")


# 1. dark by default
r = helm(SVC)
check(r.returncode == 0, f"default render failed: {r.stderr[-200:]}")
kinds = {d["kind"] for d in docs(r)}
check(kinds <= {"Namespace", "ServiceAccount", "NetworkPolicy"}, f"default render has extra kinds {kinds}")
v, r = api_values()
check(v is not None, f"default mctl-api render failed: {r.stderr[-200:]}")
if v:
    check(not any(k.startswith("GLOVO_CONSENT") or k == "GLOVO_C2_CAPACITY" for k in v["env"]),
          "default mctl-api env carries consent or capacity variables")
    check("mctl-api-glovo-consent" not in v.get("envFromOptionalSecrets", []), "default mctl-api reads the consent Secret")
check("mctl-api-glovo-consent" not in helm(API_SECRETS).stdout, "default render has the consent ExternalSecret")

# 2. every existing switch on, new ones off: no new surface, capacity 1
r = helm(SVC, *BASE)
check(r.returncode == 0, f"all-existing-switches render failed: {r.stderr[-200:]}")
ds = docs(r)
env = server_env(ds)
check(env.get("GLOVO_C2_CAPACITY") == "1", f"default capacity is {env.get('GLOVO_C2_CAPACITY')!r}, want '1'")
check(not [k for k in env if k.startswith("GLOVO_LINK")], f"link variables set with the switches off: {[k for k in env if k.startswith('GLOVO_LINK')]}")
check("Ingress" not in {d["kind"] for d in ds}, "an Ingress renders with the ingress switch off")
srv = [d for d in ds if d["kind"] == "NetworkPolicy" and d["metadata"]["name"] == "allow-server"][0]
check(all("traefik" not in str(rule) for rule in srv["spec"].get("ingress", [])), "server policy has a Traefik source with ingress off")

# 3. capacity: one value for both services, bounded, whole
for cap in ("1", "3", "20"):
    r = helm(SVC, *BASE, "--set", f"mctlGlovo.capacity={cap}")
    check(r.returncode == 0 and server_env(docs(r)).get("GLOVO_C2_CAPACITY") == cap, f"service capacity {cap} not rendered")
    v, _ = api_values("--set", "mctlGlovo.apiConsent=true", "--set", f"mctlGlovo.capacity={cap}")
    check(v and v["env"].get("GLOVO_C2_CAPACITY") == cap, f"mctl-api capacity {cap} differs from the service")
for bad in ("0", "21", "-1", "10.5", "abc"):
    fails(SVC, "--set", f"mctlGlovo.capacity={bad}", why="capacity value must be a whole number")
    fails(API, "--set", "mctlGlovo.apiConsent=true", "--set", f"mctlGlovo.capacity={bad}", why="capacity value must be a whole number")

# 4. link login
r = helm(SVC, *BASE, "--set", "mctlGlovo.linkLogin=true")
env = server_env(docs(r)) if r.returncode == 0 else {}
check(r.returncode == 0, f"linkLogin render failed: {r.stderr[-200:]}")
check(env.get("GLOVO_LINK_RESOURCE") == "https://glovo.mctl.ai/link", f"link resource {env.get('GLOVO_LINK_RESOURCE')!r}")
check(env.get("GLOVO_LINK_RESOURCE") != "https://glovo.mctl.ai/mcp", "link audience equals the MCP resource")
check(env.get("GLOVO_LINK_MAX_AUTH_AGE") == "5m", f"link max age {env.get('GLOVO_LINK_MAX_AUTH_AGE')!r}")
fails(SVC, "--set", "mctlGlovo.linkLogin=true", why="linkLogin switch requires the c2 switch")
for bad in ("16m", "901s", "0m", "5h", "1.5m", "5"):
    fails(SVC, *BASE, "--set", "mctlGlovo.linkLogin=true", "--set", f"mctlGlovo.linkMaxAuthAge={bad}", why="linkMaxAuthAge value")
r = helm(SVC, *BASE, "--set", "mctlGlovo.linkLogin=true", "--set", "mctlGlovo.linkMaxAuthAge=15m")
check(r.returncode == 0, "15m is the allowed maximum")

# 5. ingress
fails(SVC, "--set", "mctlGlovo.ingress=true", why="ingress switch requires the c2 switch")
fails(SVC, *BASE, "--set", "mctlGlovo.ingress=true", *PROXIES, why="owner in reservedPlatformHosts", extra_values=None)
fails(SVC, *BASE, "--set", "mctlGlovo.ingress=true", why="trustedProxies", extra_values=HOSTS)
r = helm(SVC, *BASE, "--set", "mctlGlovo.ingress=true", *PROXIES, extra_values=HOSTS)
check(r.returncode == 0, f"ingress render failed: {r.stderr[-200:]}")
if r.returncode == 0:
    ds = docs(r)
    ings = [d for d in ds if d["kind"] == "Ingress"]
    check(len(ings) == 1, f"expected one Ingress, got {len(ings)}")
    if ings:
        rules = ings[0]["spec"]["rules"]
        check(len(rules) == 1 and rules[0]["host"] == "glovo.mctl.ai", f"ingress hosts {[x.get('host') for x in rules]}")
        paths = [p["path"] for p in rules[0]["http"]["paths"]]
        check(paths == ["/mcp", "/link", "/.well-known/oauth-protected-resource"], f"ingress paths {paths}")
        check(not [p for p in paths if "internal" in p or "livez" in p or "readyz" in p or p == "/"], "ingress exposes an internal path")
        check("tls" not in ings[0]["spec"], "ingress unexpectedly carries a tls block")
        check(ings[0]["metadata"]["namespace"] == "mctl-glovo", "ingress outside the service namespace")
    srv = [d for d in ds if d["kind"] == "NetworkPolicy" and d["metadata"]["name"] == "allow-server"][0]
    srcs = [rule["from"][0]["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] for rule in srv["spec"]["ingress"]]
    check(srcs == ["mctl-api", "traefik"], f"server policy ingress sources {srcs}, want mctl-api (control) then traefik")
    check("Ingress" in srv["spec"]["policyTypes"], "server policy does not list the Ingress policy type")
    check(server_env(ds).get("GLOVO_LINK_TRUSTED_PROXIES") == "10.42.0.0/16", "trusted proxies not set with the ingress")
    check("GLOVO_LINK_RESOURCE" not in server_env(ds), "link variables set by the ingress switch alone")

# 6. mctl-api consent side
v, r = api_values("--set", "mctlGlovo.apiConsent=true")
check(v is not None, f"apiConsent render failed: {r.stderr[-200:]}")
if v:
    env = v["env"]
    check(env.get("GLOVO_CONSENT_ENABLED") == "true", "consent not enabled on mctl-api")
    check(env.get("GLOVO_C2_CAPACITY") == "1", "mctl-api capacity differs from the default 1")
    check("GLOVO_CONSENT_SERVICE_SUBJECT" not in env and "GLOVO_CONSENT_SERVICE_PROVIDER" not in env,
          "a reader identity is a literal in the public repo")
    check("mctl-api-glovo-consent" in v["envFromOptionalSecrets"], "the consent Secret is not read by mctl-api")
r = helm(API_SECRETS, "--set", "mctlGlovo.apiConsent=true")
es = [d for d in docs(r) if d["kind"] == "ExternalSecret" and d["metadata"]["name"] == "mctl-api-glovo-consent"]
check(len(es) == 1, "expected the consent reader ExternalSecret")
if es:
    check(es[0]["metadata"]["namespace"] == "mctl-api", "reader ExternalSecret outside mctl-api")
    keys = {d["remoteRef"]["key"] for d in es[0]["spec"]["data"]}
    check(keys == {"platform/mctl-api/glovo-consent"}, f"reader ExternalSecret reads {keys}")
    check(all(d["remoteRef"]["key"].startswith("platform/mctl-api/") for d in es[0]["spec"]["data"]),
          "reader ExternalSecret reads outside platform/mctl-api/")

if failures:
    print("\n".join("FAIL " + f for f in failures), file=sys.stderr)
    sys.exit(1)
print("ok: C2 cutover render")
