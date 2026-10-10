"""Pin the execution-trace wiring on the mctl-agents CWFTs (mctl-agents#195).

What this guards, for every container of every `cwft-mctl-agents-*.yaml`:

1. A container that sets an OTLP endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT` or
   `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) must also set
   `MCTL_TRACE_REQUIRE_PARENT: "true"` and take `TRACEPARENT` from the
   `traceparent` workflow parameter. Without the gate, a manual or sweep
   submit of the same template would export spans, which is outside the
   producer scope ADR 0001's "Producer amendment: DevLoop traces" declares.
2. A template that maps `TRACEPARENT` declares the `traceparent` parameter
   with an empty default, so a submit without it still renders.
3. The two templates the DevLoop traces, investigate and implement, carry
   the mapping, so the rollout cannot silently lose a hop.

Read from the templates, never restated, so it fails when they drift.

Run: python3 tests/test_cwft_execution_trace_env.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"
ENDPOINTS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
TRACEPARENT_VALUE = "{{workflow.parameters.traceparent}}"
TRACED = ("cwft-mctl-agents-investigate.yaml", "cwft-mctl-agents-implement.yaml")

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def containers(template):
    for key in ("container", "script"):
        if isinstance(template.get(key), dict):
            yield template[key]
    for key in ("initContainers", "sidecars"):
        yield from template.get(key) or []


def env_of(container):
    return {e.get("name"): e.get("value") for e in container.get("env") or [] if isinstance(e, dict)}


def main():
    files = sorted(TEMPLATES_DIR.glob("cwft-mctl-agents-*.yaml"))
    check("found the mctl-agents CWFTs", len(files) >= 2, str(files))
    for path in files:
        doc = yaml.safe_load(path.read_text())
        spec = doc.get("spec") or {}
        params = {p.get("name"): p for p in (spec.get("arguments") or {}).get("parameters") or []}
        maps_traceparent = False
        for template in spec.get("templates") or []:
            for container in containers(template):
                env = env_of(container)
                where = f"{path.name}:{template.get('name')}"
                if env.get("TRACEPARENT") is not None:
                    maps_traceparent = True
                    check(f"{where} TRACEPARENT comes from the parameter",
                          env["TRACEPARENT"] == TRACEPARENT_VALUE, repr(env["TRACEPARENT"]))
                if any(env.get(name) for name in ENDPOINTS):
                    check(f"{where} exports only with MCTL_TRACE_REQUIRE_PARENT=true",
                          str(env.get("MCTL_TRACE_REQUIRE_PARENT", "")).lower() == "true",
                          repr(env.get("MCTL_TRACE_REQUIRE_PARENT")))
                    check(f"{where} exports only with TRACEPARENT mapped",
                          env.get("TRACEPARENT") == TRACEPARENT_VALUE, repr(env.get("TRACEPARENT")))
        if maps_traceparent:
            param = params.get("traceparent")
            check(f"{path.name} declares the traceparent parameter", param is not None)
            check(f"{path.name} traceparent defaults to empty",
                  param is not None and param.get("value") == "", repr(param))
        if path.name in TRACED:
            check(f"{path.name} is wired for traces", maps_traceparent)

    if failures:
        print("\n".join(["", "FAILURES:"] + failures))
        sys.exit(1)
    print("execution-trace env wiring holds")


if __name__ == "__main__":
    main()
