# Design: argo-workflows-4-1-7-bump-check

## Current state
Argo Workflows runs all cron/on-demand pipelines including image builds (context/architecture.md). Known issue: v3.7.10 archive INSERT NULL bug.

## Proposed solution
1. Read deployed controller/server image tags from the manifests in this repo (and via mctl MCP when available).
2. Read CHANGELOG for 4.1.6 to 4.1.7 and verify CVE fixes (CVE IDs unverified; check GHSA).
3. If on the 4.1 line below 4.1.7, bump the tag in a single commit; otherwise record the result and stop.
Executor image and CRDs are bumped together.

## Alternatives
- Stay on 4.1.6: misses the newest patch; low cost to move. 
- Upgrade across major lines: violates the patch-day rule.

## Platform impact
- Migrations: CRDs apply via ArgoCD; check for CRD changes in the changelog.
- Backward compatibility: patch-level.
- Resource impact: none expected; labs unaffected (platform namespaces).
- Risks: in-flight workflows disrupted; schedule outside the build window; archive regression checked by T1.
