#!/usr/bin/env python3
"""Validate the inert Glovo M1 staging package (mctlhq/mctl-gitops#2470, P0).

  validate-glovo-m1-staging.py            check the repository tree
  validate-glovo-m1-staging.py --selftest prove each refusal fires

Exit 0 = pass, 6 = refused, 7 = could not observe. Anything unreadable is a
refusal or an unknown, never a pass.

Two independent halves:
  1. The staged package under deploy/staged/glovo-m1 must render, stay private
     where it must, and keep the fail-closed defaults.
  2. A leak guard: no Glovo host, workload, image or assistant namespace may
     appear in reconciled paths (platform-gitops/**, excluding agents-state/),
     except an exact line listed for its exact file in ALLOWED_LINES. Each
     activation PR adds only its own lines there, as its first commit, and
     the reviewer reads that diff first (runbook "Leak guard at activation").
     A matching path name, a matching line not in the set, or a match in a
     file not in the map still refuses; a provenance image never passes.
     gate.yaml is informational and is NEVER consulted as an unlock: a PR
     author can edit it, so it proves nothing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGED = "deploy/staged/glovo-m1"
RECONCILED = "platform-gitops"
REFUSED = 6
UNKNOWN = 7
HOST = "glovo.mctl.ai"
METADATA_PATH = "/.well-known/oauth-protected-resource"
LEAK = re.compile(r"glovo|mctl-assistants", re.IGNORECASE)
VALUES = {
    "facade": "facade/values.yaml",
    "provider": "provider-worker/values.yaml",
    "control": "control-worker/values.yaml",
}
TENANT = "provider-tenant/values.yaml"
SECRET_SHAPED = re.compile(r"(ghp_|github_pat_|hvs\.|AKIA|-----BEGIN)")

# Exact lines (whitespace included) that may match LEAK in one reconciled file,
# keyed by the path relative to the repository root. Empty until the first
# activation PR; each activation PR adds only its own lines, removal PRs delete
# them. Only lines that match LEAK are judged, so only those are listed: a
# neighbouring line without a Glovo or assistants reference (an ingress
# `paths:` entry such as `- /mcp`) needs no entry, and listing one would be a
# dead entry. The self-test pins this both ways.
ALLOWED_LINES: dict[str, frozenset[str]] = {
    # Step D1: the Basket canary managed roles (mctlhq/mctl-api#1006).
    "platform-gitops/infra-components/data/cnpg/shared/cluster.yaml": frozenset({
        "      - host mctl-api glovo_runtime all scram-sha-256",
        "      - host mctl-api glovo_migrator all scram-sha-256",
        "      - name: glovo_runtime",
        "          name: glovo-runtime-db-creds",
        "      - name: glovo_migrator",
        "          name: glovo-migrator-db-creds",
    }),
    "platform-gitops/infra-components/data/cnpg/shared/secrets.yaml": frozenset({
        "  name: glovo-runtime-db-creds",
        "    name: glovo-runtime-db-creds",
        "        key: platform/mctl-api/glovo-runtime-database",
        "  name: glovo-migrator-db-creds",
        "    name: glovo-migrator-db-creds",
        "        key: platform/mctl-api/glovo-migrator-database",
    }),
    # Step Z: the approval page client in zitadel-iac.
    "platform-gitops/helm-charts/zitadel-iac/iac/mctl-api.tf": frozenset({
        '    # The Glovo basket approval page client (mctl-api#1006). Nothing reads',
        '    # stays unmounted unless GLOVO_BASKET_UI_ENABLED is "true" (it is unset).',
        '    GLOVO_BASKET_UI_CLIENT_ID     = zitadel_application_oidc.mctl_api_glovo_basket.client_id',
        '    GLOVO_BASKET_UI_CLIENT_SECRET = zitadel_application_oidc.mctl_api_glovo_basket.client_secret',
        '  name       = "mctl-api-glovo-basket"',
        '  redirect_uris               = ["https://api.mctl.ai/glovo/basket/approvals/callback"]',
        '# The Glovo basket approval page (mctl-api#1006): an MCP client shows the',
        '# basket owner a link to api.mctl.ai/glovo/basket/approvals/{id}, and the',
        'resource "zitadel_application_oidc" "mctl_api_glovo_basket" {',
    }),
    "platform-gitops/helm-charts/zitadel-iac/iac/tests/mctl_api.tftest.hcl": frozenset({
        '      "GLOVO_BASKET_UI_CLIENT_ID",',
        '      "GLOVO_BASKET_UI_CLIENT_SECRET",',
        '    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["GLOVO_BASKET_UI_CLIENT_ID"]) == "glovo-basket-client-id" && nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["GLOVO_BASKET_UI_CLIENT_SECRET"]) == "glovo-basket-client-secret"',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.access_token_type == "OIDC_TOKEN_TYPE_BEARER"',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.app_type == "OIDC_APP_TYPE_WEB" && zitadel_application_oidc.mctl_api_glovo_basket.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC"',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.dev_mode == false',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.grant_types == tolist(["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]) && zitadel_application_oidc.mctl_api_glovo_basket.response_types == tolist(["OIDC_RESPONSE_TYPE_CODE"])',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.id_token_userinfo_assertion == true',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.name == "mctl-api-glovo-basket"',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.project_id == "mctl-api-project" && zitadel_application_oidc.mctl_api_glovo_basket.org_id == "100000000000000001"',
        '    condition     = zitadel_application_oidc.mctl_api_glovo_basket.redirect_uris == tolist(["https://api.mctl.ai/glovo/basket/approvals/callback"])',
        '    error_message = "The Glovo basket keys must carry the mctl-api-glovo-basket client\'s credentials, never another flow\'s."',
        '    error_message = "The client is named mctl-api-glovo-basket."',
        '    error_message = "The only redirect URI must be https://api.mctl.ai/glovo/basket/approvals/callback."',
        '    target = [zitadel_application_oidc.mctl_api_glovo_basket]',
        '    target = zitadel_application_oidc.mctl_api_glovo_basket',
        '    values = { client_id = "glovo-basket-client-id", client_secret = "glovo-basket-client-secret" }',
        '# The client of the Glovo basket approval page (mctl-api#1006). The same',
        'run "glovo_basket_client_is_a_confidential_pkce_web_client" {',
    }),
    "platform-gitops/helm-charts/zitadel-iac/values.yaml": frozenset({
        '#   Glovo basket approval page, in the MCTL API project): no new action; a',
        '#   mctl-api#1006 (mctl-api.tf: the mctl-api-glovo-basket web client of the',
    }),
    # Step W1: inert runtime DB env and the mctl-api ExternalSecrets.
    "platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml": frozenset({
        '            - mctl-api-glovo-runtime-db',
        '            GLOVO_DB_MIGRATION_ROLE: glovo_migrator',
        '            GLOVO_DB_RUNTIME_ROLE: glovo_runtime',
        '            GLOVO_DB_URL: "postgresql://$(GLOVO_DB_USER):$(GLOVO_DB_PASSWORD)@shared-pg-rw.platform-db.svc:5432/mctl-api?sslmode=require"',
        # Step B1: the basket MCP flags (mctl-api#1006).
        '            GLOVO_ENABLED: "true"',
        '            GLOVO_MCP_RESOURCE: https://glovo.mctl.ai/mcp',
        '            GLOVO_BASKET_MCP_ENABLED: "true"',
        # Step B2: the approval page flag, its route and its chart slot.
        '              - /glovo',
        '            GLOVO_BASKET_UI_ENABLED: "true"',
        '          glovoBasketUISecret: mctl-api-oidc-zitadel',
        # Step C: the host, restricted to the MCP and its metadata path.
        '              - host: glovo.mctl.ai',
    }),
    # Step C: the host is reserved for mctl-api in the same PR as its Ingress.
    "platform-gitops/bootstrap/values.yaml": frozenset({
        '  glovo.mctl.ai: [mctl-api]',
    }),
    "platform-gitops/bootstrap/templates/mctl-platform/mctl-api-secrets.yaml": frozenset({
        '        GLOVO_DB_PASSWORD: "{{ `{{ .password }}` }}"',
        '        GLOVO_DB_USER: "{{ `{{ .username }}` }}"',
        '        key: platform/mctl-api/glovo-runtime-database',
        '    name: mctl-api-glovo-runtime-db',
        '  name: mctl-api-glovo-runtime-db',
    }),
}


class Refused(Exception):
    pass


class Unknown(Exception):
    pass


def _load(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise Unknown(f"cannot read {path}: {e}") from e


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise Refused(msg)


def check_staged_values(root: Path) -> None:
    """Pure checks on the staged values files, no helm needed."""
    base = root / STAGED
    tp = _load(base / "target-paths.yaml")
    listed = set((tp or {}).get("files", {}))
    for p in sorted(base.glob("*/values.yaml")) + sorted(base.glob("netpol/*.yaml")):
        rel = str(p.relative_to(base))
        _need(rel in listed, f"{rel} is not listed in target-paths.yaml")

    # gate.yaml must be readable, but its content is never an unlock.
    gate = _load(base / "gate.yaml")
    _need(isinstance(gate, dict) and "phases" in gate, "gate.yaml malformed")

    facade = _load(base / VALUES["facade"])
    ing = facade.get("ingress", {})
    _need(ing.get("enabled") is False, "facade ingress.enabled must be false in P0")
    _need(ing.get("hosts") == [HOST], f"facade ingress.hosts must be exactly [{HOST}]")
    _need(ing.get("path") == "/mcp", "facade ingress.path must be /mcp")
    paths = [e.get("path") for e in facade.get("extraIngresses", [])]
    _need(paths == [METADATA_PATH], f"facade extra ingress paths must be exactly [{METADATA_PATH}]")
    for e in facade.get("extraIngresses", []):
        _need(e.get("hosts") == [HOST], "extra ingress host must be exactly the Glovo host")
    env = facade.get("env", {})
    _need(env.get("AUTH_REQUIRED") == "true", "facade AUTH_REQUIRED must be \"true\"")
    _need(env.get("GLOVO_ENABLED") == "false", "facade kill switch GLOVO_ENABLED must be \"false\"")
    _need(env.get("GLOVO_ALLOWLIST") == "", "facade GLOVO_ALLOWLIST must be empty")
    _need(env.get("GLOVO_TEAM_FALLBACK") == "false", "facade GLOVO_TEAM_FALLBACK must be \"false\"")
    _need(env.get("OAUTH_RESOURCE") == f"https://{HOST}/mcp", "facade OAUTH_RESOURCE must be the MCP URL")
    csc = facade.get("containerSecurityContext", {})
    _need(csc.get("runAsNonRoot") is True and csc.get("readOnlyRootFilesystem") is True,
          "facade must keep the hardened security context")

    for name in ("provider", "control"):
        v = _load(base / VALUES[name])
        _need(not v.get("ingress", {}).get("enabled"), f"{name} must have no Ingress")
        _need(not v.get("extraIngresses"), f"{name} must have no extra Ingress")
        _need(v.get("service", {}).get("type", "ClusterIP") == "ClusterIP",
              f"{name} Service must be ClusterIP (no NodePort/LoadBalancer)")
    prov = _load(base / VALUES["provider"])
    _need(prov.get("env", {}).get("TEMPORAL_NAMESPACE") == "mctl-assistants-provider-glovo",
          "provider Temporal identity must be mctl-assistants-provider-glovo")
    _need(bool(prov.get("extraExternalSecrets")), "provider credentials must come from an ExternalSecret")
    ctl = _load(base / VALUES["control"])
    _need(ctl.get("env", {}).get("TEMPORAL_NAMESPACE") == "mctl-assistants",
          "control Temporal identity must be mctl-assistants")

    ten = _load(base / TENANT)
    _need(ten.get("tenant", {}).get("networking", {}).get("allowInternetEgress") is False,
          "provider tenant must set allowInternetEgress: false")
    _need(ten.get("tenant", {}).get("networking", {}).get("allowClusterEgress") is False,
          "provider tenant must set allowClusterEgress: false")

    for p in base.rglob("*"):
        if p.is_file() and p.suffix in {".yaml", ".md"}:
            _need(not SECRET_SHAPED.search(p.read_text()), f"secret-shaped value in {p.relative_to(root)}")


def check_provenance(root: Path) -> None:
    """P0 validates staged provenance shape only. No digest is demanded here."""
    prov = _load(root / STAGED / "provenance.yaml")
    images = (prov or {}).get("images")
    _need(isinstance(images, dict) and set(images) == {"facade", "provider", "control"},
          "provenance.yaml needs exactly facade, provider, control")
    for name, img in images.items():
        for key in ("repository", "digest", "sourceRepo", "commit", "sbom", "buildRun"):
            _need(bool(img.get(key)), f"provenance {name}.{key} missing")


def leak_guard(root: Path, allowed_lines: dict[str, frozenset[str]] | None = None) -> None:
    """Deny unless the exact line is listed for the exact file. Ignores
    gate.yaml and every local marker on purpose."""
    if allowed_lines is None:
        allowed_lines = ALLOWED_LINES
    repos = []
    try:
        images = _load(root / STAGED / "provenance.yaml").get("images", {})
        repos = [i["repository"] for i in images.values() if i.get("repository")]
    except Unknown:
        raise
    except (AttributeError, KeyError) as e:
        raise Unknown(f"provenance unreadable: {e}") from e
    top = root / RECONCILED
    _need(top.is_dir(), f"{RECONCILED} missing")
    for p in sorted(top.rglob("*")):
        if not p.is_file() or "agents-state" in p.relative_to(top).parts:
            continue
        try:
            text = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue  # binary content cannot carry a values file
        rel = str(p.relative_to(root))
        if LEAK.search(str(p.relative_to(top))) or any(r in text for r in repos):
            raise Refused(f"Glovo/assistants reference in reconciled path {rel}")
        allowed = allowed_lines.get(rel, frozenset())
        for line in text.splitlines():
            if LEAK.search(line) and line not in allowed:
                raise Refused(f"Glovo/assistants reference in reconciled path {rel}")


def _run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def render_checks(root: Path) -> None:
    for tool in ("helm", "kubeconform"):
        if shutil.which(tool) is None:
            raise Unknown(f"{tool} not installed")
    base = root / STAGED
    schema = ["-schema-location", "default"]
    crd = os.environ.get("CRD_SCHEMA_LOCATION")
    if crd:
        schema += ["-schema-location", crd]
    jobs = []
    for name in ("facade", "provider", "control"):
        for flag in ("false", "true"):
            jobs.append((name, ["helm", "template", "t", str(root / "platform-gitops/helm-charts/base-service"),
                                "-f", str(base / VALUES[name]), "--set", f"ingress.enabled={flag}"
                                + (",ingress.hosts[0]=" + HOST if flag == "true" and name != "facade" else "")]))
    jobs.append(("tenant", ["helm", "template", "t", str(root / "platform-gitops/helm-charts/tenant"),
                            "-f", str(base / TENANT)]))
    for name, cmd in jobs:
        r = _run(cmd)
        _need(r.returncode == 0, f"helm template failed for {name}: {r.stderr.strip()[:300]}")
        docs = [d for d in yaml.safe_load_all(r.stdout) if d]
        kinds = [d.get("kind") for d in docs]
        if name in ("provider", "control") and "--set" in cmd and "ingress.enabled=true" in cmd[-1]:
            continue  # shape probe only: the Ingress guard below judges the real render
        if name in ("provider", "control"):
            _need("Ingress" not in kinds, f"{name} render contains an Ingress")
        for d in docs:
            if d.get("kind") == "Service":
                _need(d.get("spec", {}).get("type", "ClusterIP") == "ClusterIP",
                      f"{name} Service is not ClusterIP")
        k = _run(["kubeconform", "-strict", "-summary", *schema, "-"], input=r.stdout)
        _need(k.returncode == 0, f"kubeconform failed for {name}: {(k.stdout + k.stderr).strip()[:300]}")
    for p in sorted((base / "netpol").glob("*.yaml")):
        k = _run(["kubeconform", "-strict", "-summary", *schema, str(p)])
        _need(k.returncode == 0, f"kubeconform failed for {p.name}")


def run(root: Path, render: bool = True, allowed: dict[str, frozenset[str]] | None = None) -> int:
    try:
        check_staged_values(root)
        check_provenance(root)
        leak_guard(root, allowed)
        if render:
            render_checks(root)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return REFUSED
    except (Unknown, OSError) as e:
        print(f"UNKNOWN: {e}", file=sys.stderr)
        return UNKNOWN
    print("glovo-m1: ok")
    return 0


def _fixture(dst: Path) -> None:
    shutil.copytree(ROOT / STAGED, dst / STAGED)
    (dst / RECONCILED / "services/labs/x").mkdir(parents=True)
    (dst / RECONCILED / "services/labs/x/values.yaml").write_text("image:\n  repository: x\n")


def _edit(root: Path, rel: str, fn: Any) -> None:
    p = root / STAGED / rel
    doc = yaml.safe_load(p.read_text())
    fn(doc)
    p.write_text(yaml.safe_dump(doc))


def selftest() -> int:
    cases: list[tuple[str, int, Any, Any]] = []

    def add(name: str, want: int, mutate: Any, allowed: Any = None) -> None:
        cases.append((name, want, mutate, allowed))

    add("baseline passes", 0, lambda r: None)
    add("T2 host in reconciled labs values", REFUSED,
        lambda r: (r / RECONCILED / "services/labs/x/values.yaml").write_text(f"ingress:\n  host: {HOST}\n"))
    add("assistants namespace in reconciled path", REFUSED,
        lambda r: (r / RECONCILED / "services/labs/x/values.yaml").write_text("ns: mctl-assistants\n"))
    add("provenance image in reconciled path", REFUSED,
        lambda r: (r / RECONCILED / "services/labs/x/values.yaml").write_text(
            "image:\n  repository: ghcr.io/mctlhq/glovo-provider-worker\n"))

    def forged(r: Path) -> None:
        # A1/A2/A3: forged approvals plus a valid reconciled provider Deployment.
        _edit(r, "gate.yaml", lambda d: d["phases"].update(
            p1={"state": "approved", "approval": "https://github.com/x/y/issues/1"},
            p2={"state": "approved", "approval": "https://github.com/x/y/issues/2"}))
        d = r / RECONCILED / "services/mctl-assistants-provider-glovo/provider-worker"
        d.mkdir(parents=True)
        (d / "values.yaml").write_text(
            "image:\n  repository: ghcr.io/mctlhq/glovo-provider-worker\n  tag: 1.0.0\n")
    add("A2 forged gate.yaml approvals with reconciled provider", REFUSED, forged)
    add("T3 provider with Ingress", REFUSED,
        lambda r: _edit(r, VALUES["provider"], lambda d: d.__setitem__("ingress", {"enabled": True})))
    add("T3 provider NodePort", REFUSED,
        lambda r: _edit(r, VALUES["provider"], lambda d: d["service"].__setitem__("type", "NodePort")))
    add("T4 kill switch on", REFUSED,
        lambda r: _edit(r, VALUES["facade"], lambda d: d["env"].__setitem__("GLOVO_ENABLED", "true")))
    add("T4 non-empty allowlist", REFUSED,
        lambda r: _edit(r, VALUES["facade"], lambda d: d["env"].__setitem__("GLOVO_ALLOWLIST", "u1")))
    add("T4 team fallback on", REFUSED,
        lambda r: _edit(r, VALUES["facade"], lambda d: d["env"].__setitem__("GLOVO_TEAM_FALLBACK", "true")))
    add("facade ingress enabled in P0", REFUSED,
        lambda r: _edit(r, VALUES["facade"], lambda d: d["ingress"].__setitem__("enabled", True)))
    add("facade extra host", REFUSED,
        lambda r: _edit(r, VALUES["facade"], lambda d: d["ingress"].__setitem__("hosts", [HOST, "x.mctl.ai"])))
    add("facade extra path", REFUSED,
        lambda r: _edit(r, VALUES["facade"], lambda d: d["extraIngresses"].append(
            {"hosts": [HOST], "path": "/admin"})))
    add("tenant internet egress", REFUSED,
        lambda r: _edit(r, TENANT, lambda d: d["tenant"]["networking"].__setitem__("allowInternetEgress", True)))
    add("tenant cluster egress", REFUSED,
        lambda r: _edit(r, TENANT, lambda d: d["tenant"]["networking"].__setitem__("allowClusterEgress", True)))
    add("unlisted staged file", REFUSED,
        lambda r: (r / STAGED / "netpol/new.yaml").write_text("a: 1\n"))
    add("secret-shaped value", REFUSED,
        lambda r: (r / STAGED / "secrets-map.md").write_text("token ghp_abcdef\n"))
    add("T5 provenance incomplete", REFUSED,
        lambda r: _edit(r, "provenance.yaml", lambda d: d["images"]["facade"].pop("sbom")))
    add("T6 gate.yaml missing", UNKNOWN, lambda r: (r / STAGED / "gate.yaml").unlink())
    add("T6 gate.yaml unparseable", UNKNOWN, lambda r: (r / STAGED / "gate.yaml").write_text(": : :\n- ["))

    # Exact-line allowlist (runbook "Leak guard at activation").
    a_file = f"{RECONCILED}/services/labs/x/values.yaml"
    a_line = "  - name: glovo_runtime"
    allow = {a_file: frozenset({a_line})}
    add("allowlist: listed line in listed file passes", 0,
        lambda r: (r / a_file).write_text(f"roles:\n{a_line}\n"), allow)
    # Host block shape of activation step C: only the host line matches LEAK.
    h_line = "      - host: glovo.mctl.ai"
    h_block = f"hosts:\n{h_line}\n        paths:\n          - /mcp\n          - /.well-known/oauth-protected-resource\n"
    add("allowlist: non-matching path lines under an allowed host need no entry", 0,
        lambda r: (r / a_file).write_text(h_block), {a_file: frozenset({h_line})})
    add("allowlist: the host line itself is still required", REFUSED,
        lambda r: (r / a_file).write_text(h_block), {a_file: frozenset()})
    add("allowlist: same line in another file refuses", REFUSED,
        lambda r: (r / RECONCILED / "services/labs/y.yaml").write_text(f"roles:\n{a_line}\n"), allow)
    add("allowlist: extra Glovo line next to an allowed one refuses", REFUSED,
        lambda r: (r / a_file).write_text(f"roles:\n{a_line}\n  - name: glovo_extra\n"), allow)
    add("allowlist: changed whitespace refuses", REFUSED,
        lambda r: (r / a_file).write_text(f"roles:\n {a_line}\n"), allow)
    add("allowlist: Glovo path name refuses even with allowed lines", REFUSED,
        lambda r: (r / RECONCILED / "services/labs/glovo.yaml").write_text(f"{a_line}\n"),
        {f"{RECONCILED}/services/labs/glovo.yaml": frozenset({a_line})})
    add("allowlist: provenance image refuses even on an allowed line", REFUSED,
        lambda r: (r / a_file).write_text("  repository: ghcr.io/mctlhq/glovo-provider-worker\n"),
        {a_file: frozenset({"  repository: ghcr.io/mctlhq/glovo-provider-worker"})})
    add("allowlist: forged gate.yaml unlocks nothing", REFUSED,
        lambda r: (_edit(r, "gate.yaml", lambda d: d["phases"].update(
            p1={"state": "approved", "approval": "https://github.com/x/y/issues/1"})),
            (r / a_file).write_text("ns: mctl-assistants\n")), allow)
    add("allowlist: real ALLOWED_LINES on an untouched tree passes", 0, lambda r: None)

    failed = 0
    for name, want, mutate, allowed in cases:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            mutate(root)
            got = run(root, render=False, allowed=allowed)
        ok = got == want
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: exit {got}, want {want}", file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    return run(ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
