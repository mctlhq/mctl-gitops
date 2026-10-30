"""Render base-service and assert the blueGreen objects carry PruneLast.

Switching `blueGreen.enabled` off swaps the Rollout for a Deployment of the
same name. ArgoCD would otherwise prune the Rollout in the same wave that
creates the Deployment, so the only Ready pod goes away about as long before
the new one is Ready as the app takes to start, and the site is down for that
window. `argocd.argoproj.io/sync-options: PruneLast=true` defers the prune
until the rest of the sync is healthy. ArgoCD reads a pruned object's sync
options from the live object, so the annotation has to be live before the
switch: this test keeps it from being dropped from either template.

Run: python3 tests/test_base_service_bluegreen_prune_last.py
"""
import pathlib
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("platform-gitops/helm-charts/base-service")
ANNOTATION = "argocd.argoproj.io/sync-options"

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as fh:
        yaml.safe_dump(values, fh)
        fh.flush()
        proc = subprocess.run(
            ["helm", "template", "test", str(CHART), "-f", fh.name,
             "--namespace", "labs"],
            capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"helm template failed:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def sync_options(doc):
    raw = ((doc.get("metadata") or {}).get("annotations") or {}).get(ANNOTATION, "")
    return {o.strip() for o in raw.split(",") if o.strip()}


# 1. blueGreen on: the Rollout and the preview Service both carry PruneLast.
docs = render({"image": {"tag": "1.0.0"}, "blueGreen": {"enabled": True}})
rollouts = [d for d in docs if d.get("kind") == "Rollout"]
previews = [d for d in docs if d.get("kind") == "Service"
            and d["metadata"]["name"].endswith("-preview")]
check(len(rollouts) == 1, f"want 1 Rollout, got {len(rollouts)}")
check(len(previews) == 1, f"want 1 preview Service, got {len(previews)}")
for doc in rollouts + previews:
    check("PruneLast=true" in sync_options(doc),
          f"{doc['kind']} {doc['metadata']['name']}: no PruneLast=true in {ANNOTATION}")

# 2. blueGreen off: a Deployment and no Rollout or preview Service, and
#    PruneLast does not leak onto objects that are never pruned this way.
#    Other sync options on those objects are not this test's concern.
docs = render({"image": {"tag": "1.0.0"}, "blueGreen": {"enabled": False}})
kinds = [d.get("kind") for d in docs]
check("Rollout" not in kinds, "blueGreen off still renders a Rollout")
check("Deployment" in kinds, "blueGreen off renders no Deployment")
for doc in docs:
    check("PruneLast=true" not in sync_options(doc),
          f"blueGreen off: {doc['kind']} {doc['metadata']['name']} carries PruneLast=true")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print("base-service blueGreen: Rollout and preview Service carry PruneLast; none on the Deployment rendering")
