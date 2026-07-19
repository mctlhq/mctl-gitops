# Tasks: incident-argo-id-slug-collision

1. [ ] In the mctl-agents repo, locate the incident-responder's proposal-path
       / slug construction (search for `incident-` combined with a string
       slice of the incident id — likely in
       `orchestrator/incident_responder.py`).
2. [ ] Replace the `incident_id[:8]` slice with a collision-resistant slug,
       e.g. `hashlib.sha1(incident_id.encode()).hexdigest()[:8]`.
3. [ ] Add a guard: if the target proposal directory already exists and the
       incident ID recorded in its `requirements.md` differs from the
       incident currently being processed, do not overwrite — pick a
       disambiguated slug (e.g. append `-2`) and log a warning instead of
       raising / silently clobbering.
4. [ ] Do not modify
       `platform-gitops/agents-state/mctl-gitops/proposals/incident-argo-mct/`
       — it is a separate, still-open proposal for a different incident
       (argo-mctl-agents-implement-1784072700-1784073633).
5. [ ] After merging, trigger a manual incident-responder run
       (mctl_trigger_incident_responder) and confirm it completes with
       status Succeeded, then confirm the next two scheduled ticks (:15 and
       :45 past the hour) also complete Succeeded.
6. [ ] Bump the `mctl-agents` image tag referenced in
       `argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`
       (currently `ghcr.io/mctlhq/mctl-agents:1.17.0`) once the fix is
       released, so the CronWorkflow picks it up.
