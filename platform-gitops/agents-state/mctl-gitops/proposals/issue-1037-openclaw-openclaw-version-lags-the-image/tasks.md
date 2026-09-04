# Tasks: issue-1037-openclaw-openclaw-version-lags-the-image

- [ ] 1. Bump `env.OPENCLAW_VERSION` to match `image.tag` in
      `platform-gitops/services/admins/openclaw/values.yaml` (line 71,
      `"2026.5.14-beta.1"` -> `"2026.7.11-beta.2"`) and
      `platform-gitops/services/labs/openclaw/values.yaml` (line 60, same
      change). Leave `platform-gitops/services/ovk/openclaw/values.yaml`
      untouched — its two fields already match.
      DoD: `grep -A1 -n 'image:\|OPENCLAW_VERSION' <file>` shows identical
      version strings for `image.tag` and `env.OPENCLAW_VERSION` in both
      edited files; `helm template test platform-gitops/helm-charts/base-service
      -f <file>` renders successfully (per `CLAUDE.md`'s "Testing &
      Validation" dry-run command); no other line in either file changes.

- [ ] 2. Update
      `platform-gitops/argo-workflows/service-templates/openclaw/values.yaml.tpl`
      so `env.OPENCLAW_VERSION` reads `"__IMAGE_TAG__"` instead of the
      hardcoded `"2026.3.25-beta.26"` literal.
      DoD: the template's `env:` block sets
      `OPENCLAW_VERSION: "__IMAGE_TAG__"`; a manual
      `sed -e "s|__IMAGE_TAG__|2026.7.11-beta.2|g" values.yaml.tpl` (the
      same `-e ... /g` substitution `tpl-git-commit.yaml` lines 368-375 use
      for real onboarding) produces a file where both `image.tag` and
      `env.OPENCLAW_VERSION` read `2026.7.11-beta.2`; no other
      `__PLACEHOLDER__` token in the file is touched.

- [ ] 3. Add `scripts/validate-openclaw-version-pin.py` (depends on 1, so
      the new check is added against an already-consistent repository
      state and never opens the PR on a red check) that:
      - Globs `platform-gitops/services/*/openclaw/values.yaml`.
      - Parses each file's top-level `image.tag` and `env.OPENCLAW_VERSION`.
      - Prints `::error::<path>: image.tag=<X> OPENCLAW_VERSION=<Y>` and
        exits non-zero if both keys are present and their values differ,
        for every offending file (not just the first).
      - Exits 0 if every file's two values match (or a file has at most
        one of the two keys, which is out of scope for this check).
      - Supports `--selftest`: builds two temp fixtures (one matching, one
        mismatched) and asserts the detector stays quiet on the first and
        fires on the second, following the shape of
        `scripts/validate-shell-param-interpolation.py`'s `--selftest`.
      DoD: `python3 scripts/validate-openclaw-version-pin.py --selftest`
      exits 0 and prints a self-test-ok line; `python3
      scripts/validate-openclaw-version-pin.py` exits 0 against the
      repository state left by task 1.

- [ ] 4. Wire the new script into `.github/workflows/validate-manifests.yml`
      (depends on 3): add a step alongside the existing
      `scripts/validate-*.py` steps (e.g. after "Check every changed
      ExecutionProfile bumped its version") that runs
      `scripts/validate-openclaw-version-pin.py --selftest` then
      `scripts/validate-openclaw-version-pin.py`, matching the existing
      two-line selftest-then-real-run pattern used by the neighboring
      steps.
      DoD: the new step appears in `validate-manifests.yml` in the same
      style (comment explaining why, `--selftest` before the real
      invocation) as `validate-shell-param-interpolation.py` /
      `validate-yq-interpolation.py`; a local dry run of the same two
      commands from task 3's DoD succeeds.

- [ ] 5. Confirm, by reading `mctl-openclaw`'s handling of
      `OPENCLAW_VERSION` (or asking whoever owns that repo, per the
      issue's own note that this "needs someone who knows what
      `OPENCLAW_VERSION` gates"), whether correcting the value on
      `admins`/`labs` triggers any one-time behavior (a migration, a
      first-run-at-version check). Not a blocking dependency for tasks 1-4,
      but should happen before or during rollout so an unexpected one-time
      effect is not mistaken for a regression.
      DoD: a note (PR description or a follow-up comment on issue #1037)
      records what was found — either "no gated behavior between these two
      versions" or a description of what does trigger and how it was
      verified safe.

## Tests

- [ ] T1. `helm lint platform-gitops/helm-charts/base-service` passes
      (per `CLAUDE.md`'s documented lint command) — proves the edited
      values.yaml files still produce a valid chart render.
- [ ] T2. For each of `admins/openclaw/values.yaml` and
      `labs/openclaw/values.yaml`: `helm template test
      platform-gitops/helm-charts/base-service -f <file> | grep -A1
      'name: OPENCLAW_VERSION'` shows `value: "2026.7.11-beta.2"` in the
      rendered manifest, matching the rendered image reference.
- [ ] T3. `python3 scripts/validate-openclaw-version-pin.py --selftest`
      exits 0 and demonstrably fails on the mismatched fixture before the
      real script logic is applied to it (proves the detector is not
      vacuously passing).
- [ ] T4. `python3 scripts/validate-openclaw-version-pin.py` exits 0
      against the full repository after task 1's edits land.
- [ ] T5. Manually revert task 1's edit to `admins/openclaw/values.yaml`
      in a scratch copy and re-run
      `python3 scripts/validate-openclaw-version-pin.py` against it to
      confirm it now exits non-zero and names that file — proves the CI
      guard actually catches the exact drift this issue reports, not just
      a synthetic fixture.
- [ ] T6. After merge, watch `mctl_get_service_logs` (or
      `kubectl -n admins logs deploy/admins-openclaw-base-service -c
      base-service`, per `k8s.md`'s "Inspect a tenant pod end-to-end")
      for `admins` and `labs` for 15-30 minutes post-rollout for any
      version-banner or startup error referencing `OPENCLAW_VERSION`,
      confirming task 5's "no gated behavior" expectation.

## Rollback

All changes are plain gitops edits with no data migration:

- Tasks 1-2 (values.yaml and template edits): revert with a follow-up
  commit restoring the prior literal values (`"2026.5.14-beta.1"` for
  `admins`/`labs`, `"2026.3.25-beta.26"` for the scaffolder template).
  ArgoCD reconciles the revert the same way it reconciled the forward
  change — no manual cluster surgery, no state loss, since
  `OPENCLAW_VERSION` is a plain env var and the S3-backed `state-data`
  emptyDir (per `k8s.md`) is untouched by this class of change.
- If a rolled-forward `admins` or `labs` pod shows unexpected behavior
  tied to the corrected `OPENCLAW_VERSION` (per task 5), the fastest
  mitigation is reverting just that tenant's values.yaml line via a new PR
  and letting ArgoCD sync (or a hard refresh per `k8s.md`'s "Trigger ArgoCD
  sync without waiting for the 3-minute poll") — no image rollback is
  needed since `image.tag` never changes in this proposal.
- Task 4 (CI step): revert the added step from
  `validate-manifests.yml` in a follow-up commit if it produces false
  positives; this does not affect any deployed service, only PR checks.
