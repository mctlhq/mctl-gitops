# Agent isolation gate (mctl-gitops#2292)

`validate-manifests.yml` runs `scripts/validate-agent-isolation-baseline.py`. It runs a
vendored, pinned copy of the mctl-agents isolation auditor (spike mctlhq/mctl-agents#807)
over `platform-gitops/` and compares the JSON matrix with `baseline.json`.

## Source and pin

- Source: `tools/agent_isolation_audit.py` in `mctlhq/mctl-agents`, vendored verbatim
  (never edited here) into `auditor/`.
- Pin: `auditor.pin.json` records the repo, the full commit SHA, the vendored files and
  their SHA-256. Commit `eb6297b78c9c` includes the #921 fix (NetworkPolicy peers that
  combine `namespaceSelector` and `podSelector`).
- Why vendored: the run is hermetic, and a reviewer sees any change of the oracle in the
  PR diff. On a PR that touches the pin or `auditor/`, and on every push to `main`, CI
  also fetches the pinned file from the pinned commit and requires byte identity
  (`--verify-upstream`).
- The auditor is one self-contained file (PyYAML only). It reports no version, so the pin
  `auditor_version` is `null` and the SHA-256 is the version.

## Output contract (output `schema_version` 2)

`{"schema_version", "files_read", "templates", "rows"}`. A row is
`{primitive, scope, status, severity, source, field, detail, recommendation}`; the key is
`(primitive, scope, field)`. Statuses: `enforced`, `partial`, `absent`,
`declared-not-enforced`, `not-observed`. Agent steps are `templates[*]` entries with
`agent: true`, named `<cwft>/<template>` in `scope`. The egress-proxy `allow-agent-ingress`
policy has a row (`NetworkPolicy/cross-namespace`, scope `allow-agent-ingress`).

## Rules the gate enforces

- Missing baseline, unknown `schema_version`, duplicate keys, a non-JSON or non-zero
  auditor, or a baseline whose `auditor` differs from the pin: fail closed.
- An `enforced` row that is anything else (including missing or `not-observed`): fail.
- An accepted gap (non-`enforced`, with `issue`) that is unchanged: pass, listed in the job
  summary. Worsened: fail. Closed or otherwise changed: fail until the baseline is updated
  in the same PR. A gap that becomes `not-observed` or missing: fail.
- A row not in the baseline: fail. A new agent step must also have every control that
  all baselined agent steps have as `enforced`.
- Rows owned by `validate-agent-pod-security` (fixed `POD_SECURITY_OWNED` table in the
  script) are recorded but not compared; that validator stays their only check.
- CI never writes `baseline.json`.

## Upgrading the auditor

1. Copy the new file(s) from the chosen mctl-agents commit into `auditor/` and update
   `auditor.pin.json` (commit, SHA-256, `includes`).
2. Run `scripts/validate-agent-isolation-baseline.py --regenerate --out /tmp/new.json`
   and diff it against `baseline.json`. New non-enforced rows come out with
   `issue: null`; fill in the owning issue.
3. Commit the new `baseline.json` in the same PR. The PR body must include the baseline diff
   and explain each changed status as an auditor interpretation change or a GitOps change.
   `baseline.auditor` changes in that diff, which is the signal that the oracle moved.

A GitOps-only PR leaves `baseline.auditor` alone, so any baseline row diff in it is a real
posture change. Closing a gap: fix it and update the row in the same PR.

Initial accepted gaps all reference mctlhq/mctl-agents#807; replace with narrower issues as
they are filed.
