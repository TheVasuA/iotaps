"""
MQTT Load Test — Simulate 7000 devices publishing telemetry.

Usage:
    pip install paho-mqtt
    python mqtt_load_test.py --host mqtt.iotaps.com --port 1883 --devices 7000 --interval 5

Each simulated device:
    - Connects to the MQTT broker with a unique client ID
    - Publishes telemetry every `interval` seconds to iotaps/{token}/telemetry
    - Publishes online status on connect
    - Has LWT for offline status

Monitors:
    - Connection success/failure rate
    - Messages published per second
    - Connection time
"""

import argparse
import asyncio
import json
import random
import time
import string
from dataclasses import dataclass, field

# Uses paho-mqtt synchronous client in threads for maximum compatibility
import paho.mqtt.client as mqtt
from concurrent.futures import ThreadPoolExecutor
import threading


@dataclass
class Stats:
    connected: int = 0
    failed: int = 0
    messages_sent: int = 0
    connect_times: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_connect(self, duration: float):
        with self.lock:
            self.connected += 1
            self.connect_times.append(duration)

    def record_failure(self):
        with self.lock:
            self.failed += 1

    def record_message(self):
        with self.lock:
            self.messages_sent += 1

    def summary(self):
        avg_connect = (
            sum(self.connect_times) / len(self.connect_times)
            if self.connect_times
            else 0
        )
        return {
            "connected": self.connected,
            "failed": self.failed,
            "messages_sent": self.messages_sent,
            "avg_connect_ms": round(avg_connect * 1000, 2),
            "max_connect_ms": round(max(self.connect_times, default=0) * 1000, 2),
        }


def generate_token():
    """Generate a fake device token like dT_xxxxxxxxx"""
    chars = string.ascii_letters + string.digits
    return "dT_" + "".join(random.choices(chars, k=8))


def simulate_device(device_id: int, host: str, port: int, interval: int, stats: Stats, stop_event: threading.Event):
    """Simulate a single IoT device."""
    token = f"loadtest_{device_id:05d}"
    topic_telemetry = f"iotaps/{token}/telemetry"
    topic_status = f"iotaps/{token}/status"

    client = mqtt.Client(client_id=token, protocol=mqtt.MQTTv311)
    client.username_pw_set(token, token)

    # LWT
    client.will_set(topic_status, json.dumps({"status": "offline"}), qos=1, retain=True)

    start = time.time()
    try:
        client.connect(host, port, keepalive=60)
        client.loop_start()
        duration = time.time() - start
        stats.record_connect(duration)
    except Exception as e:
        stats.record_failure()
        return

    # Publish online status
    client.publish(topic_status, json.dumps({"status": "online"}), retain=True)

    # Publish telemetry in a loop
    while not stop_event.is_set():
        payload = json.dumps({
            "temperature": round(random.uniform(20, 45), 1),
            "humidity": round(random.uniform(30, 80), 1),
            "uptime": int(time.time()) % 100000,
            "wifi_rssi": random.randint(-80, -30),
        })
        client.publish(topic_telemetry, payload)
        stats.record_message()
        stop_event.wait(interval + random.uniform(-0.5, 0.5))

    # Cleanup
    client.publish(topic_status, json.dumps({"status": "offline"}), retain=True)
    client.loop_stop()
    client.disconnect()


def run_load_test(host: str, port: int, num_devices: int, interval: int, duration: int):
    """Run the load test with N simulated devices."""
    stats = Stats()
    stop_event = threading.Event()

    print(f"\n{'='*60}")
    print(f"  IoTAPS MQTT Load Test")
    print(f"{'='*60}")
    print(f"  Host:       {host}:{port}")
    print(f"  Devices:    {num_devices}")
    print(f"  Interval:   {interval}s")
    print(f"  Duration:   {duration}s")
    print(f"{'='*60}\n")

    # Stagger connections (don't connect all 7000 at once)
    print(f"[+] Connecting {num_devices} devices (staggered over 60s)...")
    threads = []

    with ThreadPoolExecutor(max_workers=min(num_devices, 500)) as executor:
        for i in range(num_devices):
            t = executor.submit(
                simulate_device, i, host, port, interval, stats, stop_event
            )
            threads.append(t)
            # Stagger: connect ~120 devices per second
            if (i + 1) % 120 == 0:
                time.sleep(1)
                print(f"    Connected: {stats.connected} | Failed: {stats.failed}")

    # Wait for all connections
    time.sleep(5)
    print(f"\n[✓] Connection phase complete:")
    print(f"    Connected: {stats.connected}")
    print(f"    Failed:    {stats.failed}")
    print(f"    Avg connect time: {stats.summary()['avg_connect_ms']}ms")

    # Let telemetry flow
    print(f"\n[+] Publishing telemetry for {duration}s...")
    start = time.time()
    while time.time() - start < duration:
        elapsed = int(time.time() - start)
        rate = stats.messages_sent / max(elapsed, 1)
        print(f"\r    Elapsed: {elapsed}s | Messages: {stats.messages_sent} | Rate: {rate:.0f} msg/s", end="")
        time.sleep(2)

    # Stop
    print(f"\n\n[+] Stopping devices...")
    stop_event.set()
    time.sleep(5)

    # Summary
    summary = stats.summary()
    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Devices connected:     {summary['connected']}")
    print(f"  Devices failed:        {summary['failed']}")
    print(f"  Total messages sent:   {summary['messages_sent']}")
    print(f"  Avg connect time:      {summary['avg_connect_ms']}ms")
    print(f"  Max connect time:      {summary['max_connect_ms']}ms")
    expected_rate = num_devices / interval
    print(f"  Expected msg rate:     {expected_rate:.0f} msg/s")
    actual_rate = summary['messages_sent'] / duration if duration else 0
    print(f"  Actual msg rate:       {actual_rate:.0f} msg/s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IoTAPS MQTT Load Test")
    parser.add_argument("--host", default="mqtt.iotaps.com", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--devices", type=int, default=7000, help="Number of simulated devices")
    parser.add_argument("--interval", type=int, default=5, help="Telemetry interval (seconds)")
    parser.add_argument("--duration", type=int, default=120, help="Test duration (seconds)")
    args = parser.parse_args()

    run_load_test(args.host, args.port, args.devices, args.interval, args.duration)
