#!/usr/bin/env python3
"""Fail when the implementation admission worker is scaled past one replica.

mctlhq/mctl-agents#395 admits implementer runs in Temporal before Argo sees
them: a dedicated task queue, `mctl-dev-loop-implement`, served by
`mctl-agents-worker-implement` with `max_concurrent_activities = N`. That
limit is a per-PROCESS limit in the Temporal SDK, not a distributed
semaphore on the queue — capacity is `replicas × N`. Two replicas at N=3
admit six, silently, while every comment and alert still says three.

So for this phase `replicaCount: 1` on that one deployment is an
architectural invariant, not a sizing choice, and a comment in values.yaml
is not enough to hold it: this check fails CI if the value changes, or if
anything else that multiplies pods (an autoscaler, a blue/green rollout) is
switched on. The remedy for "not enough capacity" is raising N in the same
file; a hard N across crashes and replicas is ADR-010's server-side claim
(mctlhq/mctl-api#337), not a second pod.

Deliberately scoped to the single implementation worker. The control and
exec workers also run one replica today, but there it is a current value
(ADR-008 D6), not an invariant — scaling exec is a legitimate future move.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "platform-gitops/services/admins/mctl-agents-worker-implement/values.yaml"
ISSUE = "mctlhq/mctl-agents#395"


def violations(values_path: Path) -> list[str]:
    """Every way this file could yield more than one admission process."""
    if not values_path.is_file():
        return [f"{values_path} does not exist — the admission worker deployment is gone"]
    doc = yaml.safe_load(values_path.read_text())
    # A file that is not a mapping is out of scope here and kubeconform's
    # business; refusing to crash keeps a malformed file from blocking every
    # PR through this required check. But a missing replicaCount is NOT out
    # of scope: base-service's default is not 1 by contract, so an absent
    # key must be treated as "not pinned".
    if not isinstance(doc, dict):
        return [f"{values_path}: not a mapping; cannot verify replicaCount"]

    found: list[str] = []
    replicas = doc.get("replicaCount")
    if replicas != 1:
        found.append(f"replicaCount is {replicas!r}, must be exactly 1")

    autoscaling = doc.get("autoscaling")
    if isinstance(autoscaling, dict) and autoscaling.get("enabled"):
        found.append("autoscaling.enabled is true; an HPA multiplies admission capacity")

    rollout = doc.get("rollout")
    if isinstance(rollout, dict) and rollout.get("enabled"):
        found.append(
            "rollout.enabled is true; a blue/green Rollout runs two ReplicaSets and "
            "therefore two admission processes during every deploy"
        )

    command = doc.get("command")
    if isinstance(command, list) and "implementation" not in [str(c) for c in command]:
        found.append(
            f"command does not select --role implementation ({command!r}); the "
            "deployment this check guards is no longer the admission worker"
        )
    return found


def _write(root: Path, body: str) -> Path:
    path = root / "platform-gitops/services/admins/mctl-agents-worker-implement/values.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def selftest() -> int:
    """Prove the detector fires on every multiplier and stays quiet on the invariant."""
    good = (
        "replicaCount: 1\n"
        'command: ["python", "-m", "orchestrator.temporal.worker", "--role", "implementation"]\n'
        "env:\n  IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES: \"3\"\n"
    )
    cases: list[tuple[str, str, bool]] = [
        ("invariant held", good, False),
        ("scaled to two", good.replace("replicaCount: 1", "replicaCount: 2"), True),
        ("scaled to zero", good.replace("replicaCount: 1", "replicaCount: 0"), True),
        ("replicaCount missing", good.replace("replicaCount: 1\n", ""), True),
        ("hpa on", good + "autoscaling:\n  enabled: true\n  minReplicas: 1\n", True),
        ("blue-green on", good + "rollout:\n  enabled: true\n  strategy: blueGreen\n", True),
        ("hpa present but off", good + "autoscaling:\n  enabled: false\n", False),
        ("role changed", good.replace('"implementation"', '"execution"'), True),
        ("not a mapping", "- just\n- a list\n", True),
    ]
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name, body, should_fire in cases:
            try:
                found = violations(_write(root, body))
            except Exception as exc:  # noqa: BLE001 - a crash is the failure being tested for
                print(f"selftest FAIL: case {name!r} crashed the scan: {exc}", file=sys.stderr)
                return 1
            if bool(found) != should_fire:
                print(
                    f"selftest FAIL: case {name!r} expected fire={should_fire}, got {found}",
                    file=sys.stderr,
                )
                return 1
        # And the file being absent altogether is itself a violation.
        if not violations(root / "nowhere/values.yaml"):
            print("selftest FAIL: a missing values file passed", file=sys.stderr)
            return 1
    print(
        "selftest OK: detector fires on replicas != 1, a missing pin, an HPA, a "
        "blue/green rollout and a changed role; stays quiet on the invariant"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    found = violations(VALUES)
    if found:
        rel = VALUES.relative_to(ROOT)
        print(
            f"::error::{rel}: the implementation admission worker must run exactly one "
            f"process ({ISSUE}). IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES is a per-process "
            "limit, so capacity is replicas × N — scale N, not replicas:",
            file=sys.stderr,
        )
        for item in found:
            print(f"::error::{rel}: {item}", file=sys.stderr)
        return 1

    print("OK: mctl-agents-worker-implement is pinned to a single admission process")
    return 0


if __name__ == "__main__":
    sys.exit(main())
