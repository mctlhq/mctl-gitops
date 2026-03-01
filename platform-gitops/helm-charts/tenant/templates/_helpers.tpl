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
