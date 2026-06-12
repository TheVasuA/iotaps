# IoTAPS Load Testing

## Prerequisites

```bash
pip install paho-mqtt locust
```

## 1. MQTT Load Test (Simulate 7000 devices)

Simulates N devices connecting to the MQTT broker and publishing telemetry every 5 seconds.

```bash
# Test with 100 devices first
python mqtt_load_test.py --host mqtt.iotaps.com --port 1883 --devices 100 --duration 60

# Ramp up to 1000
python mqtt_load_test.py --host mqtt.iotaps.com --port 1883 --devices 1000 --duration 120

# Full 7000 device test
python mqtt_load_test.py --host mqtt.iotaps.com --port 1883 --devices 7000 --duration 300
```

**What to watch on the server during the test:**
```bash
# In separate SSH sessions:
docker stats                          # CPU/RAM per container
docker logs iotaps-workers -f         # Worker processing
docker exec iotaps-redis redis-cli -a YOUR_REDIS_PASSWORD INFO memory
docker exec iotaps-postgres psql -U iotaps -d iotaps -c "SELECT count(*) FROM telemetry;"
```

## 2. Web/API Load Test (Simulate concurrent users)

Uses [Locust](https://locust.io) to simulate browser users hitting the API.

```bash
# With web UI (open http://localhost:8089)
locust -f web_load_test.py --host http://iotaps.com

# Headless — 200 users, spawning 10/sec, for 2 minutes
locust -f web_load_test.py --host http://iotaps.com \
    --users 200 --spawn-rate 10 --run-time 2m --headless
```

## 3. Combined Test (realistic scenario)

Run both simultaneously to simulate real-world load:

**Terminal 1 — Devices:**
```bash
python mqtt_load_test.py --devices 5000 --duration 300
```

**Terminal 2 — Users:**
```bash
locust -f web_load_test.py --host http://iotaps.com \
    --users 100 --spawn-rate 5 --run-time 5m --headless
```

## Success Criteria

| Metric | Target |
|--------|--------|
| MQTT connections | 7000+ successful |
| Telemetry rate | 1400 msg/s (7000 ÷ 5s) |
| API response time (p95) | < 500ms |
| API error rate | < 1% |
| Ingest queue depth | < 5000 (not growing unbounded) |
| Server RAM | < 80% |
| CPU | < 80% sustained |

## Interpreting Results

- **MQTT connections failing**: Increase server `ulimits` (file descriptors)
- **Ingest queue growing**: Batch writer can't keep up → increase batch size or add workers
- **API slow (>1s p95)**: Add more gunicorn workers or optimize DB queries
- **High RAM**: Reduce telemetry retention or add swap
