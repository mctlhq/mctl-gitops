{{/*
Expand the name of the chart.
*/}}
{{- define "worker-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "worker-service.fullname" -}}
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
{{- define "worker-service.labels" -}}
helm.sh/chart: {{ include "worker-service.name" . }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "worker-service.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "worker-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "worker-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "worker-service.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "worker-service.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Container spec (shared between Deployment and CronJob)
*/}}
{{- define "worker-service.containerSpec" -}}
- name: {{ .Chart.Name }}
  image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  {{- with .Values.command }}
  command:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.args }}
  args:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- if .Values.probes.liveness }}
  livenessProbe:
    httpGet:
      path: {{ .Values.probes.liveness.path }}
      port: {{ .Values.probes.liveness.port }}
    initialDelaySeconds: {{ .Values.probes.liveness.initialDelaySeconds }}
    periodSeconds: {{ .Values.probes.liveness.periodSeconds }}
  {{- end }}
  {{- if .Values.probes.readiness }}
  readinessProbe:
    httpGet:
      path: {{ .Values.probes.readiness.path }}
      port: {{ .Values.probes.readiness.port }}
    initialDelaySeconds: {{ .Values.probes.readiness.initialDelaySeconds }}
    periodSeconds: {{ .Values.probes.readiness.periodSeconds }}
  {{- end }}
  resources:
    {{- toYaml .Values.resources | nindent 4 }}
  {{- if .Values.env }}
  env:
    {{- range $key, $value := .Values.env }}
    - name: {{ $key }}
      value: {{ $value | quote }}
    {{- end }}
  {{- end }}
  {{- with .Values.extraVolumeMounts }}
  volumeMounts:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
