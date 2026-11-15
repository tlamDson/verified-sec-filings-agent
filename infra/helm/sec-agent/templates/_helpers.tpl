{{/* Labels shared by every object; `component` names the part (api, worker, ...). */}}
{{- define "sec-agent.labels" -}}
app.kubernetes.io/name: sec-agent
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "sec-agent.selector" -}}
app.kubernetes.io/name: sec-agent
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "sec-agent.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end }}

{{- define "sec-agent.secret" -}}
{{ required "set secretName to a Secret with PGPASSWORD, API_AUTH_SECRET and SEC_USER_AGENT" .Values.secretName }}
{{- end }}

{{/* Database connection: libpq takes the password from PGPASSWORD, so no URL holds it. */}}
{{- define "sec-agent.dbEnv" -}}
- name: DATABASE_URL
  value: "host={{ .Release.Name }}-postgres port=5432 user=sec dbname=sec"
- name: PGPASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "sec-agent.secret" . }}
      key: PGPASSWORD
{{- end }}

{{/* Init container: wait until Postgres accepts connections. */}}
{{- define "sec-agent.waitForPostgres" -}}
- name: wait-for-postgres
  image: {{ .Values.postgres.image }}
  imagePullPolicy: IfNotPresent
  command:
    - sh
    - -c
    - until pg_isready -h {{ .Release.Name }}-postgres -p 5432 -U sec -d sec; do sleep 2; done
{{- end }}
