# Tasks: terraform-v1-15-1-patch

- [ ] 1. Identify all version pin locations for Terraform in this repository
  Check `infrastructure/` for `.terraform-version`, `versions.tf`, `terraform.tf`, or any
  equivalent root module file that declares the required Terraform version. Also check Argo
  Workflows pipeline step definitions in `platform-gitops/argo-workflows/` for container image
  tags referencing the Terraform binary.
  **DoD:** A list of all files that declare the Terraform version is attached to the PR
  description. No location is missed.

- [ ] 2. Update the version pin to v1.15.1 in all identified locations (depends on 1)
  Change every occurrence of `1.15.0` (or the previous pin) to `1.15.1`. This includes:
  - `.terraform-version` (if present)
  - `required_version` constraint in the root module (if present)
  - Container image tags in Argo Workflows pipeline definitions (if present)
  Make all changes in a single commit for atomicity.
  **DoD:** The PR diff shows only version string changes; no logic, configuration, or provider
  files are modified. All changed files reference `1.15.1` consistently.

- [ ] 3. Run CI plan against the existing infrastructure configuration (depends on 2)
  Trigger a `terraform plan` run (via the CI pipeline or locally with credentials) against the
  `infrastructure/` root module using the new v1.15.1 binary.
  **DoD:** The plan exits with code 0, produces no unexpected resource diffs, and the plan output
  header confirms `Terraform v1.15.1`.

- [ ] 4. Merge and confirm pipeline health (depends on 3)
  Merge the PR. Confirm that the next scheduled or on-demand Argo Workflows Terraform pipeline
  run completes successfully using v1.15.1.
  **DoD:** At least one post-merge Argo Workflow terraform run shows `Succeeded` status and the
  log confirms `Terraform v1.15.1`.

## Tests

- [ ] T1. Version confirmation — After the version pin update, run `terraform version` inside the
  pipeline container (or via a one-off workflow step) and confirm the output is
  `Terraform v1.15.1`.

- [ ] T2. Plan no-diff — Run `terraform plan` against the current `infrastructure/` state and
  confirm the output is `No changes. Your infrastructure matches the configuration.` (or shows
  only expected pending changes, none of which are caused by the version bump itself).

- [ ] T3. Panic regression — If the `infrastructure/` modules contain or can be temporarily
  amended to include a typed module with zero expanded instances, verify that v1.15.1 handles it
  without a panic. If no such module exists, document that the fix is verified via the upstream
  release notes and the passing CI plan is the acceptance gate.

## Rollback

If v1.15.1 causes unexpected plan diffs, errors, or a regression:

1. Revert the version pin commit (git revert or a new commit restoring `1.15.0` in all files
   updated in task 2).
2. Merge the revert PR immediately; the next pipeline run will use v1.15.0 again.
3. Open a follow-up issue referencing the specific error observed in v1.15.1 and track it against
   the Terraform upstream release tracker.

No state rollback is required: v1.15.1 introduces no state format changes, so reverting to
v1.15.0 will read the existing state without modification.
