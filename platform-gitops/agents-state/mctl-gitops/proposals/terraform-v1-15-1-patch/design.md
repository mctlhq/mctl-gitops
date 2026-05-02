# Design: terraform-v1-15-1-patch

## Current state

As documented in `context/architecture.md`, Terraform lives under `infrastructure/` in this
repository and manages cluster-level infrastructure. The Terraform binary version is pinned
either via a `.terraform-version` file (tfenv convention) or via the `required_version` constraint
in `infrastructure/versions.tf` (or equivalent root module file). The platform is currently on
Terraform v1.15.0.

Terraform apply runs are invoked through Argo Workflows pipelines defined in
`platform-gitops/argo-workflows/`. The pipeline steps pull the Terraform binary at the pinned
version before running plan/apply. Provider versions are pinned separately in
`infrastructure/.terraform.lock.hcl` and are not affected by this change.

v1.15.0 contains two known crash/panic defects:
- Panic on typed modules with zero expanded instances (upstream bug fixed in v1.15.1).
- Crash on invalid `action_trigger` blocks (upstream bug fixed in v1.15.1).

Both can cause silent mid-run aborts, which on a GitOps platform produce configuration drift
without a clear failure signal.

## Proposed solution

Bump the Terraform version pin from `v1.15.0` to `v1.15.1` in `infrastructure/`. The exact
file(s) to update depend on how the version is currently pinned:

- If tfenv is used: update `.terraform-version` in `infrastructure/` to `1.15.1`.
- If `required_version` is used: update the constraint in `infrastructure/versions.tf` (or
  the root `terraform.tf`) to `>= 1.15.1, < 1.16.0` (or `= 1.15.1` if strict pinning is
  preferred).
- If the Argo Workflows pipeline step references a Terraform container image by tag, update
  the image tag to the `1.15.1` variant (e.g., `hashicorp/terraform:1.15.1`).

No Terraform state changes, no provider upgrades, and no configuration changes are required.
The upgrade is a drop-in replacement per the upstream release notes at
`https://github.com/hashicorp/terraform/releases/tag/v1.15.1`.

After the version pin is updated, the CI pipeline's `terraform plan` step is the primary
validation gate.

## Alternatives

### Option 1: Stay on v1.15.0

Accept the risk of silent panics and crashes on typed modules with no expanded instances or
invalid `action_trigger` blocks. The probability of hitting these bugs depends on the specific
module patterns in `infrastructure/`; if no such patterns exist today, the risk is low until new
modules are added. Dropped: the upgrade is trivially low-effort (effort score 1) and there is no
benefit to leaving known crash bugs unpatched on a production infrastructure path.

### Option 2: Upgrade to Terraform v1.16.x (next minor)

v1.16.x introduces new features but may also include minor API or provider interface changes
that require testing. A minor version bump carries higher risk than a patch bump for no
additional gain specific to the two defects being fixed. Dropped: v1.15.1 is the minimum
sufficient fix; a minor upgrade should be a separate, explicitly scoped proposal.

### Option 3: Pin per-module terraform versions using tfenv `.terraform-version` files

Rather than a single root-level pin, maintain per-directory version files. This adds flexibility
but also adds maintenance overhead and the risk of inconsistency between directories. Dropped:
the current single-pin approach is consistent and appropriate for this codebase; this proposal
is a patch bump, not an architecture change.

## Platform impact

### Migrations

No Terraform state migrations are required. v1.15.1 is a patch release with no state format
changes.

### Backward compatibility

v1.15.1 is fully backward compatible with v1.15.0. All existing Terraform configurations,
provider lock files, and module structures continue to work without modification.

### Resource impact

Terraform runs as a transient workflow step in Argo Workflows, not as a persistent service. There
is no persistent pod, no memory allocation to a tenant namespace, and no impact on the `labs`
memory budget. This change carries no memory risk for either tenant.

### CI pipeline note

If the Argo Workflows step uses a container image tag to specify the Terraform version
(e.g., `hashicorp/terraform:1.15.0`), that tag must be updated alongside the version file.
If tfenv is used inside the container, updating `.terraform-version` is sufficient provided the
pipeline step pulls the tfenv-managed binary at run time. Verify the mechanism in the pipeline
definition before committing.

### Risks and mitigations

- **Risk:** The version bump file and the container image tag get out of sync, causing the
  pipeline to run a different version than declared.
  **Mitigation:** Task 1 audits all locations where the version is declared and updates them
  atomically in a single commit.
- **Risk:** v1.15.1 introduces a regression not present in v1.15.0 (unlikely for a patch
  release, but possible).
  **Mitigation:** The CI plan run (task 3) against the existing `infrastructure/` configuration
  is the validation gate. If the plan produces unexpected diffs or errors, the version pin is
  reverted immediately.
