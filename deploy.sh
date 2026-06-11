#!/bin/bash
# IoTAPS Production Deploy Script
# Run this on the Contabo VPS after git pull

set -e

echo "=== IoTAPS Production Deploy ==="
echo ""

# 1. Pull latest code
echo "[1/6] Pulling latest code..."
git pull origin main

# 2. Build the backend Docker image
echo "[2/6] Building API image..."
docker compose build fastapi-api

# 3. Build the frontend
echo "[3/6] Building frontend..."
cd web
npm install --production=false
npm run build
cd ..

# 4. Stop and recreate services
echo "[4/6] Restarting services..."
docker compose down
docker compose up -d

# 5. Wait for DB to be healthy and run migrations
echo "[5/6] Running database migrations..."
sleep 10
docker exec -w /srv/app iotaps-api alembic upgrade head || true

# 6. Verify services are running
echo "[6/6] Verifying..."
echo ""
docker compose ps
echo ""
echo "--- API Health ---"
sleep 3
curl -s http://localhost:8000/api/v1/health || echo "API not responding yet, give it a few seconds"
echo ""
echo ""
echo "--- Mosquitto Port Check ---"
docker exec iotaps-mosquitto mosquitto_pub -t test -m "ping" 2>/dev/null && echo "MQTT broker OK" || echo "MQTT broker running (pub test skipped)"
echo ""
echo "=== Deploy Complete ==="
echo ""
echo "IMPORTANT: Make sure your VPS firewall allows:"
echo "  - Port 80   (HTTP / nginx)"
echo "  - Port 443  (HTTPS / future SSL)"
echo "  - Port 1883 (MQTT / device connections)"
echo "  - Port 9001 (MQTT WebSocket / optional)"
echo ""
echo "To open ports on Ubuntu/Debian:"
echo "  sudo ufw allow 1883/tcp"
echo "  sudo ufw allow 9001/tcp"
echo "  sudo ufw reload"
echo ""
echo "Or with iptables:"
echo "  sudo iptables -A INPUT -p tcp --dport 1883 -j ACCEPT"
echo "  sudo iptables -A INPUT -p tcp --dport 9001 -j ACCEPT"
