#!/usr/bin/env python3
"""#1332: run the committed redaction and resource processors in the real
collector binary and check what comes out of the exporter.

tests/test_otel_collector_redaction.py checks how keys are classified. That
cannot see the defect #1332 was about: a masked integer counter arrives as
the *string* "****", so asserting key presence passes against the broken
config. This test sends one OTLP/JSON span through
`otel/opentelemetry-collector-contrib` at the tag the bootstrap chart pins,
with the `redaction` and `resource` processors taken verbatim from the
rendered default config, and reads the span back from a file exporter:

- every gen_ai.usage.*_tokens counter arrives as an intValue with its
  original number;
- a double cost attribute arrives as the same doubleValue;
- credential-shaped keys arrive as "****", including one inside the
  gen_ai.usage namespace, and a benign key carrying a GitHub-token-shaped
  value is masked by blocked_values;
- the resource carries deployment.environment.name and not the deprecated
  deployment.environment;
- summary: info leaves redaction.masked.count on the span.

Needs docker. Run: python3 tests/test_otel_collector_redaction_e2e.py
Mutation proof (#1332 put back): --without-ignore drops ignored_key_patterns
from the rendered config before running; the test must then fail.
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
DEFAULT_VALUES = CHART / "values.yaml"

COUNTERS = {
    "gen_ai.usage.input_tokens": 1234,
    "gen_ai.usage.output_tokens": 56,
    "gen_ai.usage.cache_read.input_tokens": 789,
    "gen_ai.usage.reasoning_tokens": 7,
}
COST = ("mctl.cost.usd", 0.4217)
MASKED_KEYS = {
    "authorization": "Bearer not-a-real-credential",
    "github_token": "not-a-real-credential",
    "gen_ai.usage.access_token": "not-a-real-credential",
}
# A benign key whose value has a GitHub-token shape: blocked_values must catch
# it. Built at runtime so no token-shaped literal sits in the repository.
VALUE_SHAPED_KEY = "mctl.note"
VALUE_SHAPED = "ghp_" + "A1" * 18


def render_processors():
    out = subprocess.run(
        ["helm", "template", "test", str(CHART), "-f", str(DEFAULT_VALUES)],
        capture_output=True, text=True, check=True,
    ).stdout
    for doc in yaml.safe_load_all(out):
        if doc and doc.get("kind") == "Application" and doc["metadata"]["name"] == "otel-collector":
            values = yaml.safe_load(doc["spec"]["sources"][0]["helm"]["values"])
            return values["image"]["tag"], values["config"]["processors"]
    raise AssertionError("no otel-collector Application in the rendered bootstrap chart")


def attr(key, value):
    if isinstance(value, bool):
        raise TypeError(key)
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": value}}


def payload():
    attrs = [attr(k, v) for k, v in COUNTERS.items()]
    attrs.append(attr(*COST))
    attrs += [attr(k, v) for k, v in MASKED_KEYS.items()]
    attrs.append(attr(VALUE_SHAPED_KEY, VALUE_SHAPED))
    now = time.time_ns()
    return {"resourceSpans": [{
        "resource": {"attributes": [attr("service.name", "redaction-e2e")]},
        "scopeSpans": [{"spans": [{
            "traceId": "5b8efff798038103d269b633813fc60c",
            "spanId": "eee19b7ec3c1b174",
            "name": "gen_ai.chat",
            "kind": 3,
            "startTimeUnixNano": str(now - 1_000_000),
            "endTimeUnixNano": str(now),
            "attributes": attrs,
        }]}],
    }]}


def run(without_ignore):
    tag, processors = render_processors()
    redaction = dict(processors["redaction"])
    if without_ignore:
        redaction.pop("ignored_key_patterns", None)
    config = {
        "receivers": {"otlp": {"protocols": {"http": {"endpoint": "0.0.0.0:4318"}}}},
        "processors": {"redaction": redaction, "resource": processors["resource"]},
        "exporters": {"file": {"path": "/out/spans.json"}},
        "service": {"pipelines": {"traces": {
            "receivers": ["otlp"],
            "processors": ["resource", "redaction"],
            "exporters": ["file"],
        }}},
    }
    work = pathlib.Path(tempfile.mkdtemp(prefix="otel-redaction-e2e-"))
    out = work / "out"
    out.mkdir()
    out.chmod(0o777)
    (work / "config.yaml").write_text(yaml.safe_dump(config))
    image = f"otel/opentelemetry-collector-contrib:{tag}"
    cid = subprocess.run(
        ["docker", "run", "-d", "--rm", "-p", "127.0.0.1::4318",
         "-v", f"{work / 'config.yaml'}:/etc/otelcol/config.yaml:ro",
         "-v", f"{out}:/out", image, "--config=/etc/otelcol/config.yaml"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        port = subprocess.run(["docker", "port", cid, "4318/tcp"], capture_output=True,
                              text=True, check=True).stdout.strip().splitlines()[0].rsplit(":", 1)[1]
        body = json.dumps(payload()).encode()
        deadline = time.time() + 60
        while True:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/traces", data=body,
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=5)
                break
            except (urllib.error.URLError, ConnectionError):
                if time.time() > deadline:
                    raise AssertionError("collector never accepted the span:\n" + logs(cid))
                time.sleep(1)
        spans_file = out / "spans.json"
        deadline = time.time() + 30
        while not (spans_file.exists() and spans_file.read_text().strip()):
            if time.time() > deadline:
                raise AssertionError("file exporter wrote nothing:\n" + logs(cid))
            time.sleep(1)
        return json.loads(spans_file.read_text().strip().splitlines()[0])
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


def logs(cid):
    return subprocess.run(["docker", "logs", cid], capture_output=True, text=True).stderr[-3000:]


def check(exported):
    failures = []
    rs = exported["resourceSpans"][0]
    resource = {a["key"]: a["value"] for a in rs["resource"]["attributes"]}
    span = rs["scopeSpans"][0]["spans"][0]
    got = {a["key"]: a["value"] for a in span["attributes"]}

    for key, number in COUNTERS.items():
        value = got.get(key)
        if value != {"intValue": str(number)}:
            failures.append(f"{key}: expected intValue {number}, got {value}")
    if got.get(COST[0]) != {"doubleValue": COST[1]}:
        failures.append(f"{COST[0]}: expected doubleValue {COST[1]}, got {got.get(COST[0])}")
    for key in MASKED_KEYS:
        if got.get(key) != {"stringValue": "****"}:
            failures.append(f"{key}: expected masked, got {got.get(key)}")
    note = got.get(VALUE_SHAPED_KEY, {}).get("stringValue", "")
    if re.search(r"ghp_[A-Za-z0-9]{36}", note):
        failures.append(f"{VALUE_SHAPED_KEY}: token-shaped value was exported unmasked")
    if "redaction.masked.count" not in got:
        failures.append("redaction.masked.count missing: summary: info is not in effect")
    if resource.get("deployment.environment.name", {}).get("stringValue") != "preprod":
        failures.append(f"resource deployment.environment.name: got {resource.get('deployment.environment.name')}")
    if "deployment.environment" in resource:
        failures.append("resource still carries the deprecated deployment.environment")
    return failures


def main():
    without_ignore = "--without-ignore" in sys.argv[1:]
    failures = check(run(without_ignore))
    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)
    print(f"otel-collector redaction e2e: {len(COUNTERS)} counters intact as int, "
          f"cost intact, {len(MASKED_KEYS) + 1} credential values masked")


if __name__ == "__main__":
    main()
