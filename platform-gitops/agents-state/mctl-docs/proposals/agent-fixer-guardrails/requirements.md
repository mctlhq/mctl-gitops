# mctl-agent fixer guardrails: scope and refusal behaviour

version-status: unverified, see commit SHA (8f91420, 42cce34, ca6beca). Shipped status is only inferred from the mctl-gitops bump to mctl-agent 2.9.2; not confirmed via MCP.

## Context
On 2026-11-13 three fixes landed in `mctl-agent` (`internal/fixer/`): 8f91420 (patch only the YAML path a fix names), ca6beca (refuse diagnosis values that would not stay one scalar) and 42cce34 (refuse no-op diagnoses and Unicode line breaks). Together they define what the self-healing fixer will and will not put into an auto-generated PR.

Reviewers of agent PRs, and tenants who wonder why no PR appeared for an alert, currently have no documented description of these guarantees. `docs/platform/components.md` (mctl-agent block) should describe them.

## User stories
- AS a tenant owner reviewing an agent-generated PR I WANT to know the fixer edits exactly one YAML scalar line SO THAT I can review the diff with confidence.
- AS a developer I WANT to know when the fixer refuses a diagnosis SO THAT I understand why no PR was opened.
- AS a platform admin I WANT to know the fixer errors rather than guesses SO THAT I can trust its output.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/components.md` THE SYSTEM SHALL show, in the mctl-agent section, that a fix edits exactly one scalar line, located by a dotted path walked from the document root through block mappings only, preserving indentation, quoting and inline comment.
- WHEN the fixer cannot prove the target (sequences, flow style, missing or nested key, or a current value differing from the diagnosed one) THE SYSTEM SHALL document that this is an error and no PR is opened.
- WHEN a suggested value equals the current value THE SYSTEM SHALL document that it is refused as a no-op.
- WHEN a suggested value contains a newline, non-printable rune (including NEL, LS, PS), an inline " #", ": ", or a flow/alias indicator THE SYSTEM SHALL document that it is refused, not escaped.
- IF a reader wonders why no PR appeared THEN THE SYSTEM SHALL list these refusal reasons.
- WHILE shipped status is unverified THE SYSTEM SHALL keep the version-status tag in the review notes (not in the published page).

## Out of scope
- Telegram token redaction (afde427).
- Fixer internals beyond the commit messages; migration guide; localisation.
- Exact error message strings: `<TODO: confirm with author of 8f91420>`.
