"""issue-1355 / #1332: regression test for the otel-collector's `redaction`
processor key rules.

Renders the default collector config (no eval overlay -- the redaction
config does not depend on any eval key), compiles `ignored_key_patterns` and
`blocked_key_patterns` with Python `re` (every committed pattern is
RE2-compatible and also valid Python, so this evaluates the real committed
strings rather than a paraphrase of them), and classifies each key the way
processAttrs does at the pinned v0.160.0: an ignored key is left untouched
and never reaches the block list; otherwise a blocked key is masked.

- MUST_BE_MASKED: credential-shaped keys, including credential-shaped keys
  inside the gen_ai.usage namespace the ignore list opens, so the exemption
  can never widen into cover for a credential.
- MUST_SURVIVE: the GenAI usage counters (current and deprecated semconv
  spellings) and cost-shaped keys. Token counts are the cost-attribution
  input (#1332); before the fix the bare `token` alternative masked every
  one of them.

This checks key classification only. Whether the counter's *value and type*
reach the exporter intact is checked against the real collector binary by
tests/test_otel_collector_redaction_e2e.py.

Run: python3 tests/test_otel_collector_redaction.py
"""
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
DEFAULT_VALUES = CHART / "values.yaml"

MUST_BE_MASKED = [
    "github_token",
    "authorization",
    "api_key",
    "vault.token",
    "access_token",
    "http.request.header.authorization",
    "gen_ai.usage.access_token",
    "gen_ai.usage.api_key",
    "gen_ai.usage.input_tokens.secret",
    "x.gen_ai.usage.input_tokens",
]
MUST_SURVIVE = [
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.reasoning_tokens",
    "gen_ai.usage.cache_read_input_tokens",
    "gen_ai.usage.cache_creation_input_tokens",
    "gen_ai.usage.cache_read.input_tokens",
    "gen_ai.usage.cache_creation.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "gen_ai.usage.completion_tokens",
    "gen_ai.usage.total_tokens",
    "gen_ai.request.model",
    "mctl.cost.usd",
    "mctl.cost.source",
    "gen_ai.usage.cost",
]

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def helm_template(*value_files):
    cmd = ["helm", "template", "test", str(CHART)]
    for vf in value_files:
        cmd += ["-f", str(vf)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"helm template failed: {proc.stderr}")
    return list(yaml.safe_load_all(proc.stdout))


def collector_config(docs):
    apps = [
        d for d in docs
        if d and d.get("kind") == "Application" and d["metadata"]["name"] == "otel-collector"
    ]
    assert len(apps) == 1, f"expected exactly one otel-collector Application, got {len(apps)}"
    src = apps[0]["spec"]["sources"][0]
    return yaml.safe_load(src["helm"]["values"])["config"]


docs = helm_template(DEFAULT_VALUES)
cfg = collector_config(docs)
redaction = cfg["processors"]["redaction"]
ignore_patterns = [re.compile(p) for p in redaction.get("ignored_key_patterns", [])]
key_patterns = [re.compile(p) for p in redaction["blocked_key_patterns"]]


def classify(key):
    """Mirror processAttrs' key order: ignore first, then the block list."""
    if any(p.search(key) for p in ignore_patterns):
        return "ignored"
    if any(p.search(key) for p in key_patterns):
        return "masked"
    return "kept"


check(redaction.get("allow_all_keys") is True,
      "allow_all_keys must stay true: false turns the key rules into deletion of every unlisted key")

for key in MUST_BE_MASKED:
    check(classify(key) == "masked", f"{key!r} must be masked, got {classify(key)}")

for key in MUST_SURVIVE:
    check(classify(key) != "masked", f"{key!r} must survive redaction, got masked")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"otel-collector redaction: {len(MUST_BE_MASKED)} credential keys masked, "
      f"{len(MUST_SURVIVE)} usage/cost keys survive")
