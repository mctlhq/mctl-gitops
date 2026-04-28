# Allowlist policy for external ClawHub skills

## Context
The active ClawHavoc campaign placed 341+ malicious skills in the official ClawHub marketplace (recorded in inbox/2026-04-27.md, source: armosec.io). No CVE has been assigned yet, the campaign is ongoing. The mctl-openclaw platform uses a 3-layer skills architecture, where Layer 3 (remote/HTTP-delegated skills) is registered via REST API without any restriction on source. If even one tenant (ovk, labs, admins) installed skills from ClawHub without source verification, the attack vector is already open.

At present, there is no mechanism in the gitops config that fixes the list of permitted skill sources. There is also no CI check that would detect new unapproved skill sources appearing in manifest changes. This is a low-effort configuration change: no RAM impact, no upstream patch needed, implemented via Helm values + a CI step.

## User stories
- AS a platform operator I WANT a fixed allowlist of permitted Layer 3 skill sources in each tenant's gitops config SO THAT malicious skills from ClawHub cannot be registered without explicit approval
- AS a security engineer I WANT a CI check that blocks PRs introducing new unapproved skill sources SO THAT accidental or unauthorised registration of malicious skills is caught before deploy
- AS a tenant operator I WANT a clear approval process for new skill sources (allowlist update) SO THAT legitimate skills can be added without bypassing protection

## Acceptance criteria (EARS)
- WHEN a Layer 3 skill is registered via REST API with a source (URL/origin) not in the tenant's allowlist THEN THE SYSTEM SHALL reject registration with a 403 status and a policy-restriction message
- WHILE an allowlist is set in a tenant's Helm values THE SYSTEM SHALL apply it to every incoming remote skill registration request, including pod restart and hot-reload
- IF the CI pipeline detects a PR change adding a new skill source to a manifest without a corresponding allowlist update THEN THE SYSTEM SHALL fail the CI step with an explicit message requesting review
- WHEN the allowlist is set as an empty list THEN THE SYSTEM SHALL block registration of all Layer 3 skills (fail-closed semantics)
- IF a tenant has no explicitly set allowlist in Helm values THEN THE SYSTEM SHALL apply a default deny-all policy for Layer 3 skills
- WHEN the allowlist is updated through a gitops manifest THEN THE SYSTEM SHALL apply the new policy without a pod restart (hot-reload via the YAML skill config)

## Out of scope
- Audit of already installed Layer 3 skills (separate inventory task)
- Changes in Layer 1 (built-in) and Layer 2 (YAML hot-reload) skills — they are not registered via REST API from external sources
- Blocking ClawHub at the network layer (NetworkPolicy) — a broader measure, separate proposal
- Scanning skill content for malicious code — out of scope for allowlist control
- Changes in the upstream openclaw API
