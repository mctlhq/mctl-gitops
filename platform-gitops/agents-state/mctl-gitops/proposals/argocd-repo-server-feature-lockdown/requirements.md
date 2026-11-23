# Disable unused repo-server features (Jsonnet, kustomize-Helm, SSH proxy)

## Context
The recent Argo CD repo-server CVEs (CVE-2026-113672 Jsonnet file read, -113708 Kustomize arg injection, -113709 Helm configHome with `--enable-helm`, -55797 SSH proxy injection) all depend on optional features. Disabling unused ones reduces exposure before and after patching. IDs are unverified.

## User stories
- AS a platform operator I WANT unused repo-server features off SO THAT fewer exploit paths exist.

## Acceptance criteria (EARS)
- WHEN no Application uses kustomize with Helm THE SYSTEM SHALL disable `--enable-helm` for kustomize builds.
- WHEN no Application uses Jsonnet THE SYSTEM SHALL restrict or disable Jsonnet evaluation.
- IF a feature is in use THEN THE SYSTEM SHALL keep it and record the owner and reason.
- WHEN repositories are configured THE SYSTEM SHALL contain no SSH proxy settings unless justified.
- WHEN the change is applied THE SYSTEM SHALL keep all Applications Synced/Healthy.

## Out of scope
- Version upgrades; credential rotation.
