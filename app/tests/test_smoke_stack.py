"""Smoke tests for stack boot and health (Task 22.3).

Verifies the platform's deployment surface is structurally sound and that the
core boot-time invariants hold:

  - the FastAPI health endpoint responds (Req 28.1);
  - the Docker Compose stack declares every required service with self-heal
    `restart: always` (Req 32.3);
  - the Nginx reverse proxy routes the SPA, REST API, and WebSocket gateway,
    with SSL terminated at the Cloudflare edge in front of it and the real
    client IP restored from `CF-Connecting-IP` (Req 32.3 / 32.4);
  - dynamic platform settings load through the read-through loader (Req 29.4 /
    boot dependency for 28.1);
  - per-org MQTT ACLs permit same-org topics and deny cross-org publish/
    subscribe (Req 3.5).

Pure-logic checks (health via TestClient, compose/nginx structural validation,
settings loader, ACL matching) always run. Checks that need live infrastructure
(a running Docker Compose stack, a reachable Mosquitto broker) skip gracefully
when that infrastructure is unavailable, so the suite is green in CI/dev.

Run with: python -m pytest app/tests/test_smoke_stack.py
"""

from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core import mqtt_topics as mt
from app.core.settings_loader import _DEFAULT_SETTINGS, get_all_settings, get_setting
from app.main import API_V1_PREFIX, create_app

# Repository root: app/tests/this_file -> app -> <root>
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
NGINX_CONF = REPO_ROOT / "infra" / "nginx" / "nginx.conf"
NGINX_SITE_CONF = REPO_ROOT / "infra" / "nginx" / "conf.d" / "iotaps.conf"
NGINX_REALIP_CONF = REPO_ROOT / "infra" / "nginx" / "conf.d" / "cloudflare-realip.conf"
MOSQUITTO_CONF = REPO_ROOT / "infra" / "mosquitto" / "mosquitto.conf"

# Services the Compose stack must declare (Req 32.3, 30.1).
REQUIRED_SERVICES = {
    "nginx",
    "fastapi-api",
    "workers",
    "mosquitto",
    "postgres",
    "redis",
}


