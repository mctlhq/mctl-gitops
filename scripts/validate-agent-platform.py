#!/usr/bin/env python3
"""Validate the agent platform catalog (ADR 007) under
platform-gitops/agent-platform/.

ADR 007 (mctlhq/mctl-agents docs/adr/007-agent-definition-execution-profile-contract.md)
splits agent execution into a canonical AgentDefinition (mctl-agents Git),
an independently versioned ExecutionProfile (this repo, reviewed in Git),
immutable published versions and atomic environment ReleaseBinding history
(mctl-api registry), and one immutable ExecutionPlan/ExecutionRecord per run
(runtime resolver, #227). This script owns only the mctl-gitops half: the
ExecutionProfile catalog, the ReleaseBindingIntent fixtures that pin an
exact (definition, profile) pair plus the canonical AgentDefinition's
sourceManifest, and platform-wide policy ceilings. It does not, and must
not, become a second AgentDefinition body or a release-history database --
see requirements.md's fixed decisions.

Every check here fails closed: an unrecognized tool/skill/policy/mutation-
scope/approval-gate/model-policy-task/sandbox reference, a budget or
timeout above the policy ceiling, a mutating scope with no matching
approval gate, a release intent that is not exactly one compatible
(definition, profile) pair, or a rollback that does not exactly replay a
previously recorded pair, is a validation error -- never a silent
fallback.

Usage:
  scripts/validate-agent-platform.py             validate the real catalog
  scripts/validate-agent-platform.py --selftest  also replay the fixtures
                                                  under
                                                  scripts/tests/fixtures/agent-platform/
                                                  and assert every valid/
                                                  case passes and every
                                                  invalid/ case fails
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "platform-gitops" / "agent-platform"
SCHEMAS = CATALOG / "schemas"
FIXTURES_ROOT = ROOT / "scripts" / "tests" / "fixtures" / "agent-platform"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
COMPAT_RE = re.compile(r"(>=|<=|==|>|<)\s*([0-9]+(?:\.[0-9]+)*)")


class CatalogValidationError(Exception):
    """Raised for a structural problem that stops validation of one file."""


def load_yaml(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_version(version: str) -> tuple:
    parts = version.split(".")
    out = []
    for part in parts:
        if not part.isdigit():
            raise CatalogValidationError(f"non-numeric version component {part!r} in {version!r}")
        out.append(int(part))
    return tuple(out)


def parse_compatibility(constraint: str):
    # findall alone is not enough: it skips whatever sits BETWEEN matches, so
    # ">=1.0.0 GARBAGE <2.0.0" parsed as ">=1.0.0 <2.0.0" and validated
    # green -- a constraint nobody wrote, silently honoured (agy P3 on
    # mctl-agents#291, which found the same hole in the resolver's copy of
    # this function). The whole string has to be consumed.
    matches = list(COMPAT_RE.finditer(constraint))
    if not matches:
        raise CatalogValidationError(f"unparseable compatibility constraint {constraint!r}")
    consumed = "".join(m.group(0) for m in matches)
    if re.sub(r"\s+", "", constraint) != re.sub(r"\s+", "", consumed):
        raise CatalogValidationError(
            f"compatibility constraint {constraint!r} contains text outside its comparators"
        )
    return [(op, parse_version(bound)) for op, bound in (m.groups() for m in matches)]


def _pad(a: tuple, b: tuple):
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def version_satisfies(version: str, constraint: str) -> bool:
    version_tuple = parse_version(version)
    for op, bound in parse_compatibility(constraint):
        a, b = _pad(version_tuple, bound)
        if op == ">=" and not a >= b:
            return False
        if op == "<=" and not a <= b:
            return False
        if op == ">" and not a > b:
            return False
        if op == "<" and not a < b:
            return False
        if op == "==" and not a == b:
            return False
    return True


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------


def require_limit(limits: dict, key: str):
    """Read a policy ceiling, failing closed when it is missing or non-numeric.

    policy.yaml has no JSON Schema, so a mistyped or dropped ceiling would
    otherwise leave the limit unset and skip the ceiling check entirely --
    the one place this validator could fail *open*. Every other policy list
    degrades to an empty collection, which correctly makes every reference
    "unknown"; these two scalars must raise instead.
    """
    value = limits.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogValidationError(
            f"spec.limits.{key} is missing or non-numeric ({value!r});"
            " policy ceilings must be declared explicitly (fail closed)"
        )
    return value


class Policy:
    def __init__(self, doc: dict):
        spec = doc.get("spec") or {}
        limits = spec.get("limits") or {}
        self.max_budget_usd = require_limit(limits, "maxBudgetUsd")
        self.max_timeout_seconds = require_limit(limits, "maxTimeoutSeconds")
        self.known_tools = {t["name"] for t in spec.get("knownTools") or []}
        self.known_skills = set(spec.get("knownSkills") or [])
        self.known_model_policy_tasks = set(spec.get("knownModelPolicyTasks") or [])
        self.known_policies = set(spec.get("knownPolicies") or [])
        self.known_evidence_kinds = set(spec.get("knownEvidenceKinds") or [])
        self.mutation_scopes = {
            s["name"]: s for s in spec.get("knownMutationScopes") or []
        }
        self.known_approval_gates = set(spec.get("knownApprovalGates") or [])
        self.approved_sandboxes = {
            entry["backend"]: set(entry.get("clusterWorkflowTemplates") or [])
            for entry in spec.get("approvedSandboxes") or []
        }

    @classmethod
    def load(cls, path: pathlib.Path) -> "Policy":
        return cls(load_yaml(path))


def load_policy(errors: list, path: pathlib.Path | None = None) -> Policy | None:
    path = path if path is not None else CATALOG / "policy.yaml"
    if not path.exists():
        errors.append(f"{path}: missing policy.yaml")
        return None
    try:
        return Policy.load(path)
    except Exception as exc:  # noqa: BLE001 - report and continue
        errors.append(f"{path}: {exc}")
        return None


# --------------------------------------------------------------------------
# ExecutionProfile
# --------------------------------------------------------------------------


def validate_profile_file(path: pathlib.Path, schema: dict, policy: Policy, errors: list):
    """Returns (name, version) on success, or None on any error (appended to errors)."""
    try:
        doc = load_yaml(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{path}: {exc}")
        return None

    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"{path}: schema: {exc.message} at {'/'.join(str(p) for p in exc.absolute_path)}")
        return None

    spec = doc["spec"]
    name = doc["metadata"]["name"]

    # -- reference checks: fail closed on anything not in policy.yaml --
    unknown_tools = set(spec["tools"]) - policy.known_tools
    for tool in sorted(unknown_tools):
        errors.append(f"{path}: unknown tool {tool!r} (not in policy.yaml knownTools)")

    unknown_skills = set(spec["skills"]) - policy.known_skills
    for skill in sorted(unknown_skills):
        errors.append(f"{path}: unknown skill {skill!r} (not in policy.yaml knownSkills)")

    if spec["policyRef"] not in policy.known_policies:
        errors.append(f"{path}: unknown policyRef {spec['policyRef']!r} (not in policy.yaml knownPolicies)")

    model_task = spec["modelPolicyRef"]["task"]
    if model_task not in policy.known_model_policy_tasks:
        errors.append(f"{path}: unknown modelPolicyRef.task {model_task!r} (not in policy.yaml knownModelPolicyTasks)")

    try:
        parse_compatibility(spec["modelPolicyRef"]["compatibility"])
    except CatalogValidationError as exc:
        errors.append(f"{path}: modelPolicyRef.compatibility: {exc}")

    for kind in spec["evidence"]["required"]:
        if kind not in policy.known_evidence_kinds:
            errors.append(f"{path}: unknown evidence kind {kind!r} (not in policy.yaml knownEvidenceKinds)")

    # -- budget / timeout ceilings --
    if spec["budgetUsd"] > policy.max_budget_usd:
        errors.append(
            f"{path}: budgetUsd {spec['budgetUsd']} exceeds policy ceiling {policy.max_budget_usd}"
        )
    if spec["timeoutSeconds"] > policy.max_timeout_seconds:
        errors.append(
            f"{path}: timeoutSeconds {spec['timeoutSeconds']} exceeds policy ceiling {policy.max_timeout_seconds}"
        )

    # -- sandbox approval --
    sandbox = spec["runtime"]["sandbox"]
    approved_cwfts = policy.approved_sandboxes.get(sandbox["backend"], set())
    if not sandbox["approved"]:
        errors.append(f"{path}: runtime.sandbox.approved is false")
    elif sandbox["clusterWorkflowTemplate"] not in approved_cwfts:
        errors.append(
            f"{path}: unapproved sandbox {sandbox['backend']}/{sandbox['clusterWorkflowTemplate']}"
            " (not in policy.yaml approvedSandboxes)"
        )

    # -- mutation requires scope + approval --
    approval_gates = set(spec["approval"]["requiredBefore"])
    for gate in approval_gates:
        if gate not in policy.known_approval_gates:
            errors.append(f"{path}: unknown approval gate {gate!r} (not in policy.yaml knownApprovalGates)")

    mutation_scopes = spec["permissions"]["mutationScopes"]
    for scope_name in mutation_scopes:
        scope = policy.mutation_scopes.get(scope_name)
        if scope is None:
            errors.append(f"{path}: unknown mutationScope {scope_name!r} (not in policy.yaml knownMutationScopes)")
            continue
        required_gate = scope.get("requiresApproval")
        if scope.get("mutating") and required_gate and required_gate not in approval_gates:
            errors.append(
                f"{path}: mutationScope {scope_name!r} requires approval gate {required_gate!r}"
                " in spec.approval.requiredBefore, but it is absent"
                " (mutation requires both a scoped permission and the applicable approval rule)"
            )

    return name, spec["version"]


# --------------------------------------------------------------------------
# Effective values: profile vs the deployed ClusterWorkflowTemplate
#
# Every profile header claims to "preserve today's effective values", and
# until now nothing checked that claim. It is the half of mctl-agents#277
# that can be checked entirely inside this repo: budgetUsd and
# timeoutSeconds come from the CWFT the profile itself names, not from
# mctl-agents' Python defaults. Checking them against those defaults would
# be wrong and would fire immediately -- implementer-default declares
# $20.00 because cwft-mctl-agents-implement.yaml sets IMPLEMENTER_BUDGET_USD
# to "20.00", while orchestrator/options.py defaults to $3.00.
#
# The tool allow-list is the other half and cannot be checked here: it needs
# to call the real options.py builders, so it lives in mctl-agents'
# orchestrator/validate_manifest.py.
# --------------------------------------------------------------------------

CWFT_DIR = ROOT / "platform-gitops" / "argo-workflows" / "cluster-templates"

BUDGET_ENV_SUFFIX = "_BUDGET_USD"
TIMEOUT_ENV_SUFFIX = "_TIMEOUT_SECONDS"


def _iter_env_vars(node):
    """Yield every (name, value) under any `env:` list anywhere in the doc.

    A CWFT nests env under templates -> container/script, at a depth that
    differs between templates, so this walks rather than indexes. Reading
    the file as text and regexing for the var would also work until the day
    a var name appears in a comment -- which it already does in
    cwft-mctl-agents-run.yaml.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "env" and isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and "name" in entry and "value" in entry:
                        yield str(entry["name"]), entry["value"]
            yield from _iter_env_vars(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_env_vars(item)


def _unique_env_by_suffix(doc, suffix: str, path: pathlib.Path):
    """The single value of the one env var ending in `suffix`, or None.

    Ambiguity is an error in both directions, and neither is hypothetical:

    - Two different NAMES with the same suffix: cannot tell which one a
      profile pins.
    - One name with two different VALUES: a CWFT declares the same variable
      in several steps (WORKFLOW_SERVICE appears three times in
      cwft-mctl-agents-implement.yaml), so values must be collected per
      name rather than assigned into a dict. A dict comprehension keyed by
      name keeps only the LAST occurrence — so a template setting a real
      budget in the step that runs the agent and a different one in a later
      step would validate against the later value while the earlier one is
      what executes. agy P2 on mctl-gitops#981.

    Repeats with the SAME value are fine and normal — that is what the
    duplicates above actually are.
    """
    found: dict[str, set] = {}
    for name, value in _iter_env_vars(doc):
        if name.endswith(suffix):
            found.setdefault(name, set()).add(str(value))
    if len(found) > 1:
        raise CatalogValidationError(
            f"{path.name} declares {len(found)} {suffix} variables "
            f"({', '.join(sorted(found))}); cannot tell which one a profile pins"
        )
    if not found:
        return None
    name, values = next(iter(found.items()))
    if len(values) > 1:
        raise CatalogValidationError(
            f"{path.name} declares {name} with {len(values)} different values "
            f"({', '.join(sorted(values))}); the effective value is ambiguous"
        )
    return next(iter(values))


def validate_profile_against_cwft(
    path: pathlib.Path, doc: dict, errors: list, cwft_dir: pathlib.Path
) -> None:
    """Check budgetUsd/timeoutSeconds against the CWFT the profile names.

    The CWFT is derived from spec.runtime.sandbox.clusterWorkflowTemplate
    rather than from a profile->template table. A table would be a third
    place able to drift from the other two, which is the failure this whole
    check exists to remove.
    """
    spec = doc["spec"]
    name = doc["metadata"]["name"]
    cwft_name = spec["runtime"]["sandbox"]["clusterWorkflowTemplate"]
    cwft_path = cwft_dir / f"cwft-{cwft_name}.yaml"
    if not cwft_path.exists():
        errors.append(
            f"{path}: names sandbox.clusterWorkflowTemplate {cwft_name!r} but "
            f"{cwft_path} does not exist"
        )
        return

    try:
        cwft = load_yaml(cwft_path)
        if not isinstance(cwft, dict):
            raise CatalogValidationError("not a YAML mapping")
        budget = _unique_env_by_suffix(cwft, BUDGET_ENV_SUFFIX, cwft_path)
        timeout_env = _unique_env_by_suffix(cwft, TIMEOUT_ENV_SUFFIX, cwft_path)

        # No *_TIMEOUT_SECONDS override means the pod-level deadline IS the
        # effective timeout, which is what the investigator and shepherd
        # headers already say. Deliberately the workflow-level
        # activeDeadlineSeconds, not a step-level one:
        # cwft-mctl-agents-implement.yaml has two 300-second step deadlines
        # that bound single steps, not the run.
        if timeout_env is not None:
            effective, source = timeout_env, f"*{TIMEOUT_ENV_SUFFIX}"
        else:
            effective = (cwft.get("spec") or {}).get("activeDeadlineSeconds")
            source = "spec.activeDeadlineSeconds"

        # Conversions live inside the try with everything else that can
        # throw. A CWFT is free to express a value as an Argo template
        # (value: "{{workflow.parameters.budget}}"), and float() on that
        # would abort the entire run — including --selftest — with a bare
        # traceback, where every other check in this module degrades to a
        # file-scoped error and carries on (claude P2 on mctl-gitops#981).
        budget_value = None if budget is None else float(budget)
        timeout_value = None if effective is None else int(effective)
    except Exception as exc:  # noqa: BLE001 - report and continue
        errors.append(f"{path}: reading {cwft_path.name}: {exc}")
        return

    if budget_value is None:
        errors.append(
            f"{path}: profile {name!r} declares budgetUsd {spec['budgetUsd']} but "
            f"{cwft_path.name} sets no *{BUDGET_ENV_SUFFIX} — the profile's "
            "effective value cannot be verified against anything"
        )
    elif budget_value != float(spec["budgetUsd"]):
        errors.append(
            f"{path}: budgetUsd {spec['budgetUsd']} does not match "
            f"{cwft_path.name}'s {budget_value}"
        )

    if timeout_value is None:
        errors.append(
            f"{path}: {cwft_path.name} declares neither a *{TIMEOUT_ENV_SUFFIX} "
            "nor spec.activeDeadlineSeconds; timeoutSeconds is unverifiable"
        )
    elif timeout_value != int(spec["timeoutSeconds"]):
        errors.append(
            f"{path}: timeoutSeconds {spec['timeoutSeconds']} does not match "
            f"{cwft_path.name}'s {source} of {timeout_value}"
        )


# --------------------------------------------------------------------------
# ReleaseBindingIntent
# --------------------------------------------------------------------------


def validate_release_file(
    path: pathlib.Path,
    schema: dict,
    policy: Policy,
    profiles_by_name: dict,
    errors: list,
):
    try:
        doc = load_yaml(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{path}: {exc}")
        return

    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"{path}: schema: {exc.message} at {'/'.join(str(p) for p in exc.absolute_path)}")
        return

    spec = doc["spec"]

    if spec["bindingSource"] == "compatibility-fixture" and spec["promotable"] is not False:
        errors.append(
            f"{path}: bindingSource: compatibility-fixture requires promotable: false"
            " (a fixture must never be interpreted as production activation state)"
        )

    if spec["registryLifecycle"]["definition"] == "disabled":
        errors.append(f"{path}: definition {spec['definition']['name']!r} registryLifecycle is disabled")
    if spec["registryLifecycle"]["profile"] == "disabled":
        errors.append(f"{path}: profile {spec['profile']['name']!r} registryLifecycle is disabled")

    # -- exact-pair resolution: profile must resolve to exactly one known
    # (name, version) in the profile catalog this validation run loaded. --
    profile_name = spec["profile"]["name"]
    profile_version = spec["profile"]["version"]
    candidates = profiles_by_name.get(profile_name)
    if candidates is None:
        errors.append(f"{path}: release references unknown profile {profile_name!r}")
    elif len(candidates) > 1:
        errors.append(
            f"{path}: profile name {profile_name!r} is ambiguous"
            f" ({len(candidates)} catalog entries share this name)"
        )
    elif candidates[0] != profile_version:
        errors.append(
            f"{path}: release pins profile version {profile_version!r} but the catalog"
            f" entry for {profile_name!r} is version {candidates[0]!r}"
        )

    # -- compatibility: definition's constraint against the concrete
    # selected profile version. Never read from the profile side. --
    try:
        if not version_satisfies(profile_version, spec["definition"]["profileCompatibility"]):
            errors.append(
                f"{path}: profile version {profile_version!r} does not satisfy definition"
                f" profileCompatibility {spec['definition']['profileCompatibility']!r}"
            )
    except CatalogValidationError as exc:
        errors.append(f"{path}: {exc}")

    # -- exact-pair rollback: rollbackOf must replay one recorded prior
    # pair verbatim, never an independently chosen or synthetic mix. --
    rollback_of = spec.get("rollbackOf")
    if rollback_of is not None:
        history = {entry["bindingRevision"]: entry for entry in spec.get("history") or []}
        recorded = history.get(rollback_of)
        if recorded is None:
            errors.append(
                f"{path}: rollbackOf {rollback_of} has no matching entry in spec.history"
                " (rollback must select a prior recorded pair, not an independently chosen one)"
            )
        else:
            # spec.definition also carries profileCompatibility, which a
            # history entry does not -- compare only name/version so that
            # field doesn't produce a false mismatch.
            current_definition = {
                "name": spec["definition"]["name"],
                "version": spec["definition"]["version"],
            }
            if recorded["definition"] != current_definition or recorded["profile"] != spec["profile"]:
                errors.append(
                    f"{path}: rollbackOf {rollback_of} does not exactly match its recorded"
                    " (definition, profile) pair -- independent rollback of either half is rejected"
                )
        if spec.get("previousBindingRevision") != rollback_of:
            errors.append(
                f"{path}: rollbackOf {rollback_of} must equal previousBindingRevision"
                f" ({spec.get('previousBindingRevision')!r})"
            )


# --------------------------------------------------------------------------
# Catalog walk
# --------------------------------------------------------------------------


def validate_catalog(
    root: pathlib.Path,
    profile_schema: dict,
    release_schema: dict,
    policy: Policy,
    errors: list,
    cwft_dir: pathlib.Path | None = None,
):
    profiles_by_name: dict[str, list[str]] = {}

    profiles_dir = root / "execution-profiles"
    for profile_path in sorted(profiles_dir.glob("*/profile.yaml")) if profiles_dir.is_dir() else []:
        result = validate_profile_file(profile_path, profile_schema, policy, errors)
        if result is None:
            continue
        name, version = result
        profiles_by_name.setdefault(name, []).append(version)
        # Skipped unless a template directory is supplied. A selftest
        # fixture is a synthetic catalog whose profiles must name a real
        # CWFT (approvedSandboxes forces that) while carrying made-up
        # budgets, so checking it against the DEPLOYED templates would fail
        # every fixture for the wrong reason. A fixture that wants to
        # exercise this check ships its own cluster-templates/ instead.
        if cwft_dir is not None:
            validate_profile_against_cwft(
                profile_path, load_yaml(profile_path), errors, cwft_dir
            )

    # profiles_by_name maps name -> list of versions seen across every
    # execution-profiles/*/profile.yaml in this catalog root; more than one
    # entry for the same name is exactly the "ambiguous version" case,
    # handled in validate_release_file.
    releases_dir = root / "releases"
    for release_path in sorted(releases_dir.glob("*/*.yaml")) if releases_dir.is_dir() else []:
        validate_release_file(release_path, release_schema, policy, profiles_by_name, errors)


def run(root: pathlib.Path) -> list:
    errors: list = []
    policy = load_policy(errors)
    if policy is None:
        return errors
    profile_schema = load_json(SCHEMAS / "execution-profile.schema.json")
    release_schema = load_json(SCHEMAS / "release-binding-intent.schema.json")
    validate_catalog(
        root,
        profile_schema,
        release_schema,
        policy,
        errors,
        cwft_dir=CWFT_DIR if root == CATALOG else None,
    )
    return errors


def case_policy_path(case_dir: pathlib.Path) -> pathlib.Path:
    """A fixture may ship its own policy.yaml to exercise policy loading."""
    fixture_policy = case_dir / "policy.yaml"
    return fixture_policy if fixture_policy.exists() else CATALOG / "policy.yaml"


def case_cwft_dir(case_dir: pathlib.Path) -> pathlib.Path | None:
    """A fixture ships cluster-templates/ to opt into the CWFT cross-check.

    Without this the effective-value check would be unreachable from
    --selftest, and a weakened version of it could be merged green. Opting
    in per fixture keeps the other 18 cases from being checked against
    production templates they have nothing to do with.
    """
    fixture_cwfts = case_dir / "cluster-templates"
    return fixture_cwfts if fixture_cwfts.is_dir() else None


def run_selftest() -> list:
    problems: list = []
    profile_schema = load_json(SCHEMAS / "execution-profile.schema.json")
    release_schema = load_json(SCHEMAS / "release-binding-intent.schema.json")

    for case_dir in sorted((FIXTURES_ROOT / "valid").glob("*")) if (FIXTURES_ROOT / "valid").is_dir() else []:
        if not case_dir.is_dir():
            continue
        errors: list = []
        policy = load_policy(errors, case_policy_path(case_dir))
        if policy is not None:
            validate_catalog(
                case_dir,
                profile_schema,
                release_schema,
                policy,
                errors,
                cwft_dir=case_cwft_dir(case_dir),
            )
        if errors:
            problems.append(f"valid fixture {case_dir.name} unexpectedly failed:")
            problems.extend(f"  {e}" for e in errors)

    for case_dir in sorted((FIXTURES_ROOT / "invalid").glob("*")) if (FIXTURES_ROOT / "invalid").is_dir() else []:
        if not case_dir.is_dir():
            continue
        errors = []
        policy = load_policy(errors, case_policy_path(case_dir))
        if policy is not None:
            validate_catalog(
                case_dir,
                profile_schema,
                release_schema,
                policy,
                errors,
                cwft_dir=case_cwft_dir(case_dir),
            )
        if not errors:
            problems.append(f"invalid fixture {case_dir.name} unexpectedly passed (expected at least one error)")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="also replay scripts/tests/fixtures/agent-platform/{valid,invalid} and assert expected pass/fail",
    )
    args = parser.parse_args()

    errors = run(CATALOG)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"agent platform catalog: {len(errors)} error(s)", file=sys.stderr)
        return 1
    profile_count = len(list((CATALOG / "execution-profiles").glob("*/profile.yaml")))
    release_count = len(list((CATALOG / "releases").glob("*/*.yaml")))
    print(f"validated {profile_count} execution profile(s), {release_count} release intent(s)")

    if args.selftest:
        problems = run_selftest()
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            print(f"agent platform selftest: {len(problems)} problem(s)", file=sys.stderr)
            return 1
        valid_count = len(list((FIXTURES_ROOT / "valid").glob("*"))) if (FIXTURES_ROOT / "valid").is_dir() else 0
        invalid_count = len(list((FIXTURES_ROOT / "invalid").glob("*"))) if (FIXTURES_ROOT / "invalid").is_dir() else 0
        print(f"selftest ok: {valid_count} valid fixture(s), {invalid_count} invalid fixture(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
