#!/usr/bin/env python3
"""Validate the inert Glovo M1 staging package (mctlhq/mctl-gitops#2470, P0).

  validate-glovo-m1-staging.py            check the repository tree
  validate-glovo-m1-staging.py --selftest prove each refusal fires

Exit 0 = pass, 6 = refused, 7 = could not observe. Anything unreadable is a
refusal or an unknown, never a pass.

Two independent halves:
  1. The staged package under deploy/staged/glovo-m1 must render, stay private
     where it must, and keep the fail-closed defaults.
  2. A deny-only leak guard: no Glovo host, workload, image or assistant
     namespace may appear in reconciled paths (platform-gitops/**, excluding
     agents-state/). gate.yaml is informational and is NEVER consulted as an
     unlock: a PR author can edit it, so it proves nothing.
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


def leak_guard(root: Path) -> None:
    """Deny-only. Ignores gate.yaml and every local marker on purpose."""
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
        if LEAK.search(text) or LEAK.search(str(p.relative_to(top))) or any(r in text for r in repos):
            raise Refused(f"Glovo/assistants reference in reconciled path {p.relative_to(root)}")


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


def run(root: Path, render: bool = True) -> int:
    try:
        check_staged_values(root)
        check_provenance(root)
        leak_guard(root)
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
    cases: list[tuple[str, int, Any]] = []

    def add(name: str, want: int, mutate: Any) -> None:
        cases.append((name, want, mutate))

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

    failed = 0
    for name, want, mutate in cases:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            mutate(root)
            got = run(root, render=False)
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
