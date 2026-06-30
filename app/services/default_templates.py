"""Default project templates seeded into the global catalog (Req 11).

A starter set of ready-made templates covering the most common IoT use cases
(reference: typical Blynk / ThingsBoard quickstart projects). Each template
carries a dashboard definition (widgets bound to telemetry metrics), alert
rules, and a short Arduino reference sketch.

Seeding is idempotent: :func:`seed_default_templates` inserts a template only if
one with the same name does not already exist, so it is safe to run on every
startup and won't clobber edits made to existing rows.

Widget config keys match what the SPA widgets read (``deviceId`` + ``metric``,
plus ``min``/``max``/``unit``/``title``/``step``/``operator``/``threshold``).
``deviceId`` is intentionally omitted here — :meth:`TemplateService.
apply_template_to_device` injects the target device's id when a template is
applied, so the scaffolded dashboard binds to the real device automatically.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.infra import Template


# ---------------------------------------------------------------------------
# Builders (keep the definitions below compact + consistent)
# ---------------------------------------------------------------------------
def _w(
    wtype: str,
    metric: str | None,
    title: str,
    x: int,
    y: int,
    w: int = 3,
    h: int = 3,
    **config: Any,
) -> dict:
    """Build one widget definition (type + config + grid layout)."""
    cfg: dict[str, Any] = {"title": title}
    if metric is not None:
        cfg["metric"] = metric
    cfg.update(config)
    return {"type": wtype, "config": cfg, "layout": {"x": x, "y": y, "w": w, "h": h}}


def _notify_rule(name: str, key: str, op: str, value: float, message: str) -> dict:
    """Build a simple 'trigger -> notify' alert rule definition."""
    return {
        "name": name,
        "enabled": True,
        "nodes": [
            {"id": "t", "node_type": "trigger", "config": {"key": key, "op": op, "value": value}},
            {
                "id": "a",
                "node_type": "action",
                "config": {"action": "notify", "title": name, "message": message},
            },
        ],
        "edges": [{"from": "t", "to": "a"}],
    }


def _dash(name: str, widgets: list[dict]) -> dict:
    return {"name": name, "widgets": widgets}


def _rules(*rules: dict) -> dict:
    return {"rules": list(rules)}


# ---------------------------------------------------------------------------
# Template catalog
# ---------------------------------------------------------------------------
DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    # --- Student / learning projects -------------------------------------
    {
        "category": "student",
        "name": "3-LED + Sensors Demo",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// IoTAPS demo: 3 toggle LEDs + PWM brightness + temp/voltage.\n"
            "// Telemetry keys: led1, led2, led3, brightness, temperature, voltage.\n"
            "// See firmware/esp32_3led_iotaps.ino for the full reference sketch."
        ),
        "dashboard_def": _dash(
            "3-LED + Sensors",
            [
                _w("gauge", "temperature", "Temperature", 0, 0, 3, 3, min=0, max=50, unit="\u00b0C"),
                _w("value", "voltage", "Voltage", 3, 0, 3, 2, unit="V", precision=2),
                _w("toggle", "led1", "LED 1", 0, 3, 2, 2),
                _w("toggle", "led2", "LED 2", 2, 3, 2, 2),
                _w("toggle", "led3", "LED 3", 4, 3, 2, 2),
                _w("slider", "brightness", "Brightness", 6, 0, 3, 2, min=0, max=255, step=1),
                _w("line", "temperature", "Temperature trend", 6, 3, 6, 3),
            ],
        ),
        "rules_def": _rules(
            _notify_rule(
                "High temperature alert", "temperature", "gt", 40,
                "Device temperature exceeded 40\u00b0C.",
            )
        ),
    },
    {
        "category": "student",
        "name": "Soil Moisture Plant Monitor",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// Capacitive soil sensor on an analog pin; map raw -> 0..100%.\n"
            "// int raw = analogRead(34);\n"
            "// int moisture = map(raw, 3200, 1200, 0, 100);  // calibrate to your sensor\n"
            "// Publish telemetry key: moisture (and optionally temperature)."
        ),
        "dashboard_def": _dash(
            "Plant Monitor",
            [
                _w("gauge", "moisture", "Soil Moisture", 0, 0, 3, 3, min=0, max=100, unit="%"),
                _w("line", "moisture", "Moisture trend", 3, 0, 6, 3),
                _w("toggle", "pump", "Water Pump", 0, 3, 2, 2),
                _w("value", "temperature", "Temperature", 2, 3, 3, 2, unit="\u00b0C"),
            ],
        ),
        "rules_def": _rules(
            _notify_rule(
                "Dry soil alert", "moisture", "lt", 30,
                "Soil moisture dropped below 30% \u2014 the plant needs water.",
            )
        ),
    },
    {
        "category": "student",
        "name": "Temperature & Humidity (DHT) Monitor",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// DHT22 on a digital pin (e.g. GPIO 4). Library: DHT sensor library.\n"
            "// float t = dht.readTemperature();  float h = dht.readHumidity();\n"
            "// Publish telemetry keys: temperature, humidity."
        ),
        "dashboard_def": _dash(
            "Climate Monitor",
            [
                _w("gauge", "temperature", "Temperature", 0, 0, 3, 3, min=-10, max=50, unit="\u00b0C"),
                _w("gauge", "humidity", "Humidity", 3, 0, 3, 3, min=0, max=100, unit="%"),
                _w("line", "temperature", "Temperature trend", 6, 0, 6, 3),
                _w("line", "humidity", "Humidity trend", 0, 3, 6, 3),
            ],
        ),
        "rules_def": _rules(
            _notify_rule("Heat alert", "temperature", "gt", 35, "Temperature exceeded 35\u00b0C."),
            _notify_rule("High humidity alert", "humidity", "gt", 80, "Humidity exceeded 80%."),
        ),
    },
    # --- Company / commercial projects -----------------------------------
    {
        "category": "company",
        "name": "Smart Energy Meter",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// CT clamp + voltage sensor -> compute power = V * I.\n"
            "// Publish telemetry keys: voltage, current, power, energy_kwh."
        ),
        "dashboard_def": _dash(
            "Energy Meter",
            [
                _w("value", "voltage", "Voltage", 0, 0, 2, 2, unit="V", precision=1),
                _w("value", "current", "Current", 2, 0, 2, 2, unit="A", precision=2),
                _w("gauge", "power", "Power", 4, 0, 3, 3, min=0, max=5000, unit="W"),
                _w("value", "energy_kwh", "Energy", 7, 0, 2, 2, unit="kWh", precision=2),
                _w("line", "power", "Power trend", 0, 3, 9, 3),
            ],
        ),
        "rules_def": _rules(
            _notify_rule(
                "High power draw", "power", "gt", 4000,
                "Power draw exceeded 4000 W \u2014 check connected loads.",
            )
        ),
    },
    {
        "category": "company",
        "name": "Cold Storage Compliance",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// Food-grade temperature probe (e.g. DS18B20) inside the unit.\n"
            "// Publish telemetry key: temperature. Alert on cold-chain breach."
        ),
        "dashboard_def": _dash(
            "Cold Storage",
            [
                _w("gauge", "temperature", "Unit Temperature", 0, 0, 3, 3, min=-30, max=15, unit="\u00b0C"),
                _w(
                    "alert_badge", "temperature", "Cold-chain status", 3, 0, 3, 2,
                    operator=">", threshold=8,
                ),
                _w("line", "temperature", "Temperature log", 0, 3, 9, 3),
            ],
        ),
        "rules_def": _rules(
            _notify_rule(
                "Cold-chain breach", "temperature", "gt", 8,
                "Cold storage rose above 8\u00b0C \u2014 stock may be at risk.",
            )
        ),
    },
    {
        "category": "company",
        "name": "Water Tank Level Monitor",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// Ultrasonic sensor (HC-SR04) -> distance -> level %.\n"
            "// Publish telemetry key: level (0..100). Optional actuator key: pump."
        ),
        "dashboard_def": _dash(
            "Water Tank",
            [
                _w("gauge", "level", "Tank Level", 0, 0, 3, 3, min=0, max=100, unit="%"),
                _w("toggle", "pump", "Pump", 3, 0, 2, 2),
                _w("line", "level", "Level trend", 0, 3, 9, 3),
            ],
        ),
        "rules_def": _rules(
            _notify_rule("Low water level", "level", "lt", 20, "Tank level dropped below 20%."),
            _notify_rule("Tank almost full", "level", "gt", 90, "Tank level is above 90%."),
        ),
    },
    {
        "category": "company",
        "name": "Smart Home Controller",
        "wiring_diagram_url": None,
        "arduino_code": (
            "// Relays for light/fan + PWM for fan speed; DHT for room temp.\n"
            "// Telemetry keys: light, fan, fan_speed, temperature."
        ),
        "dashboard_def": _dash(
            "Smart Home",
            [
                _w("toggle", "light", "Light", 0, 0, 2, 2),
                _w("toggle", "fan", "Fan", 2, 0, 2, 2),
                _w("slider", "fan_speed", "Fan Speed", 4, 0, 3, 2, min=0, max=255, step=5),
                _w("value", "temperature", "Room Temp", 7, 0, 2, 2, unit="\u00b0C"),
                _w("line", "temperature", "Temperature trend", 0, 2, 9, 3),
            ],
        ),
        "rules_def": _rules(
            _notify_rule("Room too hot", "temperature", "gt", 32, "Room temperature exceeded 32\u00b0C."),
        ),
    },
]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
async def seed_default_templates(session: AsyncSession) -> int:
    """Insert any missing default templates into the global catalog.

    Idempotent: a template is inserted only when no row with the same name
    exists. Returns the number of templates created.
    """
    existing = set(
        (await session.execute(select(Template.name))).scalars().all()
    )
    created = 0
    for spec in DEFAULT_TEMPLATES:
        if spec["name"] in existing:
            continue
        session.add(
            Template(
                category=spec["category"],
                name=spec["name"],
                arduino_code=spec.get("arduino_code"),
                wiring_diagram_url=spec.get("wiring_diagram_url"),
                dashboard_def=spec.get("dashboard_def"),
                rules_def=spec.get("rules_def"),
            )
        )
        created += 1
    if created:
        await session.commit()
    return created
