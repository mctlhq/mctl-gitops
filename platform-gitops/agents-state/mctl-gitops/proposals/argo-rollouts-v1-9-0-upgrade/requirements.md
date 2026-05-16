# Argo Rollouts v1.9.0 BlueGreen Analysis Premature-Success Fix

## Context
Argo Rollouts is deployed cluster-wide and drives BlueGreen and Canary progressive delivery for all tenants on the platform. A bug present in versions prior to v1.9.0 causes a BlueGreen analysis step to be marked as successful whenever the incoming ReplicaSet becomes unsaturated mid-rollout (for example, due to a node eviction or resource pressure). The result is that the degraded revision is silently promoted to stable without any human or automated gate catching the regression. This is a silent data-plane correctness risk: a bad deployment can reach 100 % of production traffic with no alert.

Argo Rollouts v1.9.0 ships a targeted fix for this premature-success condition. There are no CRD schema changes in this release, making it a patch-compatible version pin bump. Upgrading eliminates the silent promotion risk and restores the integrity of BlueGreen analysis gates across both the `admins` and `labs` tenants.

## User stories
- AS a platform engineer I WANT BlueGreen analysis steps to reflect the true health of the incoming ReplicaSet SO THAT a degraded revision is never silently promoted to stable.
- AS a tenant developer I WANT my rollout analysis gates to be reliable SO THAT I can trust that a successful promotion means my new version is actually healthy.
- AS an SRE I WANT the Argo Rollouts controller to be on a release that contains the premature-success fix SO THAT I do not have to manually audit every BlueGreen promotion for silent failures.

## Acceptance criteria (EARS)
- WHEN a BlueGreen rollout analysis step is running AND the incoming ReplicaSet becomes unsaturated THE SYSTEM SHALL NOT mark the analysis step as successful.
- WHEN the Argo Rollouts controller is deployed at v1.9.0 or later THE SYSTEM SHALL gate BlueGreen promotion on all analysis steps completing with a genuinely successful result.
- WHILE a BlueGreen rollout is in progress THE SYSTEM SHALL continue to evaluate analysis steps until the incoming ReplicaSet is fully saturated and all metrics pass.
- IF the incoming ReplicaSet becomes unsaturated during an active analysis run THEN THE SYSTEM SHALL pause or fail the analysis step rather than promote the revision.
- WHEN the version pin in the Argo Rollouts ArgoCD Application manifest is updated to v1.9.0 THE SYSTEM SHALL reconcile and deploy the new controller version without requiring CRD migrations.
- WHEN the upgraded controller is running THE SYSTEM SHALL preserve all existing Rollout, AnalysisTemplate, and AnalysisRun custom resources without modification.

## Out of scope
- Upgrading Argo Rollouts beyond v1.9.0 as part of this proposal.
- Changes to any CRD schemas (none are required).
- Changes to individual tenant Rollout or AnalysisTemplate manifests.
- Migrating tenants from BlueGreen to Canary or any other delivery strategy.
- Adding new analysis metric providers or modifying existing AnalysisTemplates.
- Resource tuning of the Argo Rollouts controller beyond what ships in the v1.9.0 default manifests.
