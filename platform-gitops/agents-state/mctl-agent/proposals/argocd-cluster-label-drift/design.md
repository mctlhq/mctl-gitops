# Design: argocd-cluster-label-drift

## Current state
The `ArgoCDDrift` builtin Go skill lives in `internal/skill/builtin/` (see
`context/architecture.md` — tier 1, compiled into the binary). It parses Argo CD
Application and cluster resources to detect configuration drift and is one of the 9
universal patterns. Cluster version labels are currently read and compared as raw
strings or split on `"."` expecting exactly two numeric segments (`Major.Minor`). This
works correctly with Argo CD versions up to and including v3.4.0.

As of Argo CD v3.4.1, the ApplicationSet cluster generator writes version labels in
`"vMajor.Minor.Patch"` format (a leading `"v"` plus a third numeric component). The
existing string comparison and two-segment split will produce a mismatch for every
cluster on an upgraded platform, silently suppressing drift events (false negatives).

## Proposed solution
Introduce a small, pure-Go version label normaliser (`parseClusterVersionLabel`) inside
the `ArgoCDDrift` skill package. The normaliser:

1. Strips a leading `"v"` if present.
2. Splits on `"."` and extracts the `Major` and `Minor` integers using `strconv.Atoi`.
3. Returns a typed `ClusterVersion{Major, Minor int}` struct for comparison.
4. Returns an error (triggering the slog warning path) if the input does not match
   either recognised format.

The existing comparison site is updated to call `parseClusterVersionLabel` on both the
observed label (from the live cluster resource) and the expected label (from the skill
configuration or ApplicationSet spec). Drift is raised only when the parsed structs
differ, not when the raw strings differ — this eliminates false positives caused purely
by format differences (e.g., `"1.29"` vs `"v1.29.4"` would now compare as equal on
major+minor, avoiding a spurious drift alert).

The table-driven test suite for `ArgoCDDrift` is extended with cases covering:
- Legacy format input (`"1.29"`)
- New format input (`"v1.29.4"`)
- Cross-format comparison (legacy expected vs new observed, and vice versa)
- Malformed input (`""`, `"abc"`, `"v1"`, `"v1.abc.4"`)

No new external dependencies are introduced. No database schema changes are needed. No
API endpoint changes are required.

## Alternatives

### Option A: String normalisation at comparison time (prefix strip only)
Strip the leading `"v"` and trailing `.Patch` segment before comparing as raw
`"Major.Minor"` strings. Simpler than a typed struct, but brittle: it relies on string
manipulation that will fail for any further label format evolution. Dropped in favour of
the typed-struct approach which is more robust and more testable.

### Option B: Accept any label format by using semver library
Import a semver parsing library (e.g., `golang.org/x/mod/semver` or
`github.com/Masterminds/semver`) to handle the full semver surface. Dropped because the
`ArgoCDDrift` use case only requires Major+Minor comparison, a full semver library is
overkill, and adding a new dependency widens the supply-chain surface for minimal gain.

### Option C: Externalise the version label format as a YAML skill configuration knob
Allow operators to configure the expected format via a YAML skill overlay, delaying the
fix to configuration rather than code. Dropped because the format change is a hard
upstream change, not an operator choice — the skill must handle both formats
unconditionally.

## Platform impact

### Migrations
None. The change is entirely internal to the `ArgoCDDrift` skill package. No database
schema, no CRD change, no config-map change.

### Backward compatibility
The normaliser accepts the legacy `"Major.Minor"` format unchanged, so the skill
continues to work correctly against any Argo CD version prior to v3.4.1. The change is
transparent during a rolling platform upgrade.

### Resource impact (labs tenant)
CPU and memory overhead of the normaliser is negligible (integer parsing on label
strings). No memory increase is expected. The `labs` tenant memory budget is not
affected.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Cross-format comparison hides a real version mismatch (e.g., 1.29 vs v1.30.1) | Comparison is on parsed Major+Minor integers — a minor version change is still detected |
| Pre-release label formats (e.g., `v1.30.0-rc.1`) cause parse errors | The error path logs a structured warning and skips the version-label drift check for that attribute, preventing a crash or silent fail |
| New Argo CD versions introduce a fourth label segment | The parser extracts only Major and Minor; Patch and pre-release are intentionally ignored — safe to extend later if needed |
| Test coverage gap | New table-driven cases are required as part of the DoD for the implementation task |
