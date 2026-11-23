"""NetworkPolicy allow-argocd-mcp-to-server render (labs/argocd-mcp -> argocd-server).

`platform-gitops/argocd/templates/networkpolicy.yaml` ships default-deny-ingress
for the argocd namespace. labs/argocd-mcp (the portal's read-only Argo CD MCP
upstream) calls argocd-server in-cluster on pod port 8080, so
allow-argocd-mcp-to-server must admit exactly that pod and nothing else.

The checks parse the real `helm template` render of the argocd chart:

T1. default-deny-ingress exists in the same render (the allow rule is only
    meaningful against it).
T2. allow-argocd-mcp-to-server exists exactly once, in namespace argocd,
    selecting app.kubernetes.io/name=argocd-server, policyTypes == [Ingress].
T3. Exactly one ingress rule with exactly one `from` element, and that single
    element carries BOTH namespaceSelector (kubernetes.io/metadata.name=labs)
    and podSelector (instance labs-argocd-mcp + name base-service). Two
    elements would be OR and admit the whole labs namespace.
T4. The selectors use matchLabels only (no matchExpressions, no ipBlock) and
    the rule has exactly one port, TCP 8080.

If `helm` is not on PATH the test skips (it is installed in the validate job).

Run: python3 tests/test_argocd_mcp_netpol_render.py   (needs helm)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "argocd"
VALUES_FILE = CHART / "values.yaml"
POLICY = "allow-argocd-mcp-to-server"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def netpols(docs: list, name: str) -> list[dict]:
    return [d for d in docs if d and d.get("kind") == "NetworkPolicy"
            and d.get("metadata", {}).get("name") == name]


if not shutil.which("helm"):
    print("SKIP: helm is not on PATH; argocd mcp netpol render not checked")
    sys.exit(0)

try:
    with tempfile.TemporaryDirectory() as d:
        out = subprocess.run(
            ["helm", "template", "test", str(CHART), "-f", str(VALUES_FILE)],
            capture_output=True, text=True, check=True, cwd=d,
        )
except subprocess.CalledProcessError as exc:
    print(f"FAIL: helm template failed: {exc.stderr}", file=sys.stderr)
    sys.exit(1)

docs = list(yaml.safe_load_all(out.stdout))

# T1
deny = netpols(docs, "default-deny-ingress")
check(len(deny) == 1, f"expected exactly one default-deny-ingress, got {len(deny)}")
if deny:
    check(deny[0]["spec"].get("podSelector") == {} and deny[0]["spec"].get("policyTypes") == ["Ingress"],
          "default-deny-ingress must select every pod and be Ingress-only")

# T2
found = netpols(docs, POLICY)
check(len(found) == 1, f"expected exactly one {POLICY}, got {len(found)}")
if len(found) == 1:
    np = found[0]
    spec = np["spec"]
    check(np["metadata"].get("namespace") == "argocd",
          f"{POLICY} namespace must be argocd, got {np['metadata'].get('namespace')!r}")
    check(spec.get("podSelector") == {"matchLabels": {"app.kubernetes.io/name": "argocd-server"}},
          f"{POLICY} must select only argocd-server, got {spec.get('podSelector')!r}")
    check(spec.get("policyTypes") == ["Ingress"],
          f"{POLICY} policyTypes must be ['Ingress'], got {spec.get('policyTypes')!r}")

    # T3
    ingress = spec.get("ingress") or []
    check(len(ingress) == 1, f"{POLICY} must have exactly one ingress rule, got {len(ingress)}")
    if len(ingress) == 1:
        rule = ingress[0]
        froms = rule.get("from") or []
        check(
            len(froms) == 1,
            f"{POLICY} must have exactly one from element (namespaceSelector AND podSelector "
            f"in the same element); separate elements are OR and admit the whole namespace. "
            f"Got {len(froms)}",
        )
        if len(froms) == 1:
            peer = froms[0]
            check(set(peer) == {"namespaceSelector", "podSelector"},
                  f"the from element must carry exactly namespaceSelector and podSelector, got {sorted(peer)}")
            check(peer.get("namespaceSelector") == {"matchLabels": {"kubernetes.io/metadata.name": "labs"}},
                  f"namespaceSelector must be exactly kubernetes.io/metadata.name=labs, "
                  f"got {peer.get('namespaceSelector')!r}")
            check(peer.get("podSelector") == {"matchLabels": {
                      "app.kubernetes.io/instance": "labs-argocd-mcp",
                      "app.kubernetes.io/name": "base-service"}},
                  f"podSelector must be exactly instance=labs-argocd-mcp + name=base-service, "
                  f"got {peer.get('podSelector')!r}")
        # T4
        check(rule.get("ports") == [{"protocol": "TCP", "port": 8080}],
              f"ports must be exactly TCP 8080, got {rule.get('ports')!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"argocd mcp netpol render: {POLICY} admits only labs/labs-argocd-mcp (AND form) to argocd-server TCP 8080; "
      "default-deny-ingress present")
