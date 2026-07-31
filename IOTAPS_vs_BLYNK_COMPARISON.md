# IoTaps vs Blynk — Short Comparison Notes

---

## 1. Overview

| Feature | IoTaps (Self-Hosted Open SaaS) | Blynk (SaaS / Enterprise) |
|---------|-------------------------------|---------------------------|
| **Deployment** | Self-hosted via Docker Compose on any VPS | Cloud-hosted (Blynk Cloud) or Blynk Local (paid enterprise) |
| **License / Cost** | Open-source, self-managed, pay only for your VPS | Freemium tiers + paid subscriptions based on devices/energy |
| **Control** | Full data sovereignty, DB you own, MQTT broker is yours | Data on Blynk servers unless on Blynk Local |
| **Scaling** | Designed for single-VPS → multi-node horizontal scaling | Handled by Blynk infrastructure |

---

## 2. Core Architecture

| IoTaps | Blynk |
|--------|-------|
| **Backend**: FastAPI (Python async) | **Backend**: Java-based server |
| **Frontend**: React + Vite SPA (JSX) | **Apps**: iOS, Android, Web Dashboard |
| **Device Protocol**: MQTT over Mosquitto broker | **Device Protocol**: Blynk Protocol over TCP/UDP/MQTT |
| **Database**: TimescaleDB (PostgreSQL + time-series extension) | **Database**: Proprietary |
| **Cache/Queue**: Redis (pub/sub, queue, session store) | **Internal**: Proprietary |
| **Workers**: 8 background workers (supervisord) — MQTT listener, batch writer, downsampler, alert checker, webhook dispatcher, notification sender, session cleanup, data retention | **Workers**: Server-side automation (Blynk Logic, Events) |
| **Realtime**: WebSocket gateway (single connection per session, JWT auth via ?token=) | **Realtime**: Blynk's own persistent TCP/SSL connection |

---

## 3. Device Communication

| IoTaps | Blynk |
|--------|-------|
| **Protocol**: MQTT (standard, open) | **Protocol**: Blynk Protocol (proprietary binary over TCP/SSL) + optional MQTT |
| **Auth**: Device token used as MQTT username+password | **Auth**: Auth Token flashed to device |
| **Topics**: `iotaps/<token>/telemetry`, `/command`, `/ack`, `/status` | **Abstracted**: Virtual pins (V0–V255) handled by library |
| **Firmware**: ESP32 Arduino sketch with PubSubClient + ArduinoJson (open, standard libraries) | **Firmware**: Blynk library (proprietary, abstraction layer) |
| **Telemetry**: JSON payloads with key-value pairs, auto-discovered datastreams | **Telemetry**: Virtual pin writes (digital/analog/push) |
| **Commands**: Async via MQTT with ACK tracking (SENT → CONFIRMED/UNACKNOWLEDGED/FAILED) | **Commands**: Virtual pin reads/writes (synchronous via protocol) |
| **OTA / Flashing**: Web flasher via `webFlasher.js` | **OTA**: Blynk.Cloud OTA push |
| **Simulator**: Built-in backend device simulator per device | **No built-in**: Requires external simulation |

---

## 4. Feature Comparison

| Feature | IoTaps | Blynk |
|---------|--------|-------|
| **Device Management** | ✅ Full CRUD, groups, assignment to users, maintenance mode | ✅ Device list, tags, groups |
| **Dashboards** | ✅ Custom dashboards with widgets (auto-discovered datastreams) | ✅ Drag-drop dashboard builder (web + mobile) |
| **Widget Types** | Sensors, toggles, sliders, charts, gauges | Sliders, buttons, charts, gauges, LCD, terminal, etc. (more comprehensive) |
| **Rules / Automation** | ✅ Rule engine with conditions + actions (node graph + `ruleGraph.js`) | ✅ Blynk Automations (if-this-then-that) |
| **Scheduling** | ✅ Cron-based command schedules per device | ✅ Schedule widget + Blynk Logic |
| **Alerts** | ✅ Alert checker worker, notification system | ✅ Built-in push notifications |
| **Webhooks** | ✅ Webhook dispatcher worker | ✅ Webhook URL trigger |
| **Multi-Tenant** | ✅ Org-scoped (Super_Admin, Project_Center, Device_User) | ✅ Organization Workspaces (paid plans) |
| **RBAC** | ✅ 3-tier: Super_Admin → Project_Center → Device_User | ✅ Guest/Viewer/Editor/Admin roles |
| **Billing / Subscriptions** | ✅ Razorpay integration, plans, billing API | ✅ Blynk subscription tiers (energy-based) |
| **Time-Series** | ✅ TimescaleDB hypertables, downsampled rollups (raw/5m/1h/1d), CSV export | ✅ Built-in data storage (limited in free tier) |
| **OTA Updates** | ✅ Web flasher (`webFlasher.js`) | ✅ Cloud OTA |
| **QR Provisioning** | ✅ Auto-generated QR for device tokens | ❌ Direct auth token, no QR |
| **Public Dashboards** | ✅ Public shareable dashboards | ❌ Not available in standard plans |
| **Partner / White-Label** | ✅ Partner API, referral system, commission payouts | ✅ Business + Enterprise plans |
| **Changelog / Audit** | ✅ Changelog API per project | ❌ Not available |
| **Refund System** | ✅ Refund window with property-based testing | ❌ Manual |
| **Mobile App** | ❌ Web-only (PWA-capable?) | ✅ Native iOS + Android apps |
| **Template Library** | ✅ Dashboard + rules templates per device type | ✅ App templates |
| **MongoDB Identity Vault** | ✅ Off-VPS identity mirror (disaster recovery) | ❌ Not available |

