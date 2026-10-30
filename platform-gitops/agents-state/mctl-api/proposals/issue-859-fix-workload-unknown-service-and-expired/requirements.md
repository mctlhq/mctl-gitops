# Workload reads: tell an unknown service and an expired event window apart from observed absence

## Context
Two read endpoints feed the tenant support agent, and both can return a result that looks like "observed absent" when the server did not actually observe anything. `GET /api/v1/pods/{team}/{app}` (MCP `mctl_get_service_pods`) checks that the tenant exists but not the service. For a misspelled or never-deployed service it returns `200 {"count":0,"items":[]}`, the same body as a real service with zero pods. `GET /api/v1/events/{team}` (MCP `mctl_list_namespace_events`) accepts `since` up to 24h and echoes it back. The apiserver only keeps events for its event TTL (default `--event-ttl=1h`), so an empty result for `since=24h` only covers roughly the last hour.

The workspace rule is "could not observe is never observed absent". This proposal makes the pod read resolve the service before listing pods, using 404 for a documented absence and 503 when the lookup fails. It applies the same check to the events `app` filter. The events response will also state the window it actually covers, so a caller cannot read "nothing in the retained hour" as "nothing in 24 hours".

## User stories
- AS the tenant support agent I WANT a pod read for an unknown service to fail with "service not found" SO THAT I never tell a user "your service has no running pods" about a name that was never deployed.
- AS a tenant user I WANT a typo in a service name to be reported as a typo SO THAT I do not go looking for a scaling problem that does not exist.
- AS the tenant support agent I WANT the events response to say which part of the requested window the server can still see SO THAT I report "no warnings in the retained window (about 1h)" and not "no warnings in the last 24h".
- AS a platform operator I WANT the event retention the API assumes to be configurable SO THAT it can match the cluster's real `--event-ttl`.

## Acceptance criteria (EARS)
- WHEN `GET /api/v1/pods/{team}/{app}` is called for a registered tenant AND `services/{team}/{app}` exists in the gitops checkout THE SYSTEM SHALL list the pods as today and answer 200, including `count: 0, items: []` when there are no pods.
- WHEN the gitops checkout says `services/{team}/{app}` does not exist AND ArgoCD lists an application named `{team}-{app}` whose destination namespace is `{team}` THE SYSTEM SHALL treat the service as known and answer 200 with the pod list.
- IF the gitops checkout says the service does not exist AND the ArgoCD workload list was read successfully AND it contains no matching application THEN THE SYSTEM SHALL answer `404` with an error message starting `service not found: {app}`, and SHALL NOT call the Kubernetes pod list.
- IF the gitops service lookup returns an error, or the gitops reader is not configured, THEN THE SYSTEM SHALL answer 503 and SHALL NOT answer 404 or 200.
- IF the gitops checkout says the service does not exist AND the ArgoCD client is not configured or its workload list fails THEN THE SYSTEM SHALL answer 503 ("cannot confirm whether service {app} exists"), never 404 and never 200 with an empty list.
- WHEN `GET /api/v1/events/{team}?app={app}` is called THE SYSTEM SHALL resolve `{app}` the same way as the pod read and SHALL answer 404 or 503 under the same conditions, before it lists any events.
- WHEN `GET /api/v1/events/{team}` answers 200 THE SYSTEM SHALL include `observed_since` (RFC 3339). This is the later of `now - since` and `now - event_retention`: the oldest instant for which the absence of an event is meaningful.
- WHEN the requested `since` is longer than the configured event retention THE SYSTEM SHALL set `coverage_complete: false` and SHALL include a `coverage_note` saying events older than the retention are no longer held by the cluster and their absence is unknown.
- WHEN the requested `since` is at most the configured event retention THE SYSTEM SHALL set `coverage_complete: true` and omit `coverage_note`.
- WHILE the event retention is not configured THE SYSTEM SHALL assume 1h, the Kubernetes default `--event-ttl`.
- THE SYSTEM SHALL keep accepting `since` from 1m to 24h, and SHALL keep the `since` field as the requested window, so existing callers keep working.
- THE SYSTEM SHALL update the MCP descriptions of `mctl_get_service_pods` and `mctl_list_namespace_events` to describe the 404/503 behaviour and the `observed_since` / `coverage_complete` fields.

## Out of scope
- A `replicas_desired` field on the pod response. The issue marks it optional, and it needs a new Kubernetes read (Deployment/StatefulSet `spec.replicas`) and possibly new RBAC. It is recorded as a follow-up.
- Reading the apiserver's real `--event-ttl` at runtime. The Kubernetes API does not expose it.
- Changes to `mctl_get_service_status`, `mctl_get_service_logs` or other read tools.
- Any change to how `ListServicePods` matches pods (instance label with a name-prefix fallback).

## Open questions
- The issue asks for the service to be resolved against gitops only. `mctl_list_services` also returns "external" and "platform" ArgoCD applications in a tenant namespace that have no `services/{team}/{app}` directory. A gitops-only check would start answering 404 for pod reads of those services, which work today. This proposal therefore falls back to the ArgoCD workload list (`{team}-{app}` deployed into `{team}`). The cost: when ArgoCD is down, an unknown name answers 503, not 404. The reviewer should confirm this is preferred to a gitops-only check.
- An external application whose ArgoCD name does not start with `{team}-` appears in `mctl_list_services` under its full name. Its pods are selected by `{team}-{app}` and could not be found today anyway, so this proposal does not try to resolve such names.
- The cluster's real `--event-ttl` was not checked: no read-only tool exposes apiserver flags. The 1h default comes from the issue's observation (events from the last ~30 minutes returned for `since=24h`).
