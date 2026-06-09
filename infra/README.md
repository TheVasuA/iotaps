# IoTAPS Infrastructure: Worker Supervision & Multi-Node Readiness

This directory holds the deployment building blocks for the single-node Docker
Compose stack that is designed to scale horizontally without an architecture
rewrite. It documents how the platform satisfies the scaling/worker
requirements (Req 30.1, 30.3, 32.1, 32.2).

## Worker supervision (Req 30.1, 30.3)

All **8** background workers run inside the `workers` Compose service under
`supervisord` (`infra/supervisor/supervisord.conf`):

| Worker | Entrypoint | Supervisor program |
| --- | --- | --- |
| MQTT Listener | `python -m app.workers.mqtt_listener` | `mqtt-listener` |
| Batch Writer | `python -m app.workers.batch_writer` | `batch-writer` |
| Downsampler | `python -m app.workers.downsampler` | `downsampler` |
| Alert Checker | `python -m app.workers.alert_checker` | `alert-checker` |
| Webhook Dispatcher | `python -m app.workers.webhook_dispatcher` | `webhook-dispatcher` |
| Notification Sender | `python -m app.workers.notification_sender` | `notification-sender` |
| Session Cleanup | `python -m app.workers.session_cleanup` | `session-cleanup` |
| Data Retention | `python -m app.workers.data_retention` | `data-retention` |

Two layers of self-healing give **immediate restart on unexpected termination**
(Req 30.3):

1. **Per-process** — every `[program:*]` entry sets `autorestart=true` with a
   very high `startretries`, so `supervisord` relaunches a crashed worker
   immediately.
2. **Per-container** — the `workers` Compose service uses `restart: always`, so
   if the whole container (or host) dies, Docker brings it back on reboot.

## Stateless app servers + shared Redis = horizontal scaling (Req 32.1)

The `fastapi-api` service runs `gunicorn` with `${API_WORKERS}` Uvicorn workers
and holds **no per-instance state**:

- **Sessions / refresh tokens** live server-side in Redis under
  `iotaps:refresh:{jti}` (see `app/core/security/jwt.py`,
  `app/core/redis_keys.py`). Access tokens are stateless signed JWTs.
- **Real-time fan-out** uses Redis pub/sub, so a telemetry message published by
  one instance reaches WebSocket clients connected to any other instance.
- **Quota counters, rate-limit buckets, command queues, online-device sets** are
  all Redis-backed and shared across instances.

Because no request is pinned to a specific API process, the app tier scales by
adding instances behind Nginx — each new instance reads/writes the same shared
Redis and Postgres. The 5,000-device single-node target (Req 32.1) is met by one
`fastapi-api` + one `workers` container; growth is a matter of running more API
replicas, not redesigning the system.

## Node registry drives device distribution (Req 32.2)

New Mosquitto nodes are absorbed without code changes via the `mqtt_nodes`
registry:

- Super_Admin registers a node (`POST /api/v1/admin/mqtt-nodes`) with an `ip`,
  `port`, and connection `capacity`; it is stored `active`
  (`app/api/v1/admin_nodes.py`).
- On device provisioning, `assign_node()`
  (`app/services/node_assignment.py`) picks the **active node with the fewest
  active connections** that is still below capacity, atomically claims a
  connection slot (capacity-guarded `UPDATE`), and binds `devices.node_id` to
  it. When every node is full it raises `NoCapacityError` (HTTP 503), signalling
  the admin to add a node.

This greedy, capacity-aware assignment spreads devices across the fleet, so
adding a node immediately starts absorbing new device connections.

## Verification

- `docker compose config` validates with the example env (`.env.example`).
- `supervisord.conf` parses with exactly 8 `program:` sections, one per worker.
- All 8 worker modules import and expose a `python -m app.workers.<name>`
  entrypoint.
- `app/services/test_node_assignment.py` covers capacity-bounded distribution
  (Req 24.4, 32.2); the P18 property test
  (`test_node_assignment_property.py`) proves assignment never exceeds capacity.
