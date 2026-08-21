# Architecture

## Design principles

Four constraints shaped every decision in this codebase.

**1. Measurements are never invented.** Every number the platform displays is
traceable to a stored sample. When a metric has not been measured, the API
returns `null` and the UI renders an em dash — never `0`. When no NVIDIA GPU is
present, the API says so explicitly rather than producing plausible-looking
hardware statistics.

**2. Synthetic data is quarantined.** Every telemetry row carries a
`data_source` discriminator of `production` or `demo`. Every read path filters
on it, and the UI labels demo data persistently. Demo telemetry therefore
cannot be presented as production telemetry.

**3. Diagnosis is deterministic first.** Root-cause findings come from a
rules engine operating on stored measurements. A language model, when
configured, adds narration on top of those findings. It never supplies the
numbers, and the platform is fully functional with no LLM configured at all.

**4. The agent has no dangerous capability.** The agent's tool registry
contains only read-only queries. There is no tool to execute a command, write
to the database, or read configuration. This is enforced by the absence of the
capability, not by an instruction in a prompt.

---

## 1. System architecture

```mermaid
graph TB
    subgraph clients["Clients"]
        BROWSER["Browser<br/>Next.js dashboard"]
        CLI["Scripts and CI"]
    end

    subgraph edge["Edge"]
        INGRESS["Ingress / reverse proxy<br/>TLS termination"]
    end

    subgraph app["Application tier"]
        WEB["Web (Next.js 16)<br/>SSR shell + client queries"]
        API["API (FastAPI)<br/>REST + WebSocket"]
        WORKERS["Background workers<br/>collect · aggregate · analyse · retain"]
    end

    subgraph domain["Domain services"]
        TELEMETRY["Telemetry service"]
        INFERENCE["Inference service"]
        DIAG["Diagnostics engine<br/>15 deterministic rules"]
        ANOM["Anomaly detection<br/>robust z-score · EWMA"]
        COST["Cost service"]
        ALERTS["Alert engine"]
        AGENT["Performance Copilot<br/>11 read-only tools"]
    end

    subgraph collectors["Collectors and adapters"]
        NVML["NVML collector"]
        DCGM["DCGM adapter"]
        PSUTIL["psutil collector"]
        DEMO["Demo generator<br/>7 scenarios"]
        ADAPTERS["Inference adapters<br/>vLLM · Triton · OpenAI · local"]
    end

    subgraph data["Data tier"]
        PG[("PostgreSQL<br/>19 tables")]
        REDIS[("Redis<br/>cache + rate limit")]
    end

    subgraph external["External"]
        GPU["NVIDIA GPUs"]
        LLM["LLM provider<br/>(optional)"]
        PROM["Prometheus"]
        GRAF["Grafana"]
    end

    BROWSER --> INGRESS --> WEB
    BROWSER -.WebSocket.-> INGRESS
    CLI --> INGRESS
    WEB --> API
    INGRESS --> API

    API --> TELEMETRY & INFERENCE & DIAG & COST & ALERTS & AGENT
    WORKERS --> TELEMETRY & ANOM & ALERTS
    DIAG --> ANOM
    AGENT -->|read-only tools| TELEMETRY & INFERENCE & COST & DIAG

    TELEMETRY --> NVML & DCGM & PSUTIL & DEMO
    INFERENCE --> ADAPTERS
    NVML --> GPU
    DCGM --> GPU
    AGENT -.optional narration.-> LLM

    TELEMETRY & INFERENCE & DIAG & COST & ALERTS --> PG
    API --> REDIS
    PROM -->|scrape /metrics| API
    GRAF --> PROM

    classDef accent fill:#1a2e00,stroke:#76b900,color:#e8ebe9
    classDef store fill:#1a1f2e,stroke:#5b9dd9,color:#e8ebe9
    class API,DIAG,AGENT accent
    class PG,REDIS store
```

---

## 2. Telemetry flow

