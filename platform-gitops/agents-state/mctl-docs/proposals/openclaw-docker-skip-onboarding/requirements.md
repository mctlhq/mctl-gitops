# OpenClaw Docker Automated Deployment: OPENCLAW_SKIP_ONBOARDING

## Context

Commit `490e6d6` (mctl-openclaw, 2026-04-28) added the `OPENCLAW_SKIP_ONBOARDING`
environment variable to the OpenClaw Docker setup script. When set to a truthy value
(`1`, `true`, `yes`, or `on`), the interactive onboarding step is bypassed while gateway
defaults are still applied. The variable is documented in OpenClaw's own Docker install
guide (`docs/install/docker.md`), but not in the mctl platform's `docs/platform/openclaw.md`.

The mctl platform deploys OpenClaw for each tenant via ArgoCD / GitOps (non-interactive).
Any operator provisioning a new tenant or re-deploying an existing one needs to know about
this flag. Without it, they might encounter an unexpected interactive prompt or need to
hunt through OpenClaw's upstream Docker documentation.

## User stories

- AS a **platform admin** provisioning a new mctl tenant I WANT to know that I can set
  `OPENCLAW_SKIP_ONBOARDING=1` in the ArgoCD deployment manifest SO THAT the OpenClaw
  container starts non-interactively and the gateway defaults are applied automatically.
- AS a **developer** building a CI/CD pipeline that stands up a test environment with
  OpenClaw I WANT the setup env var documented in one place SO THAT I do not need to
  read the full openclaw Docker guide.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL show a table or list
  of supported setup environment variables that includes `OPENCLAW_SKIP_ONBOARDING` with
  a description and accepted values.
- IF a reader wants to automate OpenClaw deployment in the mctl GitOps workflow THEN THE
  SYSTEM SHALL provide enough context to set the env var correctly (accepted truthy values,
  effect on gateway defaults).
- WHEN the accepted values for `OPENCLAW_SKIP_ONBOARDING` are listed THE SYSTEM SHALL
  enumerate `1`, `true`, `yes`, `on` as truthy values (matching the upstream implementation).
- WHILE version-status is unverified THE SYSTEM SHALL note the commit SHA.

## Out of scope

- A full Docker setup tutorial (that is OpenClaw's own documentation).
- Podman-specific build args (`OPENCLAW_INSTALL_BROWSER`) — no evidence mctl uses Podman.
- Helm chart templating for the env var (mctl-gitops is private; no commit signal available).
