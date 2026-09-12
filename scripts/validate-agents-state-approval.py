#!/usr/bin/env python3
"""Refuse a proposal that is unrunnable the moment it is committed.

A `.status.yaml` that reads `status: accepted` while demanding a human
approval it does not carry can never be implemented by any supported path.
mctl-agents' `human_approval_satisfied()` correctly refuses it, and
`mctl-agents-approve` used to short-circuit on anything already accepted
without recording an approver. Both sides exited 0 and reported success, so
the proposal simply never moved -- `mctl-design/issue-21-...` sat in that
state for five weeks before anyone noticed (mctl-agents#349).

mctl-agents#358 added a write-time guard, but it only binds writers inside
that repository. It cannot stop a tool committing YAML straight into this
one, which is exactly how the stuck proposal was created. This is that gate
(gitops#1207).

The predicate below deliberately mirrors `human_approval_satisfied()` in
`orchestrator/proposal_state.py` rather than inventing its own rule, and
keeps its fail-closed direction: only a recognisably falsey value waives the
gate, an absent `control` block means "never asked", and a `control` block
that is present but not a mapping is corrupt rather than absent. Those
semantics were hardened twice by review; if they change there, change them
here. PARITY below pins the contract with the cases that actually differ, each
measured against orchestrator/proposal_state.py rather than read off it, and
--selftest asserts them.
"""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
AGENTS_STATE = ROOT / "platform-gitops/agents-state"

# Mirrors orchestrator/proposal_state.py. Only these waive the gate; anything
# unrecognised requires an approval, so a typo or a new spelling fails closed
# rather than silently letting a proposal through.
FALSEY = {"false", "no", "0", "off", ""}
ANONYMOUS_APPROVERS = {"", "unknown", "none", "null"}


def requires_human_approval(data: dict) -> bool:
    """Whether this proposal demands a recorded human approver."""
    control = data.get("control")
    if control is None:
        # No control block at all means the proposal never asked. The
        # incident-responder writes `accepted` with no control block and
        # would be stranded by any other default.
        return False
    if not isinstance(control, dict):
        # Present but unreadable asked for something we cannot evaluate.
        return True
    required = control.get("requires_human_approval")
    if required is None or required is False:
        return False
    if isinstance(required, str) and required.strip().lower() in FALSEY:
        return False
    if isinstance(required, int) and not isinstance(required, bool) and required == 0:
        return False
    return True


def has_named_approver(data: dict) -> bool:
    """Whether an approval record exists that would satisfy the gate."""
    approval = data.get("approval")
    if not isinstance(approval, dict):
        return False
    approved_by = approval.get("approved_by")
    if not isinstance(approved_by, str):
        return False
    return approved_by.strip().lower() not in ANONYMOUS_APPROVERS


def unrunnable(data: dict) -> str | None:
    """A reason string when the proposal can never run as written, else None."""
    if data.get("status") != "accepted":
        return None
    if not requires_human_approval(data):
        return None
    # Shape before approver, deliberately. `human_approval_satisfied()` returns
    # False for a non-mapping `control` BEFORE it ever looks at `approval`, so a
    # corrupt control block plus a perfectly good approver is still blocked
    # over there. Checking the approver first accepted exactly that
    # combination and left CI green on an unrunnable proposal (Codex P1 on
    # gitops#1210). Verified against orchestrator/proposal_state.py at
    # mctl-agents c13df87: {"status": "accepted", "control": "yes please",
    # "approval": {"approved_by": "mashkovd"}} -> satisfied=False.
    control = data.get("control")
    if not isinstance(control, dict):
        return (
            "control block is present but is not a mapping, so the approval "
            "requirement cannot be evaluated and the implementer fails closed "
            "on it regardless of any approval record"
        )
    if has_named_approver(data):
        return None
    return (
        "status is 'accepted' and control.requires_human_approval is set, but no "
        "approval.approved_by names a real approver"
    )


