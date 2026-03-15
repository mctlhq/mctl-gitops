{{/*
Expand the tenant name.
Uses .Values.tenant.name, falls back to .Release.Name.
*/}}
{{- define "tenant.name" -}}
{{- .Values.tenant.name | default .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels for all tenant resources.
*/}}
{{- define "tenant.labels" -}}
app.kubernetes.io/managed-by: argocd
app.kubernetes.io/part-of: mctl-platform
mctl.me/tenant: {{ include "tenant.name" . | quote }}
{{- if .Values.tenant.githubTeam }}
mctl.me/github-team: {{ .Values.tenant.githubTeam | quote }}
{{- end }}
{{- end }}

{{/*
Labels for a specific team namespace within a multi-team tenant.
*/}}
{{- define "tenant.teamLabels" -}}
app.kubernetes.io/managed-by: argocd
app.kubernetes.io/part-of: mctl-platform
mctl.me/tenant: {{ include "tenant.name" . | quote }}
{{- if .Values.tenant.githubTeam }}
mctl.me/github-team: {{ .Values.tenant.githubTeam | quote }}
{{- end }}
{{- end }}

{{/*
Returns the list of namespace names this tenant owns.
For legacy tenants (no teams): just the tenant name.
For multi-team tenants: {tenant}-{team} for each team.
Usage: range (include "tenant.namespaces" . | fromJsonArray)
*/}}
{{- define "tenant.namespaces" -}}
{{- $tenantName := include "tenant.name" . -}}
{{- if .Values.tenant.teams -}}
  {{- $names := list -}}
  {{- range .Values.tenant.teams -}}
    {{- $names = append $names (printf "%s-%s" $tenantName .name) -}}
  {{- end -}}
  {{- $names | toJson -}}
{{- else -}}
  {{- list $tenantName | toJson -}}
{{- end -}}
{{- end }}
