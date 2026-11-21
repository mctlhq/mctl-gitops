# Design: preview-promote-and-onboard

version-status: unverified, see commit SHA

## Source commits
- mctl-api:db4dda2 — feat(deploy): promote a verified preview to production behind an owner grant
- mctl-api:a3cc4b3 — fix(deploy): refuse a promotion whose production base has moved
- mctl-api:5067b9d — feat(deploy): compare a promoted digest with the preview's
- mctl-api:d45bcc4 — feat(deploy): plan and apply a preview onboard from a DeployIntent
- mctl-api:5786817 — fix(deploy): onboard plan checked at plan and decide time, audit keeps values out

## Current state of documentation
- `docs/guides/previews.md` ("Preview Environments") exists; body not read; likely no promote or onboard-from-intent coverage.
- Related existing proposal: `deploy-analyze-and-plan` (plan flow); check overlap and reuse its terminology (DeployIntent, plan digest).

## Proposed solution
UPDATE `docs/guides/previews.md` with two sections, "Promote a verified preview to production" and "Onboard a preview from a DeployIntent". Mark unknown request/response shapes TODO.

## Alternatives
- New page `docs/guides/promotion.md`: dropped, promotion is the end of the preview lifecycle.
- Split onboarding into `docs/guides/services.md`: dropped for now; add a cross-link.

## Impact
- No sidebar change. Mermaid flowchart included.
- Applies to main; no versioning.
