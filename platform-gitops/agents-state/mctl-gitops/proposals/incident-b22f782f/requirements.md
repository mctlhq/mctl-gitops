# Requirements: incident-b22f782f

## Incident
- ID: a0951729-336b-4f34-b333-7784b22f782f
- Tenant: labs
- Service: pelican-proxy-staging
- Alert: argocd_app_degraded
- Created: 2026-09-24T23:33:32.596458Z

### Summary
```
ArgoCD app labs-pelican-proxy-staging health: Degraded
```

## Evidence
### Labels
```
tenant: labs
service: pelican-proxy-staging
type: argocd_app_degraded
source: polling
severity: warning
confidence: LOW
occurrence_count: 1
```

### Log Snippet
Pod name changed four times in the 26 minutes surrounding the incident
(697c5bdc86-5wqn8, 599b7c9db-gm9jg, 74bd965f6f-z4x6j, 8699bf765d-lhr77),
indicating repeated rollouts/restarts of the deployment rather than one
long-lived pod. Each restart performs a fresh login before serving traffic:

```
2026-09-24T23:33:46.616Z pod=697c5bdc86-5wqn8 [refresher] performing full login
2026-09-24T23:33:49.417Z pod=697c5bdc86-5wqn8 [refresher] token saved, 3600s left, refresh_token=yes
2026-09-24T23:33:49.812Z pod=697c5bdc86-5wqn8 [r2] seeded 3123 items from R2 (age 3.0h)
2026-09-24T23:33:46.280Z pod=697c5bdc86-5wqn8 rate limit: 120/min/IP, allowed paths: 9
2026-09-24T23:33:46.278Z pod=697c5bdc86-5wqn8 pelican proxy: http://localhost:8787

2026-09-24T23:42:31.964Z pod=599b7c9db-gm9jg [refresher] performing full login
2026-09-24T23:42:34.662Z pod=599b7c9db-gm9jg [refresher] token saved, 3600s left, refresh_token=yes
2026-09-24T23:42:35.181Z pod=599b7c9db-gm9jg [r2] seeded 3123 items from R2 (age 3.2h)
2026-09-24T23:42:35.181Z pod=599b7c9db-gm9jg token loaded (3599s left)

2026-09-24T23:47:25.456Z pod=74bd965f6f-z4x6j [refresher] performing full login
2026-09-24T23:47:27.863Z pod=74bd965f6f-z4x6j [refresher] token saved, 3600s left, refresh_token=yes
2026-09-24T23:47:29.543Z pod=74bd965f6f-z4x6j [r2] seeded 3123 items from R2 (age 3.2h)
2026-09-24T23:47:29.555Z pod=74bd965f6f-z4x6j token loaded (3598s left)

2026-09-24T23:59:28.485Z pod=8699bf765d-lhr77 [startup] no token yet -- will retry initial build once refresher saves one
2026-09-24T23:59:25.586Z pod=8699bf765d-lhr77 [refresher] performing full login
2026-09-24T23:59:28.471Z pod=8699bf765d-lhr77 [r2] seeded 3123 items from R2 (age 3.4h)
2026-09-24T23:59:29.073Z pod=8699bf765d-lhr77 [refresher] token saved, 3600s left, refresh_token=yes
2026-09-24T23:59:38.489Z pod=8699bf765d-lhr77 [startup] token available -- catalog already seeded from R2, skipping rebuild
```

No error, panic, or OOM lines appear in the fetched window. By the time this
proposal was written, `mctl_get_service_status` reported the ArgoCD app as
`Healthy`/`Synced` again (self-recovered).

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
