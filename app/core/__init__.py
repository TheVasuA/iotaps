"""Core infrastructure helpers for the IoTAPS platform.

This package holds cross-cutting baseline modules that other tasks build on:

- ``redis_keys``   - canonical Redis key/channel namespaces (Cache_Store layout)
- ``mqtt_topics``  - the ``iotaps/{org_id}/{device_id}/{type}`` topic structure
- ``redis_client`` - a shared async Redis connection helper

These modules define *conventions only*. The workers and services that act on
them (MQTT_Listener, Batch_Writer, auth, etc.) are implemented in later tasks.
"""
