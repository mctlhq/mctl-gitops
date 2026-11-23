# Tasks: issue-2540-adr-temporal-jwks-trust-path-decision-fo

- [ ] 1. Write `docs/adr/0004-temporal-jwks-trust-path.md` (status `Proposed`,
  issue #2540; inputs ADR 0003, `docs/runbooks/temporal-authz-role-matrix.md`,
  `docs/spikes/2506-temporal-jwt-issuer.md`) with sections: Context
  (stock provider limits, `iss` not validated, plaintext Vault listener,
  2026-10-09 public-path failure), Decision (GitOps-pinned JWKS over loopback
  HTTPS, pod-local cert-manager CA delivered via `SSL_CERT_FILE` to the
  frontend only, native sidecar, fallback Deployment form, `http://` rejected),
  Key rotation (6-step zero-gap procedure, Vault auto-rotation prohibited),
  Emergency revocation (PR removal + break-glass scale-to-zero, proposed
  `refreshInterval: 1m`, target <= 15 min), Failure modes (fail closed),
  Alternatives (Vault HTTPS with internal CA; public `secrets.mctl.ai`; custom
  key provider build; loopback `http://`), Canary obligations C1-C8 plus
  per-rejected-option obligations, Stop condition / fallback outcome
  `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH`, Open items (chart sidecar keys,
  `SSL_CERT_FILE` on the shipped binary, Vault `rotation_period` limits,
  revocation latency target). States explicitly that no runtime change
  follows from merging it. — DoD: file exists, every claim about Temporal or
  Vault behaviour cites the matrix doc, a repo path, or is labelled
  NOT_OBSERVED; only English, no emoji.
- [ ] 2. Add `docs/adr/0004-rubric.yaml` in the format of
  `docs/adr/0003-rubric.yaml` with candidates
  `pinned-jwks-loopback-https`, `vault-https-internal-ca`,
  `vault-public-secrets-mctl-ai`, `custom-key-provider-build` and dimensions
  (JWKS exclusivity, stock binary, rotation/revocation, blast radius on
  Vault, operability/rollback) (depends on 1). — DoD: YAML parses (`yq . file`)
  and the candidate names match the ADR's alternatives.
- [ ] 3. Amend `docs/adr/0003-temporal-client-authz.md`: decision 4 gets one
  sentence "Trust path decided in ADR 0004 (pinned JWKS over loopback
  HTTPS)"; "Rollout and rollback" global-stop sentence gets "see ADR 0004 for
  the pinned-key equivalent"; "Open items" lists ADR 0004. Status unchanged
  (depends on 1). — DoD: `git diff` touches only those lines; status line
  still `Proposed`.
- [ ] 4. Update `docs/runbooks/temporal-client-auth.md`: unresolved unknown 4
  points to ADR 0004 and lists its open items; node C row notes "ADR 0004
  Proposed"; verdict stays `BLOCKED` (depends on 1). — DoD: verdict line
  unchanged; DAG diagram unchanged.
- [ ] 5. Update `docs/runbooks/temporal-auth-canary.md`: the Isolation JWKS
  bullet names the selected option; add steps C1-C8 (or reference ADR 0004
  section) and add stop conditions "C1 fails" and "C2 accepted" (depends
  on 1). — DoD: S1-S17 numbering unchanged; new steps are additive.
- [ ] 6. Open the PR on a feature branch (not main) with label/route for
  architecture review and separate owner approval per the DAG table. — DoD:
  PR passes `validate-manifests.yml` (no manifest touched) and
  `claude-review.yml`; the PR body states "decision only, no runtime change".

## Tests

- [ ] T1. `git diff --stat origin/main` shows only files under `docs/adr/`
  and `docs/runbooks/` (no `platform-gitops/` or `infrastructure/` path).
- [ ] T2. `grep -n 'http://' docs/adr/0004-temporal-jwks-trust-path.md` shows
  only occurrences in a "rejected" context.
- [ ] T3. ADR 0004 contains each required element from the issue: the chosen
  option, the rotation procedure, the fail-closed behaviour when JWKS is
  unreachable, and canary obligations for each reviewed option (manual
  checklist in the PR body).
- [ ] T4. `yq . docs/adr/0004-rubric.yaml` succeeds; markdown links in the new
  and edited documents resolve to existing repo paths.
- [ ] T5. Consistency check: ADR 0003, the client-auth runbook, the canary
  contract and spike #2506 all describe the same JWKS path, and none of them
  says a trust path is enabled.

## Rollback

Documentation only. Revert the PR, which restores ADR 0003 decision 4 and
runbook unknown 4 to "undecided". No cluster, Vault or Temporal state is
affected. If the architecture review rejects the selected option, amend
ADR 0004 to outcome `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` instead of
reverting, so the reviewed alternatives stay on record.