```mermaid
sequenceDiagram
    autonumber
    participant GPU as NVIDIA GPU
    participant AGENT as Telemetry agent<br/>(DaemonSet)
    participant API as API
    participant AGG as Aggregation worker
    participant DB as PostgreSQL
    participant WS as WebSocket clients

    loop every TELEMETRY_INTERVAL_SECONDS
        AGENT->>GPU: NVML query (util, VRAM, temp, power, clocks, throttle)
        alt NVIDIA hardware present
            GPU-->>AGENT: sample per device
        else no hardware
            GPU-->>AGENT: NVML unavailable
            Note over AGENT: Reports availability=false.<br/>Emits no fabricated readings.
        end
        AGENT->>API: POST /api/v1/telemetry/ingest (API key, telemetry:write)
        API->>DB: batch insert gpu_metrics (data_source=production)
        API->>WS: broadcast live snapshot
    end

    loop every 60s
        AGG->>DB: read raw inference_requests for the closed bucket
        AGG->>DB: write inference_metrics + batch_metrics rollups
        Note over AGG,DB: Dashboards read rollups only.<br/>Raw points are never scanned per request.
    end

    loop every RETENTION_SWEEP_INTERVAL_SECONDS
        AGG->>DB: delete raw rows older than RETENTION_RAW_DAYS
        AGG->>DB: delete rollups older than RETENTION_AGGREGATED_DAYS
    end
```

---

## 3. Inference request flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant GW as Inference gateway
    participant AD as Adapter (vLLM / Triton / OpenAI / local)
    participant BE as Inference backend
    participant API as Observatory API
    participant DB as PostgreSQL

    C->>GW: POST /v1/generate
    GW->>GW: assign trace id, start timer
    GW->>AD: infer(prompt, model, max_tokens)
    AD->>BE: backend-native request
    BE-->>AD: completion + usage
    AD-->>GW: result with stage timings<br/>(queue, preprocess, execute, postprocess)
    GW-->>C: response + trace id

    GW->>GW: buffer the observed record
    alt buffer full or shutdown
        GW->>API: POST /api/v1/inference/requests (batch)
        API->>DB: insert inference_requests
    end

    Note over GW,DB: Timings are measured, not estimated.<br/>A failed upstream report increments<br/>nvo_gateway_forward_failures_total.
```

---

## 4. AI diagnosis flow

```mermaid
flowchart TD
    START([Diagnosis requested]) --> CTX[Build DiagnosticContext<br/>one query pass over stored telemetry]
    CTX --> RULES{Run all 15 rules<br/>pure functions of the context}

    RULES --> F1[GPU under-utilisation]
    RULES --> F2[VRAM saturation]
    RULES --> F3[CPU / memory bottleneck]
    RULES --> F4[Latency spike]
    RULES --> F5[Throughput degradation]
    RULES --> F6[Queueing / under-batching / over-batching]
    RULES --> F7[Thermal / power limitation]
    RULES --> F8[Error rate / regression / token / cost]

    F1 & F2 & F3 & F4 & F5 & F6 & F7 & F8 --> SUPER[Apply supersession<br/>specific cause replaces general symptom]
    SUPER --> COAL[Coalesce per-kind<br/>same issue across N devices = one finding]
    COAL --> RANK[Rank by severity × confidence]
    RANK --> EMPTY{Any findings?}

    EMPTY -->|no| HEALTHY[Emit explicit healthy<br/>or no-telemetry result]
    EMPTY -->|yes| PERSIST[(Persist to diagnoses)]

    PERSIST --> LLM{LLM configured?}
    HEALTHY --> LLM
    LLM -->|no| OUT[Structured JSON:<br/>title, severity, root_cause,<br/>evidence, metrics, impact,<br/>recommendations, confidence]
    LLM -->|yes| NARRATE[Narrate the grounded findings<br/>numbers come only from the rules]
    NARRATE --> OUT
    OUT --> END([Response])

    classDef accent fill:#1a2e00,stroke:#76b900,color:#e8ebe9
    class RULES,OUT accent
