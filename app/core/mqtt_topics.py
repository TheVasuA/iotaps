"""MQTT topic structure for the IoTAPS broker.

Single source of truth for the topic layout

    iotaps/{org_id}/{device_id}/{type}

where ``type`` is one of ``telemetry``, ``command``, ``ack``, ``status``
(design "MQTT topics & payloads", Req 3.4). Per-org ACLs restrict every
organization's credentials to ``iotaps/{org_id}/#`` (Req 3.5) - the ACL pattern
helper lives here so provisioning (Task 4.x) and the Mosquitto auth backend use
the exact same string.
"""

from __future__ import annotations

from enum import Enum

# Root segment of every topic. Mirrors MQTT_TOPIC_ROOT in .env.example.
TOPIC_ROOT = "iotaps"


class MessageType(str, Enum):
    """The four message types carried under a device's topic tree."""

    TELEMETRY = "telemetry"  # device -> broker (Req 6.1)
    COMMAND = "command"      # broker -> device (Req 9.1, 9.2)
    ACK = "ack"              # device -> broker (Req 9.4)
    STATUS = "status"        # device -> broker, LWT (online/offline)


# Message types that count toward the Free_Plan Message_Quota. Only telemetry
# is counted; command/ack/status are excluded (Req 15.4).
QUOTA_COUNTED_TYPES: frozenset[MessageType] = frozenset({MessageType.TELEMETRY})


def topic(org_id: str, device_id: str, message_type: MessageType | str) -> str:
    """Build a fully-qualified topic ``iotaps/{org_id}/{device_id}/{type}``."""
    mt = message_type.value if isinstance(message_type, MessageType) else str(message_type)
    return f"{TOPIC_ROOT}/{org_id}/{device_id}/{mt}"


def telemetry_topic(org_id: str, device_id: str) -> str:
    """Telemetry topic for a device (device publishes here)."""
    return topic(org_id, device_id, MessageType.TELEMETRY)


def command_topic(org_id: str, device_id: str) -> str:
    """Command topic for a device (platform publishes here)."""
    return topic(org_id, device_id, MessageType.COMMAND)


def ack_topic(org_id: str, device_id: str) -> str:
    """Command-ACK topic for a device (device publishes here)."""
    return topic(org_id, device_id, MessageType.ACK)


def status_topic(org_id: str, device_id: str) -> str:
    """Status/LWT topic for a device (online/offline)."""
    return topic(org_id, device_id, MessageType.STATUS)


def org_acl_pattern(org_id: str) -> str:
    """ACL pattern granting an org access to all of its topics only (Req 3.5).

    Stored on ``mqtt_credentials.acl_pattern`` and enforced by the Mosquitto
    auth backend so an org's credentials can publish/subscribe only under their
    own ``org_id``.
    """
    return f"{TOPIC_ROOT}/{org_id}/#"


def topic_matches_filter(topic_filter: str, topic: str) -> bool:
    """Return ``True`` if ``topic`` matches an MQTT ``topic_filter``.

    Implements the MQTT topic-filter wildcard rules used by the broker:

    - ``+`` matches exactly one topic level.
    - ``#`` is a multi-level wildcard that matches the remaining levels (and the
      parent level); it is only valid as the final segment.

    This is the precise matching the Mosquitto auth backend performs to
    authorize a credential's ``acl_pattern`` against a requested publish/
    subscribe topic (Req 3.5), so the per-org ACL helper and the backend share
    one implementation.
    """
    filter_parts = topic_filter.split("/")
    topic_parts = topic.split("/")

    for i, fpart in enumerate(filter_parts):
        if fpart == "#":
            # Multi-level wildcard: matches the rest of the topic. Per the MQTT
            # spec it must be the last segment, so we stop here.
            return True
        if i >= len(topic_parts):
            return False
        if fpart == "+":
            continue
        if fpart != topic_parts[i]:
            return False

    # No multi-level wildcard consumed the tail: lengths must match exactly.
    return len(filter_parts) == len(topic_parts)


def org_can_access(org_id: str, topic: str) -> bool:
    """Return ``True`` if an org's credentials may publish/subscribe ``topic``.

    Enforces per-org isolation (Req 3.5): a credential scoped to
    ``iotaps/{org_id}/#`` is allowed only on topics under its own ``org_id``;
    any cross-org topic is denied.
    """
    return topic_matches_filter(org_acl_pattern(org_id), topic)


# Wildcard subscription used by the backend MQTT_Listener to receive telemetry
# from every org/device (Task 5.1). The backend connects with privileged
# internal credentials, not per-org ones.
ALL_TELEMETRY_SUBSCRIPTION = f"{TOPIC_ROOT}/+/+/{MessageType.TELEMETRY.value}"
ALL_ACK_SUBSCRIPTION = f"{TOPIC_ROOT}/+/+/{MessageType.ACK.value}"
ALL_STATUS_SUBSCRIPTION = f"{TOPIC_ROOT}/+/+/{MessageType.STATUS.value}"
