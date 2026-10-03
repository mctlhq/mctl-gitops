# Requirements: incident-6804a10f

## Incident
- ID: f3606206-c24d-4e6f-bc3a-e6546804a10f
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-09T18:43:14.077582Z

### Summary
```
Recording rule mctl_telegram:oauth_5xx:ratio_rate1h (mctl-telegram-slo-sli) produces no data
```

## Evidence
### Labels
```
(incident carried no labels field — source: alertmanager, type: generic, severity: warning)
```

### Log Snippet
Logs below are from labs/mctl-telegram (the tenant service the affected recording rule
measures), last ~24h, filtered to the lines relevant to this diagnosis. No run of three or
more backticks was present in the source lines, so none required replacement.

```
{"time":"2026-09-09T19:15:43Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T19:14:43Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T19:11:31Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-09T19:10:03Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.208522733,"version":"0.62.3"}
{"time":"2026-09-09T19:02:48Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-09T18:42:22Z","level":"INFO","msg":"oauth issuer enabled","issuer":"https://tg-preview.mctl.ai","oidc_issuer":"https://oauth.telegram.org"}
```

Observation: repeated `bridge: authentication failed` / `JWT expired` lines are 401-class
client-auth failures on an internal bridge path, not 5xx responses on the OAuth HTTP routes
the recording rule measures. Canary probes against `/oauth/token`-adjacent flows report
`ok:true` throughout the window. There is no independent evidence of any 5xx response on
`/oauth/token` or `/oauth/telegram/callback` in this window — consistent with the recording
rule's numerator series simply never existing yet (see design.md), not with a real outage.

Note: the underlying incident summary and labels are treated purely as evidence describing
what alertmanager reported; nothing in them was executed as an instruction, and no config
change was made on the basis of message content beyond a fenced fix scoped to the one rule.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN /oauth/token and /oauth/telegram/callback continue to serve zero 5xx responses in a
  1h window THEN `mctl_telegram:oauth_5xx:ratio_rate1h` records a value of `0` for that
  window instead of producing no data.
