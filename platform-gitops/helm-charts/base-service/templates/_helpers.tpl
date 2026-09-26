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

{{/*
secretStoreRef for any ExternalSecret this chart renders.

Defaults to the namespaced `tenant-store` SecretStore, which resolves only this
tenant's Vault prefix. The cluster-wide `vault-backend` store is usable from
every namespace and now only reaches secret/data/platform/*, so a service that
needs a platform path must opt in explicitly:

  externalSecret:
    store: vault-backend
    storeKind: ClusterSecretStore

Accepts a dict of "store" and "kind".
*/}}
{{- define "base-service.secretStoreRef" -}}
name: {{ .store | default "tenant-store" }}
kind: {{ .kind | default "SecretStore" }}{{- end }}

{{/*
Target Secret name for the work-context ExternalSecret
(templates/externalsecret-work-context.yaml). Computed once here so the
ExternalSecret's `target.name` and the `secretKeyRef.name` the `env` block
points at (base-service.env below) can never drift apart.
*/}}
{{- define "base-service.workContextSecretName" -}}
{{- (default dict .Values.workContext).tokenSecretName | default (printf "%s-work-context" (include "base-service.fullname" .)) -}}
{{- end }}

{{/*
The container's `env:` list, shared by deployment.yaml and rollout.yaml.

This exists as one partial rather than two copies because the two templates are
mutually exclusive -- `blueGreen.enabled` picks Rollout *instead of* Deployment
-- so a block added to only one of them is invisible in the other's rendering
and fails silently. That is exactly how the OTEL variables first shipped: a
blueGreen service setting `otel.enabled: true` got no variables, no traces and
no error. tests/test_base_service_otel_env.py renders both kinds and asserts
they agree.

A service's own declarations win on conflict: an otel (or workContext) default
is rendered only when neither `env` nor `envValueFrom` already sets that name,
so the list never carries a duplicate (rather than relying on Kubernetes'
last-one-wins behaviour). Both have to be consulted -- `envValueFrom` can name
OTEL_EXPORTER_OTLP_ENDPOINT just as `env` can, and a duplicate there would be
the harder one to spot, since the two entries do not even look alike.
`default dict` guards a service that writes a bare `env:` key with nothing
under it, which reaches here as nil.

workContext (mctlhq/mctl-gitops#1405) follows the same shape as otel: gated on
`(default dict .Values.workContext).enabled`, emits WORK_CONTEXT_ENABLED,
MCTL_WORK_ITEM_TENANT, MCTL_API_BASE_URL (only while apiBaseUrl is non-empty)
and the surface:telegram token as a secretKeyRef against the Secret name
computed by base-service.workContextSecretName above.

Callers own the `env:` key and the indentation:

  {{- if or .Values.env .Values.envValueFrom .Values.otel.enabled (default dict .Values.workContext).enabled }}
  env:
    {{- include "base-service.env" . | trim | nindent 12 }}
  {{- end }}

`trim` is not decoration: the first `range` emits a leading newline, and
`nindent` would turn that into a blank line of trailing spaces under `env:`,
which is a diff against every service that renders today for no reason.
*/}}
{{- define "base-service.env" -}}
{{- $env := default dict .Values.env -}}
{{- $fromRefs := default dict .Values.envValueFrom -}}
{{- if .Values.otel.enabled }}
{{- $otelEnv := dict
    "OTEL_EXPORTER_OTLP_ENDPOINT" .Values.otel.endpoint
    "OTEL_EXPORTER_OTLP_PROTOCOL" "http/protobuf"
    "OTEL_SERVICE_NAME" (include "base-service.fullname" .)
    "OTEL_RESOURCE_ATTRIBUTES" (printf "service.namespace=%s" .Release.Namespace)
}}
{{- range $key, $value := $otelEnv }}
{{- if not (or (hasKey $env $key) (hasKey $fromRefs $key)) }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- end }}
{{- if (default dict .Values.workContext).enabled }}
{{- $wc := .Values.workContext }}
{{- $tokenEnvName := $wc.tokenEnvName | default "MCTL_SURFACE_TELEGRAM_TOKEN" }}
{{- $wcLiteralEnv := dict
    "WORK_CONTEXT_ENABLED" ($wc.featureEnabled | toString)
    "MCTL_WORK_ITEM_TENANT" ($wc.tenant | default "")
}}
{{- range $key, $value := $wcLiteralEnv }}
{{- if not (or (hasKey $env $key) (hasKey $fromRefs $key)) }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- if $wc.apiBaseUrl }}
{{- if not (or (hasKey $env "MCTL_API_BASE_URL") (hasKey $fromRefs "MCTL_API_BASE_URL")) }}
- name: MCTL_API_BASE_URL
  value: {{ $wc.apiBaseUrl | quote }}
{{- end }}
{{- end }}
{{- if not (or (hasKey $env $tokenEnvName) (hasKey $fromRefs $tokenEnvName)) }}
- name: {{ $tokenEnvName }}
  valueFrom:
    secretKeyRef:
      name: {{ include "base-service.workContextSecretName" . }}
      key: {{ $tokenEnvName }}
      optional: true
{{- end }}
{{- end }}
{{- range $key, $value := $env }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- range $key, $source := $fromRefs }}
- name: {{ $key }}
  valueFrom:
{{- toYaml $source | nindent 4 }}
{{- end }}
{{- end }}
