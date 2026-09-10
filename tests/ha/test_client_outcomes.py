"""The HA layer relies on typed preflight rejection and the acknowledged mask."""

import pytest

from custom_components.microair_bt.microair.client import MicroAirClient
from custom_components.microair_bt.microair.protocol import ProtocolError

from .conftest import EEPROM, UPSTAIRS, BluetoothHarness, chunks


async def test_acknowledged_mask_result(ble: BluetoothHarness) -> None:
    raw = bytearray(EEPROM)
    raw[906] = 0x14
    ble.replies = [chunks(bytes(raw)), [b'{"Sts": Success}']]
    client = MicroAirClient(ble.routes[UPSTAIRS], max_attempts=1)
    async with client.transaction():
        assert await client.write_startup_mask(1) == 0x15


@pytest.mark.parametrize("kind", ["model", "bits", "partial", "read_failed"])
async def test_preflight_has_distinct_error(ble: BluetoothHarness, kind: str) -> None:
    raw = bytearray(EEPROM)
    if kind == "model":
        raw[2:9] = b"999ULBT"
    elif kind == "bits":
        raw[906] = 0x20
    elif kind == "partial":
        raw = raw[:-3]
    ble.replies = [[b'{"Sts": Fail}'] if kind == "read_failed" else chunks(bytes(raw))]
    client = MicroAirClient(ble.routes[UPSTAIRS], max_attempts=1)
    async with client.transaction():
        with pytest.raises(ProtocolError) as caught:
            await client.write_startup_mask(1)
        assert type(caught.value).__name__ == "StartupModeRejected"
    assert len(ble.clients[0].writes) == 1
