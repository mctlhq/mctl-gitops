"""k3s-preview apply guard (.github/scripts/k3s-plan-guard.sh, #1534).

terraform.yml runs the guard on every plan it might apply. It only ever
meets a real plan during an apply of the preprod cluster, so a bug in it is
found by a destroyed node or a restarted control plane. This exercises it
against synthetic plans instead:

G1. A routine plan (local files created, the kubeconfig resource updated in
    place, kustomization re-run) passes.
G2. A replacement of terraform_data.control_plane_config / agent_config is
    refused, and passes only with ALLOW_REPROVISION=true. The guard before
    #1534 treated every terraform_data as bookkeeping and let this through.
G3. A delete of a server or a replace of the Hetzner SSH key is refused, and
    passes only with ALLOW_DESTROY=true. ALLOW_REPROVISION does not unlock it.
G4. A plan with no changes passes; an unreadable plan is refused, never
    read as "nothing to destroy".

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_k3s_plan_guard.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / ".github/scripts/k3s-plan-guard.sh"


def rc(name: str, type_: str, actions: list[str], index=None) -> dict:
    address = f"module.kube-hetzner.{type_}.{name}"
    if index is not None:
        address += f"[{json.dumps(index)}]"
    change = {"address": address, "type": type_, "name": name, "change": {"actions": actions}}
    if index is not None:
        change["index"] = index
    return change


ROUTINE = [
    rc("kustomization_backup", "local_file", ["create"], 0),
    rc("kubeconfig", "local_sensitive_file", ["create"], 0),
    rc("kubeconfig", "ssh_sensitive_resource", ["update"]),
    rc("kustomization", "terraform_data", ["delete", "create"]),
    rc("server", "hcloud_server", ["no-op"]),
]


def run(plan, env: dict[str, str] | None = None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "plan.json"
        path.write_text(plan if isinstance(plan, str) else json.dumps(plan))
        full_env = {k: v for k, v in os.environ.items() if not k.startswith("ALLOW_")}
        full_env.update(env or {})
        p = subprocess.run([str(GUARD), str(path)], env=full_env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


def plan_of(changes: list[dict]) -> dict:
    return {"format_version": "1.2", "resource_changes": changes}


failures: list[str] = []


def expect(label: str, plan, want_rc: int, env: dict[str, str] | None = None, must_say: str = "") -> None:
    got, out = run(plan, env)
    if got != want_rc or (must_say and must_say not in out):
        failures.append(f"{label}: rc={got} (want {want_rc})\n{out}")


# G1
expect("G1 routine", plan_of(ROUTINE), 0)

# G2
for name in ("control_plane_config", "agent_config", "registries", "kubelet_config"):
    bad = plan_of(ROUTINE + [rc(name, "terraform_data", ["delete", "create"], "0-0-worker")])
    expect(f"G2 {name} refused", bad, 1, must_say=name)
    expect(f"G2 {name} allowed", bad, 0, {"ALLOW_REPROVISION": "true"})
    expect(f"G2 {name} not unlocked by allow_destroy", bad, 1, {"ALLOW_DESTROY": "true"})

# G3
for name, type_, actions in (
    ("server", "hcloud_server", ["delete"]),
    ("k3s", "hcloud_ssh_key", ["create", "delete"]),
    ("k3s", "hcloud_network", ["delete", "create"]),
):
    bad = plan_of(ROUTINE + [rc(name, type_, actions, 0)])
    expect(f"G3 {type_} refused", bad, 1, must_say=type_)
    expect(f"G3 {type_} allowed", bad, 0, {"ALLOW_DESTROY": "true"})
    expect(f"G3 {type_} not unlocked by allow_reprovision", bad, 1, {"ALLOW_REPROVISION": "true"})

# G4
expect("G4 no changes", {"format_version": "1.2"}, 0)
expect("G4 empty object", {}, 1, must_say="refusing")
expect("G4 resource_changes not a list", {"format_version": "1.2", "resource_changes": {}}, 1, must_say="refusing")
expect("G4 not JSON", "garbage", 1, must_say="refusing")

if failures:
    print("\n\n".join(failures))
    sys.exit(1)
print("k3s plan guard: all checks passed")
