"""issue-903: schema checks on the committed DevLoop trace fixtures.

T3. `tests/fixtures/devloop-trace.json` -- OTLP/JSON, parses; every
    correlation attribute named in `requirements.md` appears at least once;
    each execution (top-level `resourceSpans` entry) has exactly one root
    span (no `parentSpanId`) and every `parentSpanId` resolves to a span in
    the same execution; span names cover Temporal, Argo, model, MCP/tool,
    GitHub, artifact and outcome; at least one execution terminates in an
    ERROR-status span.

T4. Redaction-fixture coupling. Parses the `redaction` processor out of the
    rendered collector config (via `helm template`, the same path
    `tests/test_otel_collector_backends_render.py` uses) and asserts each of
    `gen_ai.prompt.0.content`, `mcp.tool.arguments`,
    `http.request.header.authorization` in
    `tests/fixtures/devloop-trace-redaction.json` is matched by at least one
    `blocked_key_patterns` entry, and that the value of `mctl.artifact.note`
    is matched by at least one `blocked_values` entry. This is what stops the
    fixture and the block lists drifting apart -- a poisoned fixture nothing
    blocks proves nothing.

Run: python3 tests/test_devloop_trace_fixture.py
"""
import json
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
FIXTURE = ROOT / "tests" / "fixtures" / "devloop-trace.json"
REDACTION_FIXTURE = ROOT / "tests" / "fixtures" / "devloop-trace-redaction.json"

REQUIRED_ATTRS = {
    "mctl.execution_id", "mctl.temporal.workflow_id", "mctl.temporal.run_id",
    "mctl.argo.workflow", "mctl.argo.pod", "mctl.agent.role",
    "mctl.workflow.stage", "mctl.repository", "mctl.github.issue",
    "mctl.github.pr", "mctl.outcome", "gen_ai.system", "gen_ai.request.model",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read_input_tokens", "gen_ai.usage.reasoning_tokens",
    "mcp.tool.name", "mctl.cost.usd",
}

NAME_CATEGORIES = {
    "temporal": ("temporal.workflow",),
    "argo": ("argo.workflow", "argo.pod"),
    "model": ("gen_ai.chat",),
    "mcp/tool": ("mcp.tool.call",),
    "github": ("github.request",),
    "artifact": ("artifact.generate",),
    "outcome": ("devloop.outcome",),
}

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


# --- T3: devloop-trace.json schema -------------------------------------

doc = json.loads(FIXTURE.read_text())
executions = doc["resourceSpans"]
check(len(executions) >= 2, f"expected at least two executions, got {len(executions)}")

seen_attrs = set()
error_terminal_found = False
seen_categories = set()

for i, execution in enumerate(executions):
    spans = [s for scope in execution["scopeSpans"] for s in scope["spans"]]
    span_ids = {s["spanId"] for s in spans}
    roots = [s for s in spans if "parentSpanId" not in s]
    check(len(roots) == 1, f"execution {i}: expected exactly one root span, got {len(roots)}")
    for s in spans:
        parent = s.get("parentSpanId")
        if parent is not None:
            check(parent in span_ids, f"execution {i}: span {s['name']!r} has orphaned parentSpanId {parent}")
    for s in spans:
        for a in s.get("attributes", []):
            seen_attrs.add(a["key"])
        for category, names in NAME_CATEGORIES.items():
            if s["name"] in names:
                seen_categories.add(category)
    outcome_spans = [s for s in spans if s["name"] == "devloop.outcome"]
    if any(s.get("status", {}).get("code") == 2 for s in outcome_spans):
        error_terminal_found = True

missing_attrs = REQUIRED_ATTRS - seen_attrs
check(not missing_attrs, f"fixture is missing correlation attributes: {sorted(missing_attrs)}")
missing_categories = set(NAME_CATEGORIES) - seen_categories
check(not missing_categories, f"fixture is missing span categories: {sorted(missing_categories)}")
check(error_terminal_found, "no execution terminates in an ERROR-status devloop.outcome span")

# --- T4: redaction-fixture coupling --------------------------------------

proc = subprocess.run(
    ["helm", "template", "test", str(CHART), "-f", str(CHART / "values.yaml")],
    capture_output=True, text=True)
if proc.returncode != 0:
    raise AssertionError(f"helm template failed: {proc.stderr}")
rendered_docs = list(yaml.safe_load_all(proc.stdout))
apps = [d for d in rendered_docs if d and d.get("kind") == "Application" and d["metadata"]["name"] == "otel-collector"]
collector_config = yaml.safe_load(apps[0]["spec"]["sources"][0]["helm"]["values"])["config"]
redaction = collector_config["processors"]["redaction"]
key_patterns = [re.compile(p) for p in redaction["blocked_key_patterns"]]
value_patterns = [re.compile(p) for p in redaction["blocked_values"]]

redaction_doc = json.loads(REDACTION_FIXTURE.read_text())
poisoned_attrs = {}
for rs in redaction_doc["resourceSpans"]:
    for scope in rs["scopeSpans"]:
        for s in scope["spans"]:
            for a in s.get("attributes", []):
                value = a["value"].get("stringValue", "")
                poisoned_attrs[a["key"]] = value

for key in ("gen_ai.prompt.0.content", "mcp.tool.arguments", "http.request.header.authorization"):
    check(key in poisoned_attrs, f"redaction fixture missing poisoned key {key!r}")
    matched = any(p.search(key) for p in key_patterns)
    check(matched, f"{key!r} is not matched by any blocked_key_patterns entry in the committed collector config")

note_value = poisoned_attrs.get("mctl.artifact.note", "")
check(bool(note_value), "redaction fixture missing mctl.artifact.note")
value_matched = any(p.search(note_value) for p in value_patterns)
check(value_matched, "mctl.artifact.note's value is not matched by any blocked_values entry in the committed collector config")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("devloop trace fixtures: schema valid, correlation attributes present, redaction coupling holds")
