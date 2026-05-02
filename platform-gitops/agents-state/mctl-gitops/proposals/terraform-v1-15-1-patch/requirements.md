# Upgrade Terraform to v1.15.1 (crash and panic fixes)

## Context

Terraform v1.15.1 is a patch release that resolves two stability defects present in v1.15.0:

1. A panic in typed modules that have no expanded instances — triggered at plan/apply time when
   a module is declared but evaluates to zero instances. The process exits with an unhandled
   panic, silently aborting the infrastructure apply run with no actionable error message.
2. A crash on invalid `action_trigger` blocks — malformed trigger configuration causes Terraform
   to crash rather than return a validation error, again silently terminating the run.

Both defects can cause `terraform apply` to abort mid-run without completing the intended
infrastructure changes. On this platform Terraform manages cluster infrastructure under
`infrastructure/` and is invoked through Argo Workflows pipelines. A silent abort can leave
infrastructure in a partially-applied state without surfacing a clear failure signal to operators,
increasing the risk of configuration drift and undetected breakage.

The upgrade is drop-in: v1.15.1 introduces no API changes, no provider interface changes, and
no configuration format changes. Effort is minimal (version pin update only).

## User stories

- AS a platform engineer I WANT Terraform upgraded to v1.15.1 SO THAT infrastructure apply runs
  complete reliably without silent panics or crashes that leave the cluster in a partially-applied
  state.
- AS a platform engineer I WANT the version bump to be applied with minimal disruption SO THAT
  CI/CD pipelines continue to run without reconfiguration.

## Acceptance criteria (EARS)

- WHEN a Terraform apply run targets a typed module with no expanded instances THE SYSTEM SHALL
  complete the run without a panic exit and SHALL surface any relevant plan output or a clean
  no-op result.
- WHEN a Terraform configuration contains an invalid `action_trigger` block THE SYSTEM SHALL
  return a structured validation error and SHALL NOT crash the Terraform process.
- WHEN the version pin is updated to v1.15.1 THE SYSTEM SHALL produce a passing CI plan run
  against the existing `infrastructure/` configuration with no unexpected diffs.
- WHILE a Terraform apply run is in progress THE SYSTEM SHALL not abort silently; any failure
  SHALL produce a non-zero exit code and a human-readable error message.
- IF the CI pipeline invokes `terraform plan` or `terraform apply` after the version bump THEN
  THE SYSTEM SHALL execute using v1.15.1 and the output SHALL include the version string
  confirming the correct binary is in use.

## Out of scope

- Upgrading Terraform providers (AWS, GCP, Kubernetes, Vault, etc.) — provider versions are
  tracked separately in `infrastructure/` and are not part of this patch bump.
- Upgrading to Terraform v1.16.x or any future minor/major release.
- Changes to Argo Workflows pipeline definitions beyond updating the Terraform version reference.
- Changes to platform-gitops or ArgoCD Application manifests.
- Any Terraform state migrations.