def check_dir(agents_state: Path) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    for path in sorted(agents_state.glob("*/proposals/*/.status.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            findings.append((path, f"is not parseable YAML: {exc}"))
            continue
        if data is None:
            # A genuinely empty document. It carries no `status`, so it is not
            # unrunnable in this validator's sense and something else owns it.
            continue
        if not isinstance(data, dict):
            # NOT `or {}`: that turned a falsey non-mapping root -- `[]`,
            # `false`, `0`, `""` -- into an empty mapping, which then passed the
            # type check below and left the corruption unreported (Codex P2 on
            # gitops#1210). Only an empty document is defaulted, above.
            findings.append(
                (path, f"does not parse to a mapping (got {type(data).__name__})")
            )
            continue
        reason = unrunnable(data)
        if reason:
            findings.append((path, reason))
    return findings


def report(findings: list[tuple[Path, str]], agents_state: Path) -> int:
    if not findings:
        return 0
    for path, reason in findings:
        rel = path.relative_to(agents_state)
        print(f"::error file={path.relative_to(ROOT)}::{rel}: {reason}", file=sys.stderr)
    print(
        "\n"
        f"{len(findings)} proposal(s) cannot be implemented by any supported path.\n"
        "\n"
        "Neither side of the pipeline fails on this -- the approve operation and the\n"
        "implementer both exit 0 -- so it is invisible once merged.\n"
        "\n"
        "Fix by publishing the proposal as `status: proposed` and approving it, which\n"
        "is what records `approval.approved_by`. Do NOT hand-write that field: it\n"
        "forges the exact record the gate exists to require (gitops#986).\n"
        "See mctl-agents#349 and gitops#1207.",
        file=sys.stderr,
    )
    return 1


# --- self-test ------------------------------------------------------------
#
# A guard that has never been seen to fail is not known to work -- the same
# reason every other detector in validate-manifests.yml runs --selftest before
# its real pass. This drives the real check_dir() over throwaway fixtures
# rather than reimplementing the predicate, so it tests the code that ships.

SELFTEST_CASES = [
    # (name, yaml, should_be_flagged)
    ("accepted_gated_no_approval", """
status: accepted
control:
  requires_human_approval: true
""", True),
    ("accepted_gated_quoted_true", """
status: accepted
control:
  requires_human_approval: "true"
""", True),
    ("accepted_gated_anonymous_approver", """
status: accepted
control:
  requires_human_approval: true
approval:
  approved_by: unknown
""", True),
    ("accepted_control_not_a_mapping", """
status: accepted
control: "yes please"
""", True),
    ("accepted_gated_with_approver", """
status: accepted
control:
  requires_human_approval: true
approval:
  approved_by: 'mashkovd'
""", False),
    # The incident-responder shape. Defaulting to deny would strand it.
    ("accepted_no_control_block", """
status: accepted
updated_by: mctl-agents[bot]
""", False),
    ("accepted_gate_explicitly_false", """
status: accepted
control:
  requires_human_approval: false
""", False),
    ("accepted_gate_string_no", """
status: accepted
control:
  requires_human_approval: "no"
""", False),
    # Not accepted yet: the gate is not this validator's business.
    ("proposed_gated_no_approval", """
status: proposed
control:
  requires_human_approval: true
""", False),
    ("implemented_gated_no_approval", """
status: implemented
control:
  requires_human_approval: true
""", False),
    # --- parity cases -------------------------------------------------------
    #
    # The four shapes where a plausible reading diverges from what mctl-agents
    # actually does. Each was measured by calling human_approval_satisfied()
    # from orchestrator/proposal_state.py at mctl-agents c13df87, not inferred:
    #
    #   {"control": None}                      -> satisfied=True   (runs)
    #   {} (no control key)                    -> satisfied=True   (runs)
    #   {"control": "yes please"}              -> satisfied=False  (blocked)
    #   {"control": "yes please", approver}    -> satisfied=False  (blocked)
    #
    # The last is why the shape check must come BEFORE the approver check: over
    # there a corrupt control block fails closed without ever reading the
    # approval, so a named approver does not rescue it (Codex P1, gitops#1210).
    ("accepted_control_null", """
status: accepted
control:
""", False),
    ("accepted_control_not_mapping_with_approver", """
status: accepted
control: "yes please"
approval:
  approved_by: 'mashkovd'
""", True),
    # A falsey non-mapping root used to be swallowed by `or {}` and reported as
    # clean (Codex P2, gitops#1210).
    ("root_is_empty_list", "[]\n", True),
    ("root_is_false", "false\n", True),
]


def selftest() -> int:
    import tempfile

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, body, _ in SELFTEST_CASES:
            d = root / "svc" / "proposals" / name
            d.mkdir(parents=True)
            (d / ".status.yaml").write_text(body.lstrip("\n"))
        flagged = {p.parent.name for p, _ in check_dir(root)}

    for name, _, should_flag in SELFTEST_CASES:
        did_flag = name in flagged
        if did_flag != should_flag:
            verb = "did not flag" if should_flag else "wrongly flagged"
            print(f"self-test FAILED: {verb} {name}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"self-test FAILED: {failures} case(s)", file=sys.stderr)
        return 1
    flagged_n = sum(1 for _, _, f in SELFTEST_CASES if f)
    print(
        f"validate-agents-state-approval.py self-test: rejects {flagged_n} unrunnable "
        f"shape(s), accepts {len(SELFTEST_CASES) - flagged_n} legitimate one(s)"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    if not AGENTS_STATE.is_dir():
        print(f"❌ {AGENTS_STATE} does not exist", file=sys.stderr)
        return 1
    findings = check_dir(AGENTS_STATE)
    rc = report(findings, AGENTS_STATE)
    if rc == 0:
        n = len(list(AGENTS_STATE.glob("*/proposals/*/.status.yaml")))
        print(f"✅ {n} proposal(s) checked; none are unrunnable by construction")
    return rc


if __name__ == "__main__":
    sys.exit(main())