```

---

## 5. Database entity relationships

```mermaid
erDiagram
    users ||--o{ api_keys : owns
    users ||--o{ refresh_tokens : holds
    gpus ||--o{ gpu_metrics : samples
    gpus ||--o{ gpu_processes : hosts
    ml_models ||--o{ deployments : "deployed as"
    gpus ||--o{ deployments : runs
    deployments ||--o{ inference_requests : serves
    deployments ||--o{ inference_metrics : "rolled up into"
    deployments ||--o{ batch_metrics : "batching for"
    ml_models ||--o{ inference_requests : identifies
    alert_rules ||--o{ alerts : fires
    deployments ||--o{ workloads : "load against"

    users {
        string id PK
        string email UK
        string hashed_password
        string role
        bool is_active
    }
    api_keys {
        string id PK
        string key_hash UK
        string scopes
        string owner_id FK
    }
    gpus {
        string id PK
        string uuid
        int index
        string data_source
        float total_memory_mb
    }
    gpu_metrics {
        string id PK
        string gpu_id FK
        datetime recorded_at
        string data_source
        float utilization_pct
        float memory_utilization_pct
        float temperature_c
        float power_w
    }
    system_metrics {
        string id PK
        string host
        datetime recorded_at
        string data_source
        float cpu_utilization_pct
        float ram_utilization_pct
    }
    ml_models {
        string id PK
        string name
        string version
        string quantization
        int max_batch_size
        string data_source
    }
    deployments {
        string id PK
        string model_id FK
        string gpu_id FK
        int max_batch_size
        float batch_window_ms
        string data_source
    }
    inference_requests {
        string id PK
        string deployment_id FK
        datetime started_at
        float total_latency_ms
        int batch_size
        bool is_error
        string data_source
    }
    inference_metrics {
        string id PK
        string deployment_id FK
        datetime bucket_start
        float p95_latency_ms
        float requests_per_second
        float tokens_per_second
        string data_source
    }
    batch_metrics {
        string id PK
        string deployment_id FK
        datetime bucket_start
        float avg_batch_size
        float batch_efficiency
        float queue_depth
    }
    anomalies {
        string id PK
        datetime detected_at
        string metric_kind
        string severity
        float observed_value
        float score
    }
    alerts {
        string id PK
        string rule_id FK
        string state
        string severity
        datetime triggered_at
    }
    diagnoses {
        string id PK
        string kind
        string severity
        text evidence
        text recommendations
        float confidence
    }
    pricing_profiles {
        string id PK
        float cost_per_gpu_hour
        string currency
        bool is_default
    }
    workloads {
        string id PK
        string profile
        string status
        int requests_generated
    }
    audit_logs {
        string id PK
        datetime occurred_at
        string action
        string outcome
    }
```

---

## 6. Deployment architecture (Docker Compose)

```mermaid
graph LR
    subgraph host["Docker host"]
        subgraph net["nvo bridge network"]
            WEB["web :3000"]
            API["api :8000"]
            GW["inference-gateway :8080"]
            AGENT["telemetry-agent<br/>(profile: gpu)"]
            PG[("postgres :5432")]
            RD[("redis :6379")]
            PROM["prometheus :9090"]
            GRAF["grafana :3001"]
            MIG["migrate<br/>(runs once)"]
        end
        VOL[("named volumes<br/>postgres · redis · prometheus · grafana")]
    end

    USER["Browser"] --> WEB --> API
    MIG -->|alembic upgrade head| PG
    API --> PG & RD
    GW --> API
    AGENT --> API
    PROM -->|scrape /metrics| API & GW
    GRAF --> PROM
    PG & RD & PROM & GRAF -.persist.-> VOL

    classDef accent fill:#1a2e00,stroke:#76b900,color:#e8ebe9
    class API accent
```

---

## 7. Kubernetes architecture

```mermaid
graph TB
    subgraph cluster["Kubernetes cluster"]
        subgraph ns["namespace: nvo (PodSecurity: restricted)"]
            ING["Ingress<br/>observatory.example.com"]
            subgraph apitier["API"]
                APID["Deployment nvo-api<br/>3–12 replicas · HPA · PDB minAvailable=2"]
                APIS["Service :8000"]
            end
            subgraph webtier["Web"]
                WEBD["Deployment nvo-web<br/>2–6 replicas · HPA · PDB"]
                WEBS["Service :3000"]
            end
            GWD["Deployment nvo-inference-gateway"]
            CM["ConfigMap nvo-config"]
            SEC["Secret nvo-secrets<br/>created out-of-band"]
            NP["NetworkPolicies<br/>default-deny ingress"]
        end

        subgraph gpunodes["GPU node pool (nvidia.com/gpu.present=true)"]
            DS["DaemonSet nvo-telemetry-agent"]
            DCGM["dcgm-exporter"]
        end

        subgraph datans["Data (managed service preferred)"]
            PGS["PostgreSQL"]
            RDS["Redis"]
        end

        subgraph monns["namespace: monitoring"]
            PROMO["Prometheus Operator"]
            SM["ServiceMonitor"]
        end
    end

    ING --> WEBS --> WEBD
    ING --> APIS --> APID
    APID -->|initContainer: alembic upgrade head| PGS
    APID --> RDS
    CM & SEC --> APID
    DS --> APIS
    DCGM --> DS
    GWD --> APIS
    SM --> APIS
    PROMO --> SM
    NP -. enforces .-> APID

    classDef accent fill:#1a2e00,stroke:#76b900,color:#e8ebe9
    class APID accent
```

---

## Module layout

| Path | Responsibility |
|---|---|
| `apps/api/app/core/` | Config, logging, security, RBAC, cache, middleware, metrics, errors |
| `apps/api/app/db/` | Declarative base, `UTCDateTime` type, async session management |
| `apps/api/app/models/` | 19 SQLAlchemy models |
| `apps/api/app/schemas/` | Pydantic request/response contracts |
| `apps/api/app/collectors/` | NVML, DCGM, psutil collectors behind one interface |
| `apps/api/app/services/` | Telemetry, inference, cost, alerts, comparison, anomalies |
| `apps/api/app/services/diagnostics/` | Context builder, 15 rules, orchestration engine |
| `apps/api/app/agents/` | LLM providers, tool registry, prompt guard, Copilot |
| `apps/api/app/inference/` | vLLM, Triton, OpenAI-compatible and local adapters |
| `apps/api/app/demo/` | 7 scenarios, generator, runtime and backfill |
| `apps/api/app/realtime/` | WebSocket manager and background worker supervisor |
| `apps/api/app/api/v1/` | HTTP routers |
| `apps/web/app/` | 11 routes (10 dashboard pages + login) |
| `apps/web/components/` | UI primitives, state components, charts, shell |
| `apps/web/hooks/` | TanStack Query hooks, one per resource |
| `services/` | Telemetry agent, inference gateway, workload generator |
| `infra/` | Docker, Kubernetes, Helm, Prometheus, Grafana |

## Key architectural decisions

**Bucketed aggregation, not raw scans.** `resolve_range()` selects a bucket
width that keeps any series under ~720 points. Dashboards read
`inference_metrics` rollups; the raw `inference_requests` table is only touched
for the request detail table and the latency histogram.

**Portable timestamps.** A `UTCDateTime` type decorator normalises every
datetime to timezone-aware UTC on both bind and result. SQLite drops `tzinfo`
on round-trip, which otherwise produces naive/aware comparison crashes at
runtime — this removes the entire class of bug in one place.

**Cache degradation.** Redis is preferred; if it is unreachable at startup the
platform falls back to an in-process cache and logs the downgrade. Readiness
treats the database as the only hard dependency.

**Rules before models.** The diagnostics engine is a pure function of an
explicitly assembled context. This makes it unit-testable against known inputs,
reproducible, and auditable — properties no LLM-only design provides.
