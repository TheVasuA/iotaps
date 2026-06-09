# IoTAPS Platform

Multi-tenant IoT SaaS platform (FastAPI + React) deployed via Docker Compose on
a single Contabo VPS, architected to scale to multiple nodes.

## Repository layout

```
.
├── app/                      # FastAPI backend + background workers
│   ├── Dockerfile            # Shared image for api + workers services
│   ├── requirements.txt
│   ├── main.py               # FastAPI app entrypoint (app.main:app)
│   └── workers/              # 8 background worker entrypoints (Req 30.1)
│       ├── mqtt_listener.py
│       ├── batch_writer.py
│       ├── downsampler.py
│       ├── alert_checker.py
│       ├── webhook_dispatcher.py
│       ├── notification_sender.py
│       ├── session_cleanup.py
│       └── data_retention.py
├── web/                      # React + Vite SPA (scaffolded in task 1.5)
├── infra/                    # Deployment configuration
│   ├── nginx/                # Reverse proxy + SSL config
│   ├── mosquitto/            # MQTT broker config
│   └── supervisor/           # Worker process supervision
├── docker-compose.yml        # Full service stack
└── .env.example              # Configuration template (no real secrets)
```

## Services (docker-compose.yml)

| Service       | Image / build              | Purpose                                    |
|---------------|----------------------------|--------------------------------------------|
| `nginx`       | nginx:1.27-alpine          | Reverse proxy + SSL (Req 32.3)             |
| `fastapi-api` | build `./app`              | REST API + WebSocket gateway               |
| `workers`     | build `./app` + supervisor | 8 background workers (Req 30.1, 30.3)      |
| `mosquitto`   | eclipse-mosquitto:2        | MQTT broker (per-org ACL)                  |
| `postgres`    | timescale/timescaledb      | Relational + time-series (TimescaleDB ext) |
| `redis`       | redis:7-alpine             | Cache, pub/sub, queue, sessions, quotas    |

All services use `restart: always` for self-healing (Req 30.3, 32.3).

## Getting started

```bash
cp .env.example .env        # fill in real values
docker compose build
docker compose up -d
```

## Edge, SSL, and backups

Nginx reverse-proxy + SSL routing (SPA / `/api` / `/ws`), the Cloudflare
CDN/DNS/DDoS setup, and Contabo snapshot backups are documented in
[`infra/README.md`](infra/README.md) (Req 32.3, 32.4, 29.6).
