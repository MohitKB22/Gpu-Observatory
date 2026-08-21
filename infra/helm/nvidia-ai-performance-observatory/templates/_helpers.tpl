{{/* Chart name, overridable. */}}
{{- define "nvo.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully-qualified release name. */}}
{{- define "nvo.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "nvo.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "nvo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: nvidia-ai-performance-observatory
{{- end -}}

{{- define "nvo.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nvo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Resolve a component image reference. */}}
{{- define "nvo.image" -}}
{{- $root := index . 0 -}}
{{- $component := index . 1 -}}
{{- printf "%s/%s:%s" $root.Values.image.registry $component.image.repository $component.image.tag -}}
{{- end -}}
