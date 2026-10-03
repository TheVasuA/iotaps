import pytest
from sqlalchemy import select

from app.models.infra import MqttNode
from app.services.mqtt_node_seed import seed_default_mqtt_node

_TABLES = [MqttNode.__table__]


@pytest.mark.asyncio
async def test_seed_creates_when_empty(scope_factory):
    async with scope_factory() as session:
        created = await seed_default_mqtt_node(
            session, host="dev-mqtt.iotaps.com", port=1883, capacity=100
        )
        assert created is True
        row = (await session.execute(select(MqttNode))).scalar_one()
        assert row.ip == "dev-mqtt.iotaps.com"
        assert row.port == 1883
        assert row.capacity == 100
        assert row.status == "active"


@pytest.mark.asyncio
async def test_seed_skips_when_nodes_exist(scope_factory):
    async with scope_factory() as session:
        session.add(
            MqttNode(ip="10.0.0.1", port=1883, capacity=50, active_connections=0, status="active")
        )
        await session.commit()

    async with scope_factory() as session:
        created = await seed_default_mqtt_node(
            session, host="dev-mqtt.iotaps.com", port=1883, capacity=100
        )
        assert created is False
