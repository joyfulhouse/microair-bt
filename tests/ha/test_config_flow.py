"""Model binding, duplicate prevention and editable polling options."""

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import DOWNSTAIRS, EEPROM, UPSTAIRS, BluetoothHarness, chunks, make_entry


@pytest.fixture(autouse=True)
def flow_only(monkeypatch: pytest.MonkeyPatch) -> None:
    async def setup(hass: HomeAssistant, entry: object) -> bool:
        return True

    monkeypatch.setattr("custom_components.microair_bt.async_setup_entry", setup)


@pytest.mark.parametrize("address", [UPSTAIRS, DOWNSTAIRS])
@pytest.mark.parametrize("source", [SOURCE_BLUETOOTH, SOURCE_USER])
async def test_model_bound_entry(
    hass: HomeAssistant, ble: BluetoothHarness, address: str, source: str
) -> None:
    ble.replies = [chunks(EEPROM)]
    if source == SOURCE_BLUETOOTH:
        result = await hass.config_entries.flow.async_init(
            "microair_bt",
            context={"source": source},
            data=ble.info(address, connectable=False),
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    else:
        result = await hass.config_entries.flow.async_init(
            "microair_bt", context={"source": source}, data={"address": address.lower()}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == address
    assert result["data"] == {"address": address, "model": "398ULBT", "firmware": 37}
    assert [payload for client in ble.clients for _, payload, _ in client.writes] == [
        b'{"Cmd": ReadEEP}'
    ]
    assert all(not client.is_connected for client in ble.clients)


@pytest.mark.parametrize("source", [SOURCE_BLUETOOTH, SOURCE_USER])
async def test_duplicate_aborts_without_connect(
    hass: HomeAssistant, ble: BluetoothHarness, source: str
) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "microair_bt",
        context={"source": source},
        data=ble.info()
        if source == SOURCE_BLUETOOTH
        else {"address": UPSTAIRS.lower()},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert not ble.clients


@pytest.mark.parametrize("kind", ["unsupported", "partial", "offline", "no_route"])
async def test_bind_failure_creates_no_entry(
    hass: HomeAssistant, ble: BluetoothHarness, kind: str
) -> None:
    raw = bytearray(EEPROM)
    if kind == "unsupported":
        raw[2:9] = b"999ULBT"
    if kind == "partial":
        raw = raw[:-3]
    if kind == "offline":
        ble.present.clear()
    if kind == "no_route":
        ble.routes.clear()
    ble.replies = [chunks(bytes(raw))]
    result = await hass.config_entries.flow.async_init(
        "microair_bt", context={"source": SOURCE_USER}, data={"address": UPSTAIRS}
    )
    if kind == "unsupported":
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "unsupported_model"
    else:
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}
    assert not hass.config_entries.async_entries("microair_bt")
    if kind in {"offline", "no_route"}:
        assert not ble.clients


async def test_manual_form_and_address_validation(
    hass: HomeAssistant, ble: BluetoothHarness
) -> None:
    result = await hass.config_entries.flow.async_init(
        "microair_bt", context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "invalid"}
    )
    assert result["errors"] == {"address": "invalid_address"}
    assert not ble.clients


async def test_options_interval_floor(
    hass: HomeAssistant, ble: BluetoothHarness
) -> None:
    entry = make_entry(polling_enabled=False)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"poll_interval": 14, "allow_running": True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_interval"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"poll_interval": 45, "allow_running": True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "poll_interval": 45,
        "allow_running": True,
        "polling_enabled": False,
    }


async def test_manual_uses_passive_metadata_fallback(
    hass: HomeAssistant, ble: BluetoothHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from homeassistant.components import bluetooth

    calls: list[bool] = []

    def last_info(
        hass: HomeAssistant, address: str, connectable: bool = True
    ) -> bluetooth.BluetoothServiceInfoBleak | None:
        calls.append(connectable)
        return None if connectable else ble.info(connectable=False)

    monkeypatch.setattr(bluetooth, "async_last_service_info", last_info)
    ble.replies = [chunks(EEPROM)]
    result = await hass.config_entries.flow.async_init(
        "microair_bt", context={"source": SOURCE_USER}, data={"address": UPSTAIRS}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "EasyStart_88CD"
    assert calls == [True, False]
    assert ble.resolutions == [(UPSTAIRS, True)]


async def test_model_read_can_use_nonconnectable_discovery(
    hass: HomeAssistant, ble: BluetoothHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bleak.backends.device import BLEDevice
    from homeassistant.components import bluetooth

    resolved: list[bool] = []

    def resolve(
        hass: HomeAssistant, address: str, connectable: bool = True
    ) -> BLEDevice | None:
        resolved.append(connectable)
        return None if connectable else ble.routes[address]

    monkeypatch.setattr(bluetooth, "async_ble_device_from_address", resolve)
    ble.replies = [chunks(EEPROM)]
    result = await hass.config_entries.flow.async_init(
        "microair_bt", context={"source": SOURCE_USER}, data={"address": UPSTAIRS}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert resolved == [True, False]
    assert len(ble.clients[0].writes) == 1
