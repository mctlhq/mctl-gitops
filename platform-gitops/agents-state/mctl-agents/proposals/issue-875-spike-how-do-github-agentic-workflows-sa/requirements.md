# Spike #875: GitHub Agentic Workflows guardrails compared with DevLoop, and an adoption decision

## Context

GitHub Agentic Workflows (gh-aw) went generally available on 2026-10-28. It is an open source framework
that runs coding agents inside GitHub Actions. The changelog describes four guardrails. Agents run with
read-only permissions by default. Their outputs pass through "safe outputs" validation and are executed by
separate jobs that hold the permissions. Agents run in a sandboxed container behind the Agent Workflow
Firewall (AWF), with optional micro-VMs. A threat detection job scans proposed changes before they are
applied. DevLoop (Temporal + Argo, ExecutionProfiles, the ADR 014 policy checkpoint, staged proposal
publishing, human approval) solves the same problem with its own mechanisms. Issue #875 asks how the two
compare and whether any gh-aw pattern should be adopted or should interoperate with DevLoop.

The issue limits the scope. gh-aw is a source of patterns to compare, not a replacement runtime.
Temporal/Argo, MCTL identity/policy/approval/evidence and the existing DevLoop authority boundaries stay
canonical. Safe outputs, permission defaults, network/sandbox isolation and reusable enforcement patterns
must each be evaluated on its own. The deliverable is a docs-only spike report in the same form as
`docs/spikes/852-sandbox-isolation-delta.md`, with a guard test and a recorded owner decision. Any adopted
pattern becomes a separately filed follow-up issue. This spike makes no runtime change.

## User stories

- AS a platform owner I WANT each gh-aw guardrail mapped onto the DevLoop control that covers it (or a
  named gap) SO THAT I can decide what to adopt without re-deriving the comparison.
- AS a security reviewer I WANT every comparison row tied to a repository or gitops file, or to a gh-aw
  source, SO THAT no claim rests on marketing text alone.
- AS an implementer of follow-ups I WANT each adopted pattern to arrive as a scoped issue with a control
  and a rollback SO THAT adoption happens in small, reviewable changes.
- AS a DevLoop maintainer I WANT existing gaps (#807 G1/G2, #852 D1-D3, #868-#870) cited rather than
  duplicated SO THAT this spike adds only new information.

## Acceptance criteria (EARS)

- WHEN the spike is implemented THE SYSTEM SHALL add `docs/spikes/875-gh-aw-guardrail-comparison.md` with
  exactly one `STATUS:` line whose value is `DRAFT` or one of `ADOPT_PATTERNS`, `REFERENCE_ONLY`,
  `NO_ACTION`.
- THE SYSTEM SHALL evaluate the following dimensions in separate sections or rows: safe outputs,
  permission defaults, network/sandbox isolation, threat detection, reusable enforcement patterns, and
  interoperability.
- WHEN a comparison row is written THE SYSTEM SHALL fill seven cells: `id`, `dimension`, `gh_aw_pattern`,
  `devloop_today` (with evidence paths), `status`, `owner`, `follow_up`. `status` SHALL be one of
  `adopt`, `already-covered`, `covered-by-807`, `covered-by-852`, `not-applicable`, `not-observed`.
- IF a gh-aw claim could not be verified from a retrieved primary source THEN THE SYSTEM SHALL mark that
  row `not-observed` and SHALL NOT use it to justify an `adopt` status.
- IF a row's status is `adopt` THEN THE SYSTEM SHALL name a follow-up with an owner repository, the
  concrete control, and a rollback, and the decision section SHALL list it.
- WHILE the report cites a gap already tracked by #807, #830, #852 or #868-#870 THE SYSTEM SHALL
  reference that issue instead of opening a duplicate follow-up.
- THE SYSTEM SHALL state in the report that the following remain canonical: Temporal/Argo, the ADR 014
  checkpoint, ExecutionProfiles in mctl-gitops `agent-platform/`, ADR 013 human input, ADR 016/ADR 021
  approval and completion, and ADR 018 evidence. Nothing is replaced by gh-aw.
- WHEN `tests/test_spike_875_report.py` runs THE SYSTEM SHALL check the STATUS line, the seven-cell rows,
  non-empty evidence, the allowed status values, that every dimension is present, and that the report
  contains no token-shaped strings.
- THE SYSTEM SHALL NOT change any runtime code, CWFT, ExecutionProfile or policy in this spike.

## Out of scope

- Running agents on gh-aw, adding gh-aw workflow files to any mctlhq repository, or replacing Argo/Temporal
  runtimes.
- Implementing any adopted pattern. Each one is a follow-up issue.
- Re-deciding #852 D1-D3 or #807 G1-G6.
- Writing the SpikeDefinition `decision.verdict` in `mctlhq/.github` `roadmap/spikes/`. The owner records
  it by hand (see `orchestrator/spike_issue.py`).

## Open questions

- gh-aw primary sources were only partly retrieved during investigation: the GA changelog, and the first
  100k characters of the safe-outputs reference. AWF network rules, the threat detection job's internals,
  "integrity filter rules" and staged mode were not read. The implementer must re-fetch them, and any row
  it still cannot verify stays `not-observed`.
- The decision token is the owner's choice. This proposal expects `ADOPT_PATTERNS`, scoped to the
  per-output-type limits and the agent-container write-credential removal (design.md rows S2, P1), but
  does not presume it.
- Should interoperability include gh-aw calling the mctl MCP server through Actions OIDC? The deploy path
  already accepts Actions OIDC. This proposal records it as an interop row only and does not design it.