---

## 5. Backend Infrastructure

| Component | IoTaps | Blynk |
|-----------|--------|-------|
| API Gateway | Nginx reverse-proxy (SSL, SPA routing, /api / /ws) | Blynk cloud servers |
| REST API | FastAPI — gunicorn + uvicorn workers | JAVA API |
| WebSocket | Separate WS service (dedicated gunicorn workers, `fastapi-ws`) | Part of main server |
| MQTT Broker | Eclipse Mosquitto (per-org ACL) | Proprietary server |
| Database | TimescaleDB (PostgreSQL 16 + time-series) | Proprietary |
| Cache | Redis 7 (LRU eviction, persist + replication) | Proprietary |
| Workers | 8 async workers under supervisord | Blynk Logic server |
| File Descriptors | 65536 ulimit for MQTT (10k+ connections) | Handled by Blynk infra |
| Self-Healing | `restart: always` + healthchecks on all services | Cloud SLA |

---

## 6. Key Differentiators

### IoTaps Strengths
- **Full data ownership** — You control the Postgres DB, Redis, MQTT broker
- **Open standards** — MQTT + JSON = works with any MQTT client, not just ESP32
- **Off-VPS identity vault** — MongoDB Atlas mirror for disaster recovery
- **Built-in simulator per device** — test without hardware
- **Cron-based scheduling** — precise Linux cron for device commands
- **Auto-discovered datastreams** — no manual widget mapping
- **Comprehensive property-based testing** — `test_command_service_property.py`, `test_quota_service_property.py`, etc.
- **Refund window** with property-based test coverage
- **QR generation** for device provisioning
- **Public dashboards** — shareable without login
- **Node assignment system** for multi-node scaling

### Blynk Strengths
- **Native mobile apps** — iOS + Android out of the box
- **More widget types** — LCD, terminal, joystick, etc.
- **Energy-based billing** — transparent device usage pricing
- **Larger community** — more tutorials, examples, third-party content
- **Proven production reliability** — battle-tested at scale
- **Blynk.Edgent** — zero-config WiFi provisioning (ESP32 touch)
- **No infrastructure management** — just flash and go

---

## 7. IoTaps Architecture Diagram (Simplified)

```
┌────────────┐  HTTPS/WS  ┌──────────┐  HTTP   ┌──────────────┐
│  Browser   │ ────────── │  Nginx   │ ──────→  │  FastAPI API │
│  (React)   │ ←──────────│ (SSL +   │ ←──────  │  (REST + WS) │
└────────────┘            │  Proxy)  │          └──────┬───────┘
                          └──────────┘                  │
                               │                        │
                               │ MQTT :1883             │
                               ▼                        │
                        ┌──────────────┐                │
                        │  Mosquitto   │                │
                        │  MQTT Broker │                │
                        └──────┬───────┘                │
                               │                        │
                   ┌───────────┴───────────┐            │
                   ▼                       ▼            ▼
            ┌──────────────┐     ┌─────────────────────────────┐
            │   ESP32      │     │   Workers (supervisord)     │
            │  (Devices)   │     │  MQTT listener, batch       │
            │  MQTT / JSON │     │  writer, downsampler,       │
            └──────────────┘     │  alert, webhook, notify,    │
                                 │  cleanup, retention         │
                                 └──────────┬──────────────────┘
                                            │
                    ┌───────────────────────┼─────────────────┐
                    ▼                       ▼                  ▼
            ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
            │  TimescaleDB │     │    Redis      │     │  MongoDB     │
            │  (Postgres)  │     │  Cache/Queue  │     │  Identity    │
            │  Time-series │     │  Pub/Sub      │     │  Vault       │
            └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 8. Quick Summary

| Aspect | IoTaps | Blynk |
|--------|--------|-------|
| **Best for** | Developers needing custom IoT backend, full data control, white-label SaaS | Rapid prototyping, mobile-first IoT, non-developer users |
| **Setup time** | ~30 min (Docker Compose) | ~5 min (flash ESP32 with Blynk library) |
| **Hardware flex** | Any MQTT-capable device | Blynk library devices (limited) |
| **Self-hosting** | ✅ Yes (full control) | ❌ Cloud-only (free/paid) or Blynk Local ($$$) |
| **Mobile app** | ❌ Web-only | ✅ Native Android + iOS |
| **Cost to run** | VPS cost ($5–30/mo) | Subscription (free tier limited, then paid) |
| **Scaling** | Manual (add nodes, Redis cluster) | Automatic (cloud infrastructure) |
| **Customization** | Full (entire codebase open source) | Limited (paid plan widget branding) |
| **Analytics** | TimescaleDB + rollups + CSV export | Built-in charts + data export |

---

*IoTaps is ideal if you want a self-hosted, open-source, fully customizable IoT platform where you own all data and infrastructure. Blynk is better for quick mobile-first deployments where infrastructure management isn't desired.*