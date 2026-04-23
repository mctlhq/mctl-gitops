{{/*
ConfigMap name for the Layer-3 custom skills bundle of a tenant.
*/}}
{{- define "openclaw-skills.skillsName" -}}
{{ required "team is required" .Values.team }}-openclaw-skills
{{- end -}}

{{/*
ConfigMap name for the Layer-3 identity overrides of a tenant.
*/}}
{{- define "openclaw-skills.identityName" -}}
{{ required "team is required" .Values.team }}-openclaw-identity
{{- end -}}

{{/*
Labels applied to every resource rendered by this chart.
*/}}
{{- define "openclaw-skills.commonLabels" -}}
app.kubernetes.io/name: openclaw-skills
app.kubernetes.io/part-of: openclaw
app.kubernetes.io/managed-by: {{ .Release.Service }}
mctl.ai/team: {{ .Values.team | quote }}
mctl.ai/layer: "3"
{{- end -}}
