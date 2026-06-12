"""
Web/API Load Test — Simulate concurrent dashboard users.

Usage:
    pip install locust
    locust -f web_load_test.py --host https://iotaps.com

Or run headless:
    locust -f web_load_test.py --host https://iotaps.com \
        --users 200 --spawn-rate 10 --run-time 2m --headless

Simulates:
    - User login
    - Device list fetching
    - Dashboard loading
    - Command sending
    - WebSocket subscription (via HTTP polling fallback)
"""

from locust import HttpUser, task, between, events
import json
import random


class IoTAPSUser(HttpUser):
    """Simulates a dashboard user interacting with the IoTAPS platform."""

    wait_time = between(2, 8)  # Think time between actions

    def on_start(self):
        """Login and get access token."""
        # Each virtual user registers or logs in
        self.email = f"loaduser_{self.environment.runner.user_count}_{random.randint(1000,9999)}@test.com"
        self.password = "LoadTest123!"
        self.token = None
        self.devices = []

        # Try to register
        resp = self.client.post("/api/v1/auth/register", json={
            "email": self.email,
            "password": self.password,
        }, name="/api/v1/auth/register")

        # Login
        resp = self.client.post("/api/v1/auth/login", json={
            "email": self.email,
            "password": self.password,
        }, name="/api/v1/auth/login")

        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("access_token")
        else:
            # Use admin account as fallback
            resp = self.client.post("/api/v1/auth/login", json={
                "email": "thevasu.a@gmail.com",
                "password": "p@rv2thiV",
            }, name="/api/v1/auth/login (admin)")
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")

    @property
    def auth_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(5)
    def list_devices(self):
        """Fetch device list — most common action."""
        resp = self.client.get("/api/v1/devices",
                               headers=self.auth_headers,
                               name="/api/v1/devices")
        if resp.status_code == 200:
            self.devices = resp.json()

    @task(3)
    def list_dashboards(self):
        """Fetch dashboards."""
        self.client.get("/api/v1/dashboards",
                       headers=self.auth_headers,
                       name="/api/v1/dashboards")

    @task(2)
    def get_health(self):
        """Health check — lightweight."""
        self.client.get("/api/v1/health", name="/api/v1/health")

    @task(1)
    def send_command(self):
        """Send a command to a random device."""
        if not self.devices:
            return
        device = random.choice(self.devices)
        self.client.post(
            f"/api/v1/devices/{device['id']}/commands",
            headers=self.auth_headers,
            json={"type": "on"},
            name="/api/v1/devices/{id}/commands",
        )

    @task(1)
    def get_device_groups(self):
        """Fetch device groups."""
        self.client.get("/api/v1/devices/groups",
                       headers=self.auth_headers,
                       name="/api/v1/devices/groups")


class AdminUser(HttpUser):
    """Simulates an admin checking system stats."""

    wait_time = between(5, 15)
    weight = 1  # 1 admin per 10 regular users

    def on_start(self):
        resp = self.client.post("/api/v1/auth/login", json={
            "email": "thevasu.a@gmail.com",
            "password": "p@rv2thiV",
        }, name="/api/v1/auth/login (admin)")
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
        else:
            self.token = None

    @property
    def auth_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(3)
    def admin_overview(self):
        self.client.get("/api/v1/admin/overview",
                       headers=self.auth_headers,
                       name="/api/v1/admin/overview")

    @task(2)
    def admin_system_stats(self):
        self.client.get("/api/v1/admin/system-stats",
                       headers=self.auth_headers,
                       name="/api/v1/admin/system-stats")

    @task(1)
    def admin_health(self):
        self.client.get("/api/v1/admin/health",
                       headers=self.auth_headers,
                       name="/api/v1/admin/health")
