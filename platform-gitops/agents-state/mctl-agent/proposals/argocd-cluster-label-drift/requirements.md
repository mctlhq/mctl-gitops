# Update ArgoCDDrift skill for Argo CD v3.4.1 cluster version label format change

## Context
Argo CD v3.4.1 changed the format of the cluster version label used by the
ApplicationSet cluster generator from `"Major.Minor"` (e.g., `"1.29"`) to
`"vMajor.Minor.Patch"` (e.g., `"v1.29.4"`). The `ArgoCDDrift` builtin Go skill in
`internal/skill/builtin/` compares cluster resource labels against expected values when
evaluating whether an Application is drifted. Once the platform upgrades Argo CD to
v3.4.1 or later, any version-label comparison inside `ArgoCDDrift` will silently
mismatch: the label the skill reads will carry the new `"vMajor.Minor.Patch"` format
while the skill's parser still expects `"Major.Minor"`. The result is false negatives —
real drift events go undetected and no fix PR is opened.

This proposal adds a format-aware parser and an extended table-driven test suite to the
`ArgoCDDrift` skill so it correctly handles both the legacy and the new label format,
making the skill robust across the Argo CD version boundary.

## User stories
- AS a platform engineer I WANT the `ArgoCDDrift` skill to correctly parse cluster
  version labels in both the old `"Major.Minor"` and new `"vMajor.Minor.Patch"` formats
  SO THAT drift detection remains accurate after the platform's Argo CD upgrade to v3.4.1.
- AS an on-call engineer I WANT false-negative drift events to be eliminated SO THAT I
  am not left without an automated fix PR when a genuine configuration drift occurs on
  the `admins` tenant.
- AS a developer maintaining the mctl-agent codebase I WANT the version-label parsing
  logic covered by table-driven tests SO THAT future Argo CD label changes are caught in
  CI before they reach production.

## Acceptance criteria (EARS notation)
- WHEN the `ArgoCDDrift` skill receives a cluster resource whose version label is in the
  format `"vMajor.Minor.Patch"` (e.g., `"v1.29.4"`) THE SYSTEM SHALL correctly parse
  the major and minor components and compare them to the expected values without error.
- WHEN the `ArgoCDDrift` skill receives a cluster resource whose version label is in the
  legacy format `"Major.Minor"` (e.g., `"1.29"`) THE SYSTEM SHALL continue to parse and
  compare it correctly, maintaining backward compatibility.
- WHEN a version label does not match either recognised format THE SYSTEM SHALL log a
  structured warning (slog) including the raw label value and SHALL NOT mark the
  Application as drifted solely on the basis of an unparseable label.
- WHILE the `ArgoCDDrift` skill is evaluating cluster labels in either format THE SYSTEM
  SHALL produce a drift decision (match or mismatch) within the same latency budget as
  before this change.
- IF the parsed version label matches the expected version THE SYSTEM SHALL NOT raise a
  drift event for that cluster attribute.
- IF the parsed version label does not match the expected version THE SYSTEM SHALL raise
  a drift event, set the ticket severity to the appropriate level, and include the raw
  label values (observed vs expected) in the evidence payload.

## Out of scope
- Changes to YAML skills or remote skills — only the `ArgoCDDrift` builtin Go skill is
  in scope.
- Upgrading Argo CD itself on the platform — covered by a separate proposal.
- Changes to how ApplicationSet generates cluster selectors — mctl-agent is a consumer,
  not a producer, of these labels.
- Handling label formats beyond `"Major.Minor"` and `"vMajor.Minor.Patch"` (e.g.,
  pre-release tags such as `"v1.30.0-rc.1"`) — deferred unless evidence of usage exists.
