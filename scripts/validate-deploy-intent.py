#!/usr/bin/env python3
"""Validate the DeployIntent contract (mctlhq/mctl-gitops#2186, epic
mctlhq/.github#254).

A DeployIntent is the only input an AI session controls when it deploys a
repository; mctl-api compiles it onto ordinary base-service values. Two files
define the boundary:

  platform-gitops/agent-platform/schemas/deploy-intent.schema.json
      what an intent may say (closed everywhere)
  platform-gitops/agent-platform/deploy-intent-chart-keys.yaml
      every top-level .Values key base-service reads, classified as
      intent / platform / denied

This script keeps them in step and fails closed:

  - the schema is not a valid draft-07 schema
  - the chart reads a key that is not classified, reads .Values without a
    key (toYaml .Values, index .Values ...), or the classification lists a
    key the chart no longer reads
  - a key is classified twice, or an intent key's `from` names a field the
    schema does not have
  - a must-deny escape hatch is not denied
  - a schema property shares its name with a denied key
  - an intent fixture fails the schema or the semantic checks the schema
    cannot express (env/secretRef collisions, request above limit)

Usage:
  scripts/validate-deploy-intent.py             validate the real contract
  scripts/validate-deploy-intent.py --selftest  also replay
                                                 scripts/tests/fixtures/deploy-intent/
                                                 {valid,invalid} and prove each
                                                 contract check fires on a
                                                 deliberate mutation
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import sys

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "platform-gitops" / "agent-platform"
SCHEMA_PATH = CATALOG / "schemas" / "deploy-intent.schema.json"
CHART_KEYS_PATH = CATALOG / "deploy-intent-chart-keys.yaml"
CHART_TEMPLATES = ROOT / "platform-gitops" / "helm-charts" / "base-service" / "templates"
FIXTURES_ROOT = ROOT / "scripts" / "tests" / "fixtures" / "deploy-intent"

# The escape hatches named in mctlhq/.github#254. Moving any of them out of
# `denied` is a contract change, not a classification tweak.
MUST_DENY = frozenset(
    {
        "extraObjects",
        "extraContainers",
        "initContainers",
        "extraIngresses",
        "extraVolumes",
        "extraVolumeMounts",
        "serviceAccount",
        "podSecurityContext",
        "command",
        "args",
    }
)

VALUES_KEY_RE = re.compile(r"\.Values\.([A-Za-z_][A-Za-z0-9_]*)")
# Any .Values occurrence; the ones not followed by .<key> are whole-values
# access that no classification can cover.
VALUES_ANY_RE = re.compile(r"\.Values(?![A-Za-z0-9_])(\.[A-Za-z_])?")

CPU_RE = re.compile(r"^(?:([0-9]+)m|([0-9]+(?:\.[0-9]+)?))$")
MEMORY_RE = re.compile(r"^([0-9]+)(Mi|Gi)$")


def load_yaml(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_templates(templates_dir: pathlib.Path) -> dict[str, str]:
    files = sorted(p for p in templates_dir.iterdir() if p.is_file()) if templates_dir.is_dir() else []
    if not files:
        # Reading nothing is not "the chart reads no keys".
        raise FileNotFoundError(f"no chart templates under {templates_dir}")
    return {p.name: p.read_text(encoding="utf-8") for p in files}


def chart_keys(templates: dict[str, str], errors: list) -> set[str]:
    keys: set[str] = set()
    for name, text in templates.items():
        keys.update(VALUES_KEY_RE.findall(text))
        for match in VALUES_ANY_RE.finditer(text):
            if match.group(1) is None:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{name}:{line}: whole-values access to .Values cannot be classified")
    return keys


def schema_has_field(schema: dict, dotted: str) -> bool:
    node = schema
    for part in dotted.split("."):
        props = node.get("properties")
        if not isinstance(props, dict) or part not in props:
            return False
        node = props[part]
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/definitions/"):
                return False
            node = schema.get("definitions", {}).get(ref.removeprefix("#/definitions/"), {})
    return True


def schema_property_names(node) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            names.update(props)
        for value in node.values():
            names |= schema_property_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= schema_property_names(value)
    return names


def check_contract(schema: dict, classification, templates: dict[str, str]) -> list:
    errors: list = []
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        errors.append(f"deploy-intent schema is invalid: {exc.message}")
        return errors

    if not isinstance(classification, dict) or set(classification) != {"intent", "platform", "denied"}:
        errors.append("chart-keys: top level must be exactly intent, platform and denied")
        return errors
    intent = classification["intent"] or {}
    platform = classification["platform"] or []
    denied = classification["denied"] or []
    if not isinstance(intent, dict) or not isinstance(platform, list) or not isinstance(denied, list):
        errors.append("chart-keys: intent must be a mapping, platform and denied lists")
        return errors

    seen: dict[str, str] = {}
    for cls, keys in (("intent", list(intent)), ("platform", platform), ("denied", denied)):
        for key in keys:
            if key in seen:
                errors.append(f"chart-keys: {key} is classified as both {seen[key]} and {cls}")
            seen[key] = cls

    for key, entry in intent.items():
        source = entry.get("from") if isinstance(entry, dict) else None
        if not isinstance(source, str) or not source:
            errors.append(f"chart-keys: intent key {key} has no `from` field")
        elif not schema_has_field(schema, source):
            errors.append(f"chart-keys: intent key {key} is compiled from {source}, which the schema does not define")

    read = chart_keys(templates, errors)
    for key in sorted(read - set(seen)):
        errors.append(f"chart reads .Values.{key}, which is not classified in deploy-intent-chart-keys.yaml")
    for key in sorted(set(seen) - read):
        errors.append(f"chart-keys: {key} is classified but the chart no longer reads it")

    for key in sorted(MUST_DENY - set(denied)):
        errors.append(f"chart-keys: {key} must be denied (escape hatch named in mctlhq/.github#254)")

    for name in sorted(schema_property_names(schema) & set(denied)):
        errors.append(f"deploy-intent schema has a property named {name}, which is a denied chart key")
    return errors


def cpu_millis(value: str) -> float:
    m = CPU_RE.match(value)
    if not m:
        raise ValueError(value)
    return float(m.group(1)) if m.group(1) is not None else float(m.group(2)) * 1000


def memory_mi(value: str) -> int:
    m = MEMORY_RE.match(value)
    if not m:
        raise ValueError(value)
    return int(m.group(1)) * (1024 if m.group(2) == "Gi" else 1)


def check_intent(doc, schema: dict) -> list:
    validator = jsonschema.Draft7Validator(schema)
    errors = [
        f"schema: {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors

    spec = doc["spec"]
    refs = [r["env"] for r in spec.get("secretRefs", [])]
    for name in sorted({n for n in refs if refs.count(n) > 1}):
        errors.append(f"secretRefs: env {name} is referenced more than once")
    for name in sorted(set(refs) & set(spec.get("env", {}))):
        errors.append(f"env {name} is both a plain value and a secretRef")

    resources = spec.get("resources")
    if resources:
        req, lim = resources["requests"], resources["limits"]
        if cpu_millis(req["cpu"]) > cpu_millis(lim["cpu"]):
            errors.append(f"resources: cpu request {req['cpu']} exceeds limit {lim['cpu']}")
        if memory_mi(req["memory"]) > memory_mi(lim["memory"]):
            errors.append(f"resources: memory request {req['memory']} exceeds limit {lim['memory']}")
    return errors


def expected_reason(path: pathlib.Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# expect:"):
            return line.removeprefix("# expect:").strip()
    return None


def replay_fixtures(schema: dict) -> tuple[list, int, int]:
    problems: list = []
    valid = sorted((FIXTURES_ROOT / "valid").glob("*.yaml"))
    invalid = sorted((FIXTURES_ROOT / "invalid").glob("*.yaml"))
    if not valid or not invalid:
        problems.append(f"no fixtures found under {FIXTURES_ROOT}/{{valid,invalid}}")
    for path in valid:
        errors = check_intent(load_yaml(path), schema)
        if errors:
            problems.append(f"valid fixture {path.name} unexpectedly failed:")
            problems.extend(f"  {e}" for e in errors)
    for path in invalid:
        reason = expected_reason(path)
        if not reason:
            problems.append(f"invalid fixture {path.name} has no '# expect:' line")
            continue
        errors = check_intent(load_yaml(path), schema)
        if not errors:
            problems.append(f"invalid fixture {path.name} unexpectedly passed")
        elif not any(reason in e for e in errors):
            problems.append(f"invalid fixture {path.name} failed, but not for '{reason}': {errors}")
    return problems, len(valid), len(invalid)


def replay_mutations(schema: dict, classification: dict, templates: dict[str, str]) -> tuple[list, int]:
    """Each check_contract branch must fire on a deliberate mutation of the
    real inputs, so a check that silently stopped working fails CI."""

    def drop_denied(c, s, t):
        c["denied"].remove("extraObjects")

    def drop_must_deny(c, s, t):
        c["denied"].remove("initContainers")
        c["platform"].append("initContainers")

    def unclassified_key(c, s, t):
        t["zz-mutation.yaml"] = "{{- if .Values.hostNetwork }}hostNetwork: true{{- end }}"

    def whole_values(c, s, t):
        t["zz-mutation.yaml"] = "{{ toYaml .Values }}"

    def stale_key(c, s, t):
        c["denied"].append("neverReadByTheChart")

    def duplicate_key(c, s, t):
        c["platform"].append("env")

    def missing_from(c, s, t):
        c["intent"]["service"]["from"] = "spec.runtime.listenPort"

    def denied_property(c, s, t):
        s["properties"]["spec"]["properties"]["extraObjects"] = {"type": "array"}

    def broken_schema(c, s, t):
        s["properties"]["spec"]["type"] = "not-a-type"

    mutations = {
        "a denied key removed from the classification": (drop_denied, "chart reads .Values.extraObjects"),
        "a must-deny key reclassified as platform": (drop_must_deny, "initContainers must be denied"),
        "the chart reads an unclassified key": (unclassified_key, "chart reads .Values.hostNetwork"),
        "the chart reads .Values whole": (whole_values, "whole-values access"),
        "a classified key the chart never reads": (stale_key, "neverReadByTheChart is classified but"),
        "a key classified twice": (duplicate_key, "env is classified as both"),
        "an intent key compiled from a missing field": (missing_from, "spec.runtime.listenPort, which the schema"),
        "a schema property named like a denied key": (denied_property, "property named extraObjects"),
        "an invalid schema": (broken_schema, "schema is invalid"),
    }
    problems: list = []
    for label, (mutate, reason) in mutations.items():
        c, s, t = copy.deepcopy(classification), copy.deepcopy(schema), dict(templates)
        mutate(c, s, t)
        errors = check_contract(s, c, t)
        if not any(reason in e for e in errors):
            problems.append(f"mutation '{label}' was not detected (wanted '{reason}', got {errors})")
    return problems, len(mutations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true", help="replay fixtures and contract mutations")
    args = parser.parse_args()

    schema = load_json(SCHEMA_PATH)
    classification = load_yaml(CHART_KEYS_PATH)
    templates = read_templates(CHART_TEMPLATES)

    errors = check_contract(schema, classification, templates)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"deploy intent contract: {len(errors)} error(s)", file=sys.stderr)
        return 1
    classified = sum(len(classification[c] or []) for c in ("intent", "platform", "denied"))
    print(f"deploy intent contract ok: {classified} chart key(s) classified, {len(classification['denied'])} denied")

    if args.selftest:
        problems, valid_count, invalid_count = replay_fixtures(schema)
        mutation_problems, mutation_count = replay_mutations(schema, classification, templates)
        problems += mutation_problems
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            print(f"deploy intent selftest: {len(problems)} problem(s)", file=sys.stderr)
            return 1
        print(
            f"selftest ok: {valid_count} valid fixture(s), {invalid_count} invalid fixture(s), "
            f"{mutation_count} contract mutation(s) detected"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
