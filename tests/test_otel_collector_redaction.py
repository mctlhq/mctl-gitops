"""issue-1355: redaction regression test for the otel-collector's
`redaction` processor.

Renders the default collector config (no eval overlay -- the redaction
config does not depend on any eval key), compiles
`processors.redaction.blocked_key_patterns` with Python `re` (every
committed pattern is RE2-compatible and also valid Python, so this evaluates
the real committed strings rather than a paraphrase of them), and checks two
fixed key lists:

- MUST_BE_BLOCKED: credential-shaped keys. Hard assertion, always -- this
  half never participates in the expected-failure marker below, so #1332
  can never be used as cover for a weakened credential block list.
- MUST_SURVIVE: the four `gen_ai.usage.*_tokens` counters
  tests/test_devloop_trace_fixture.py's REQUIRED_ATTRS also requires and the
  rubric's `ai_agent_observability` dimension (docs/adr/0001-rubric.yaml,
  weight 25) is scored from. Currently blocked by the bare `token`
  alternative in blocked_key_patterns[0] -- that is mctlhq/mctl-gitops#1332,
  and this half is guarded by KNOWN_BROKEN_ISSUE below (xfail-strict: the
  test hard-fails, not passes quietly, the moment the marker is left set
  after the four keys start surviving).

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

# Set to None once mctlhq/mctl-gitops#1332 is fixed and the four
# gen_ai.usage.*_tokens keys survive redaction. Left set, this test
# hard-fails the moment they start surviving -- the marker cannot outlive
# the bug it names.
KNOWN_BROKEN_ISSUE = "mctlhq/mctl-gitops#1332"

MUST_BE_BLOCKED = ["github_token", "authorization", "api_key", "vault.token"]
MUST_SURVIVE = [
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read_input_tokens",
    "gen_ai.usage.reasoning_tokens",
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
key_patterns = [re.compile(p) for p in redaction["blocked_key_patterns"]]


def blocked_by(key):
    return [p.pattern for p in key_patterns if p.search(key)]


# --- Hard assertion: the credential block list, always -----------------

for key in MUST_BE_BLOCKED:
    matches = blocked_by(key)
    check(bool(matches), f"{key!r} should be matched by at least one blocked_key_patterns entry, got none")

# --- gen_ai.usage.*_tokens: expected failure while #1332 is open --------

survivors = {key: blocked_by(key) for key in MUST_SURVIVE}
all_survive = all(not matches for matches in survivors.values())

if KNOWN_BROKEN_ISSUE:
    if all_survive:
        # The bug is fixed but the marker was left set -- xfail-strict.
        failures.append(
            f"gen_ai.usage.*_tokens keys now survive redaction, but "
            f"KNOWN_BROKEN_ISSUE is still set to {KNOWN_BROKEN_ISSUE!r} -- "
            "set KNOWN_BROKEN_ISSUE = None in "
            "tests/test_otel_collector_redaction.py now that the fix has landed"
        )
    else:
        still_blocked = {k: v for k, v in survivors.items() if v}
        print(
            f"EXPECTED FAILURE ({KNOWN_BROKEN_ISSUE}): gen_ai.usage.* still "
            f"redacted by {still_blocked}"
        )
else:
    # Marker cleared: this must now be a hard, normal assertion.
    for key, matches in survivors.items():
        check(not matches, f"{key!r} should survive redaction (matched by {matches})")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("otel-collector redaction: credential block list holds, gen_ai.usage.* status as expected")