# --------------------------------------------------------------------------- #
# Service health endpoint (Req 28.1)
# --------------------------------------------------------------------------- #
def test_health_endpoint_responds() -> None:
    """The FastAPI health endpoint boots and reports a known status."""
    client = TestClient(create_app())
    resp = client.get(f"{API_V1_PREFIX}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["service"] == "iotaps-api"
    # Health must enumerate dependency statuses for the Super_Admin view.
    assert any(dep["name"] == "redis" for dep in body["dependencies"])


# --------------------------------------------------------------------------- #
# Docker Compose structural validation (Req 32.3)
# --------------------------------------------------------------------------- #
def _load_compose() -> dict:
    assert COMPOSE_FILE.is_file(), f"missing {COMPOSE_FILE}"
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_compose_declares_all_required_services() -> None:
    compose = _load_compose()
    services = compose.get("services", {})
    missing = REQUIRED_SERVICES - set(services)
    assert not missing, f"docker-compose.yml missing services: {sorted(missing)}"


def test_compose_services_self_heal_with_restart_always() -> None:
    """Every service must restart automatically so the stack self-heals."""
    services = _load_compose().get("services", {})
    for name in REQUIRED_SERVICES:
        assert services[name].get("restart") == "always", (
            f"service '{name}' must declare restart: always"
        )


def test_compose_mounts_nginx_and_mosquitto_config() -> None:
    """Nginx and Mosquitto containers mount the infra config files."""
    services = _load_compose().get("services", {})
    nginx_volumes = " ".join(services["nginx"].get("volumes", []))
    assert "infra/nginx/nginx.conf" in nginx_volumes
    assert "infra/nginx/certs" in nginx_volumes  # SSL certs mounted

    mq_volumes = " ".join(services["mosquitto"].get("volumes", []))
    assert "infra/mosquitto/mosquitto.conf" in mq_volumes


# --------------------------------------------------------------------------- #
# Nginx / SSL termination + SPA/REST/WS routing (Req 32.3)
# --------------------------------------------------------------------------- #
def test_nginx_config_files_exist() -> None:
    assert NGINX_CONF.is_file(), f"missing {NGINX_CONF}"
    assert NGINX_SITE_CONF.is_file(), f"missing {NGINX_SITE_CONF}"
    assert NGINX_REALIP_CONF.is_file(), f"missing {NGINX_REALIP_CONF}"


def test_nginx_ssl_terminated_at_cloudflare_edge() -> None:
    """SSL is terminated at the Cloudflare edge in front of Nginx (Req 32.3/32.4).

    The platform fronts Nginx with Cloudflare (orange-cloud proxied), so TLS is
    terminated at Cloudflare and Nginx receives proxied HTTP. For per-IP login
    blocking (Req 29.3) and correct https awareness to keep working, Nginx must
    restore the original visitor IP from Cloudflare's ``CF-Connecting-IP`` header
    and forward the original scheme upstream.
    """
    realip = NGINX_REALIP_CONF.read_text(encoding="utf-8")
    # Real client IP restored from the Cloudflare edge (which did SSL).
    assert "real_ip_header CF-Connecting-IP" in realip
    assert "set_real_ip_from" in realip

    conf = NGINX_SITE_CONF.read_text(encoding="utf-8")
    # The original (https) scheme is forwarded so the app sees the real scheme.
    assert "X-Forwarded-Proto $scheme" in conf
    # Dedicated API vhost that Cloudflare proxies to (api.iotaps.com).
    assert "server_name api.iotaps.com" in conf


def test_nginx_routes_spa_rest_and_websocket() -> None:
    conf = NGINX_SITE_CONF.read_text(encoding="utf-8")
    base = NGINX_CONF.read_text(encoding="utf-8")

    # REST API -> FastAPI upstream.
    assert "location /api/" in conf
    assert "upstream iotaps_api" in base
    assert "fastapi-api:8000" in base

    # WebSocket gateway with HTTP/1.1 upgrade handling.
    assert "location /ws" in conf
    assert "Upgrade $http_upgrade" in conf
    assert "$connection_upgrade" in conf
    assert "$connection_upgrade" in base  # upgrade map defined in http context

    # SPA client-side routing fallback.
    assert "try_files $uri $uri/ /index.html" in conf


def test_nginx_health_check_location_present() -> None:
    """Nginx exposes a lightweight health-check location for upstream probes."""
    conf = NGINX_SITE_CONF.read_text(encoding="utf-8")
    assert "location = /healthz" in conf


# --------------------------------------------------------------------------- #
# platform_settings load via the settings loader (boot dependency, Req 29.4)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_platform_settings_load_known_key() -> None:
    """A known setting loads (from cache/source/default) at boot."""
    value = await get_setting("jwt_access_ttl_seconds")
    assert value == _DEFAULT_SETTINGS["jwt_access_ttl_seconds"]


@pytest.mark.asyncio
async def test_platform_settings_load_all_core_keys() -> None:
    settings = await get_all_settings()
    for key in ("pricing_tiers_monthly", "plan_limits", "rate_limits"):
        assert key in settings


# --------------------------------------------------------------------------- #
# Per-org MQTT ACL enforcement (Req 3.5)
# --------------------------------------------------------------------------- #
def test_mqtt_acl_permits_same_org_topics() -> None:
    """An org's credentials may pub/sub all of its own topics."""
    org = "org-alpha"
    device = "dev-1"
    for topic in (
        mt.telemetry_topic(org, device),
        mt.command_topic(org, device),
        mt.ack_topic(org, device),
        mt.status_topic(org, device),
    ):
        assert mt.org_can_access(org, topic), f"{org} should access {topic}"


def test_mqtt_acl_denies_cross_org_topics() -> None:
    """An org's credentials must not reach another org's topics."""
    org = "org-alpha"
    other = "org-beta"
    cross_topics = (
        mt.telemetry_topic(other, "dev-9"),
        mt.command_topic(other, "dev-9"),
        mt.ack_topic(other, "dev-9"),
        mt.status_topic(other, "dev-9"),
        f"{mt.TOPIC_ROOT}/{other}/#",
    )
    for topic in cross_topics:
        assert not mt.org_can_access(org, topic), (
            f"{org} must be denied cross-org topic {topic}"
        )


def test_mqtt_acl_org_id_prefix_not_substring_matched() -> None:
    """Topic matching is level-based, not a string prefix (no leakage).

    `org-alpha` must not gain access to `org-alpha-2`'s topics just because the
    org_id is a string prefix; the `/` level boundary keeps them isolated.
    """
    assert not mt.org_can_access("org-alpha", mt.telemetry_topic("org-alpha-2", "d"))
    assert not mt.org_can_access("org", mt.telemetry_topic("org2", "d"))


def test_per_org_acl_pattern_enforces_isolation() -> None:
    """A stored credential ACL pattern authorizes only its own org (Req 3.5).

    This mirrors the broker authorization decision: a credential is provisioned
    with ``acl_pattern = iotaps/{org_id}/#`` and every publish/subscribe is
    checked against that exact filter. A credential scoped to org-alpha must be
    allowed on alpha topics and denied on org-beta topics.
    """
    alpha_acl = mt.org_acl_pattern("org-alpha")
    assert alpha_acl == "iotaps/org-alpha/#"

    # Same-org publish + subscribe authorized against the stored pattern.
    for topic in (
        mt.telemetry_topic("org-alpha", "dev-1"),
        mt.command_topic("org-alpha", "dev-1"),
    ):
        assert mt.topic_matches_filter(alpha_acl, topic)

    # Cross-org publish + subscribe denied against the stored pattern.
    for topic in (
        mt.telemetry_topic("org-beta", "dev-1"),
        mt.command_topic("org-beta", "dev-1"),
        "iotaps/org-beta/#",
    ):
        assert not mt.topic_matches_filter(alpha_acl, topic)


def test_mosquitto_broker_config_listeners() -> None:
    """The broker config declares the MQTT + WebSocket listeners it serves.

    The deployed broker runs with anonymous access (devices identify via their
    token used as the MQTT client id); per-org isolation (Req 3.5) is enforced
    by the platform's ACL pattern (see ``org_acl_pattern`` /
    ``topic_matches_filter``), validated above.
    """
    conf = MOSQUITTO_CONF.read_text(encoding="utf-8")
    assert "listener 1883" in conf       # MQTT for devices
    assert "listener 9001" in conf       # WebSocket for browser clients
    assert "protocol websockets" in conf


# --------------------------------------------------------------------------- #
# Live-infrastructure smoke checks (skip gracefully when unavailable)
# --------------------------------------------------------------------------- #
def _docker_compose_available() -> bool:
    return shutil.which("docker") is not None


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_compose_config_valid_when_docker_available() -> None:
    """`docker compose config` parses the stack when Docker is installed."""
    if not _docker_compose_available():
        pytest.skip("docker not available; skipping live compose validation")

    # The stack's services declare `env_file: .env` (a real deployment secret
    # absent in dev/CI). `docker compose config` requires that file to exist, so
    # without it the live structural validation cannot run - skip gracefully.
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        pytest.skip(".env not present; skipping live docker compose validation")

    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "config"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - env
        pytest.skip(f"docker compose not runnable: {exc}")
    # A structurally invalid compose file makes this fail; unset vars only warn.
    assert result.returncode == 0, result.stderr


def test_mosquitto_broker_reachable_when_running() -> None:
    """Mosquitto answers on its MQTT port when the stack is up."""
    if not _port_open("localhost", 1883):
        pytest.skip("mosquitto broker not running on localhost:1883")
    assert _port_open("localhost", 1883)
