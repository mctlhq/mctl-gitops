{{/*
Expand the name of the chart.
*/}}
{{- define "base-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "base-service.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "base-service.labels" -}}
helm.sh/chart: {{ include "base-service.name" . }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "base-service.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "base-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "base-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Optional non-selector labels for Backstage/Kubernetes binding.
Do not use these in immutable workload selectors.
*/}}
{{- define "base-service.extraLabels" -}}
{{- with .Values.backstage.kubernetesId }}
backstage.io/kubernetes-id: {{ . | quote }}
{{- end }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "base-service.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "base-service.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
User-supplied pod labels, with the Argo workflow prefix refused.

`workflows.argoproj.io/workflow` gates NetworkPolicy carve-outs that are meant
for pods Argo itself created — internet egress in every tenant namespace, and
Vault reachability. podLabels is tenant-controlled (update-config applies a
caller-supplied config_patch to values.yaml with yq), so without this guard a
tenant can label an ordinary app pod and claim those allowances.

Argo sets the label on its own pods directly; nothing legitimate needs to set it
through this chart. Failing loudly beats silently dropping it — a config that
tries is either a mistake or an attempt, and both deserve a visible sync error.
*/}}
{{- define "base-service.podLabels" -}}
{{- range $k, $v := . }}
{{- if hasPrefix "workflows.argoproj.io/" $k }}
{{- fail (printf "podLabels may not set %q: this label gates NetworkPolicy exceptions for Argo-created pods" $k) }}
{{- end }}
{{- end }}
{{- toYaml . }}
{{- end }}
