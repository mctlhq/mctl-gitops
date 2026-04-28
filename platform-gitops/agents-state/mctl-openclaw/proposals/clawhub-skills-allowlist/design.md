# Design: clawhub-skills-allowlist

## Current state
According to `context/architecture.md`, the platform uses a 3-layer skills architecture:
- Layer 1: Built-in skills (compiled into the core)
- Layer 2: YAML skills (hot-reload from `skills/custom/`)
- Layer 3: Remote skills (HTTP-delegated, registered via REST API)

Layer 3 skills are registered via the openclaw REST API — any client with API access can register a skill against an arbitrary remote endpoint. The current GitOps manifests have no field constraining the list of permitted sources. The CI pipeline does not check for new skill sources appearing. Deploy: Docker → mctl-gitops → ArgoCD, tenant configuration in Helm values.

## Proposed solution

**Part 1: allowlist in Helm values (gitops)**

Add a field `skills.remoteAllowlist` to each tenant's Helm values — a list of permitted URL prefixes (or origins) for Layer 3 skills:

```yaml
# mctl-gitops/tenants/<tenant>/values.yaml
skills:
  remoteAllowlist:
    - "https://skills.mctlhq.internal/"
    # empty list = deny-all (fail-closed)
```

If the field is missing or empty — deny-all applies by default. Fail-closed semantics: no explicit grant → no access.

**Part 2: enforcement in openclaw config**

openclaw supports configuration via a YAML config file (the Layer 2 hot-reload mechanism). Add a configuration skill in `skills/custom/` (a tenant-specific overlay through gitops) or use the existing openclaw config mechanism to set `allowRemoteSkillSources`. When a Layer 3 skill is registered via REST API, openclaw checks the origin against the allowlist and returns 403 on mismatch.

If openclaw does not support a native allowlist — implement it via nginx/ingress middleware (an admission webhook or Lua script) in front of the API endpoint, filtering registration requests by Origin header. This is a more invasive approach but does not require an upstream patch.

**Part 3: CI check**

Add a step to the mctl-gitops CI pipeline:
- A script scans the PR diff for changes in `skills/` directories and manifests related to Layer 3 skills.
- If a new URL/origin not in the current tenant's allowlist is detected — CI fails with: "New remote skill source detected: <url>. Update allowlist in values.yaml and get security review."
- The step is a simple bash/Python script with no extra dependencies.

**Why this approach:**
A configuration-based approach (Helm values + CI) — minimal effort, zero RAM impact, no upstream changes required. Fail-closed semantics by default protect tenants who forget to set an allowlist explicitly. The CI check prevents accidental addition of unapproved sources via gitops.

## Alternatives

**Alternative 1: NetworkPolicy — block ClawHub at the network layer**
Kubernetes NetworkPolicy can be configured so openclaw pods cannot reach ClawHub IP ranges. Dropped: requires keeping a current ClawHub IP list (changes), does not protect against skills hosted on other domains, and does not address skills already registered. A broader measure that does not replace the allowlist.

**Alternative 2: Upstream feature request — allowlist in openclaw core**
Request that upstream openclaw add a native allowlist for remote skills. Dropped: too slow (campaign is active now); no guarantee of inclusion in the next release; the solution is needed immediately. Can be done in parallel as a long-term measure.

**Alternative 3: Disable Layer 3 skills entirely on all tenants**
The fastest way to close the vector is to turn off remote skill registration. Dropped: legitimate Layer 3 skills may already be in use in ovk or admins; turning them off without inventory may break production functionality. An allowlist with explicitly approved sources is a more precise and controllable approach.

## Platform impact

**Migration**
Before enabling the deny-all policy, take inventory of currently registered Layer 3 skills on each tenant and add their sources to the allowlist. Otherwise legitimate skills will stop working.

**Backward compatibility**
The change affects the openclaw REST API behaviour for Layer 3 skills. Existing skills registered before the allowlist was introduced are unaffected (they are already in the system), but re-registration or update attempts will be checked against the allowlist. Document the allowlist update process for operators.

**Resource impact**
- labs: NO IMPACT. Configuration-only change (Helm values + CI), no RAM increase.
- admins: NO IMPACT.
- ovk: NO IMPACT.

**Risks and mitigations**
- Legitimate Layer 3 skills are blocked by an incomplete allowlist → take inventory of skills before enabling the policy; start with admins (minimum blast radius), then labs, then ovk.
- An operator bypasses the CI check via a direct commit to main → protect main with a branch protection rule requiring CI.
- The allowlist is set too broadly (e.g. `https://clawhub.io/`) → document the policy: only explicit verified origins, no wildcard ClawHub domains.
- Hot-reload of the config does not apply without a restart → verify openclaw behaviour when config changes via YAML; if needed, plan a graceful reload or rolling restart.
