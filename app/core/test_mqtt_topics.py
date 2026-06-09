"""Unit tests for the MQTT topic structure (Task 1.4, Req 3.4/3.5)."""

from app.core import mqtt_topics as mt


def test_topic_structure_matches_spec():
    # iotaps/{org_id}/{device_id}/{type}
    assert mt.telemetry_topic("org1", "dev1") == "iotaps/org1/dev1/telemetry"
    assert mt.command_topic("org1", "dev1") == "iotaps/org1/dev1/command"
    assert mt.ack_topic("org1", "dev1") == "iotaps/org1/dev1/ack"
    assert mt.status_topic("org1", "dev1") == "iotaps/org1/dev1/status"


def test_topic_accepts_enum_and_str():
    assert mt.topic("o", "d", mt.MessageType.TELEMETRY) == "iotaps/o/d/telemetry"
    assert mt.topic("o", "d", "command") == "iotaps/o/d/command"


def test_org_acl_pattern_scopes_to_org():
    # Each org's credentials may only reach topics under their own org_id.
    assert mt.org_acl_pattern("org1") == "iotaps/org1/#"


def test_quota_counted_types_excludes_command_ack_status():
    assert mt.MessageType.TELEMETRY in mt.QUOTA_COUNTED_TYPES
    assert mt.MessageType.COMMAND not in mt.QUOTA_COUNTED_TYPES
    assert mt.MessageType.ACK not in mt.QUOTA_COUNTED_TYPES
    assert mt.MessageType.STATUS not in mt.QUOTA_COUNTED_TYPES


def test_backend_wildcard_subscriptions():
    assert mt.ALL_TELEMETRY_SUBSCRIPTION == "iotaps/+/+/telemetry"
    assert mt.ALL_ACK_SUBSCRIPTION == "iotaps/+/+/ack"
    assert mt.ALL_STATUS_SUBSCRIPTION == "iotaps/+/+/status"
