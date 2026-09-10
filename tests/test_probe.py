"""Prove the probe discovers safely and emits only the two read requests."""

import ast
import inspect
import json
from typing import cast

import pytest
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from scripts import probe
from tests.conftest import DEVICE, FakeRadio
from tests.test_protocol import eeprom_buffer, live_buffer


def advertisement(
    name: str | None, services: list[str] | None = None
) -> AdvertisementData:
    return AdvertisementData(name, {}, {}, services or [], None, -60, ())


def fake_scan(
    monkeypatch: pytest.MonkeyPatch,
    results: dict[str, tuple[BLEDevice, AdvertisementData]],
) -> None:
    async def discover(
        *, timeout: float, return_adv: bool
    ) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
        assert timeout == 2
        assert return_adv is True
        return results

    monkeypatch.setattr(BleakScanner, "discover", discover)


async def test_scan_redacts_non_candidates_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
    radio: FakeRadio,
    capsys: pytest.CaptureFixture[str],
) -> None:
    neighbor = BLEDevice("11:22:33:44:55:66", "Neighbor", None)
    service_candidate = BLEDevice("22:33:44:55:66:77", None, None)
    fake_scan(
        monkeypatch,
        {
            DEVICE.address: (DEVICE, advertisement("EasyStart_TEST")),
            neighbor.address: (neighbor, advertisement("Neighbor")),
            service_candidate.address: (
                service_candidate,
                advertisement(None, ["D973F2E0-B19E-11E2-9E96-0800200C9A66"]),
            ),
        },
    )
    assert await probe.probe(scan_seconds=2) == 0
    output = capsys.readouterr().out
    assert DEVICE.address in output
    assert service_candidate.address in output
    assert "11:22:33" in output
    assert neighbor.address not in output
    neighbor_line = next(line for line in output.splitlines() if "Neighbor" in line)
    assert "44:55:66" not in neighbor_line
    assert not radio.clients


@pytest.mark.parametrize("selector", ["name", "address"])
@pytest.mark.parametrize("json_output", [False, True])
async def test_selected_probe_reads_and_records_notifications(
    monkeypatch: pytest.MonkeyPatch,
    radio: FakeRadio,
    capsys: pytest.CaptureFixture[str],
    selector: str,
    json_output: bool,
) -> None:
    fake_scan(monkeypatch, {DEVICE.address: (DEVICE, advertisement("EasyStart_TEST"))})
    raw = eeprom_buffer()
    radio.replies = [
        [raw[i : i + 20] for i in range(0, 1100, 20)] + [b"Success\r\n"],
        [live_buffer(), b"Success\0"],
    ]
    assert (
        await probe.probe(
            name=DEVICE.name if selector == "name" else None,
            address=DEVICE.address.lower() if selector == "address" else None,
            json_output=json_output,
            scan_seconds=2,
        )
        == 0
    )
    output = capsys.readouterr().out
    assert radio.clients[0].writes == [
        ("d973f2e2-b19e-11e2-9e96-0800200c9a66", b'{"Cmd": ReadEEP}', True),
        ("d973f2e2-b19e-11e2-9e96-0800200c9a66", b'{"Cmd": ReadLive}', True),
    ]
    assert not radio.clients[0].is_connected
    if json_output:
        report = json.loads(
            output
        )  # Rejects extra JSON documents or mixed stdout text.
        assert report["mtu_size"] == 23
        assert report["eeprom"]["model"] == "398ULBT"
        assert report["eeprom"]["raw"] == raw.hex()
        assert report["live"]["current_a"] == 12.3
        assert report["live"]["status"] == "SHORT_CYCLE_DELAY"
        assert len(report["notifications"]) == 58
        notification = report["notifications"][-1]
        assert notification["hex"] == b"Success\0".hex()
        assert notification["repr"] == repr(b"Success\0")
        assert notification["len"] == 8
        assert notification["elapsed_ms"] >= 0
        characteristic = report["services"][0]["characteristics"][1]
        assert characteristic["properties"] == ["write", "write-without-response"]
        assert "descriptors" in characteristic
        descriptor = report["services"][0]["characteristics"][0]["descriptors"][0]
        assert descriptor["uuid"] == "00002902-0000-1000-8000-00805f9b34fb"
        assert descriptor["handle"] == 4
        assert descriptor["description"] == "Client Characteristic Configuration"
    else:
        for value in (
            "398ULBT",
            "12.3",
            "mtu_size=23",
            "properties",
            "descriptors",
            "len=8",
            "elapsed_ms=",
            b"Success\0".hex(),
            repr(b"Success\0"),
        ):
            assert value in output


@pytest.mark.parametrize("name", [None, "EasyStart_ABCD"])
async def test_no_target_heard_never_connects(
    monkeypatch: pytest.MonkeyPatch,
    radio: FakeRadio,
    capsys: pytest.CaptureFixture[str],
    name: str | None,
) -> None:
    fake_scan(monkeypatch, {})
    assert await probe.probe(name=name, json_output=True, scan_seconds=2) == (
        0 if name is None else 1
    )
    report = json.loads(capsys.readouterr().out)
    assert "No EasyStart" in report["message"]
    assert not radio.clients


async def test_explicit_address_cannot_connect_non_candidate(
    monkeypatch: pytest.MonkeyPatch,
    radio: FakeRadio,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = BLEDevice("11:22:33:44:55:66", "Other", None)
    fake_scan(monkeypatch, {other.address: (other, advertisement("Other"))})
    assert (
        await probe.probe(address=other.address, json_output=True, scan_seconds=2) == 1
    )
    assert other.address not in capsys.readouterr().out
    assert not radio.clients


async def test_ambiguous_name_never_connects(
    monkeypatch: pytest.MonkeyPatch, radio: FakeRadio
) -> None:
    other = BLEDevice("00:11:22:33:44:55", DEVICE.name, None)
    fake_scan(
        monkeypatch,
        {
            DEVICE.address: (DEVICE, advertisement(DEVICE.name)),
            other.address: (other, advertisement(DEVICE.name)),
        },
    )
    assert await probe.probe(name=DEVICE.name, scan_seconds=2) == 1
    assert not radio.clients


async def test_transport_error_is_one_json_document(
    monkeypatch: pytest.MonkeyPatch,
    radio: FakeRadio,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_scan(monkeypatch, {DEVICE.address: (DEVICE, advertisement(DEVICE.name))})
    radio.replies = [[b"Fail"]]
    assert await probe.probe(name=DEVICE.name, json_output=True, scan_seconds=2) == 1
    report = json.loads(capsys.readouterr().out)
    assert "error" in report
    assert report["notifications"][0]["repr"] == "b'Fail'"
    assert not radio.clients[0].is_connected


@pytest.mark.parametrize(
    "address", ["AA:BB:CC:DD:EE:FF", "AABBCCDD-EEFF-1122-3344-556677889900"]
)
def test_address_redaction(address: str) -> None:
    redacted = probe.redact_address(address)
    assert "AABBCC" in redacted.replace(":", "")
    assert "DD" not in redacted


def test_module_has_only_read_command_paths() -> None:
    source = inspect.getsource(probe)
    assert "SET_STARTUP_MASK" not in source
    assert "SMask" not in source
    tree = ast.parse(source)
    commands = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Command"
    }
    assert commands <= {"READ_EEP", "READ_LIVE"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and not (
            isinstance(node.func.value, ast.Name) and node.func.value.id == "asyncio"
        )
    }
    assert {"read_eeprom", "read_live"} <= calls
    assert not {
        "write_startup_mask",
        "write_gatt_char",
        "write_gatt_descriptor",
        "_run",
        "run",
    }.intersection(calls)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_cli_rejects_invalid_scan_duration(value: str) -> None:
    with pytest.raises(SystemExit) as error:
        probe.main(["--scan-seconds", value])
    assert error.value.code == 2


def test_cli_selectors_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as error:
        probe.main(["--name", "EasyStart_TEST", "--address", "AA:BB:CC:DD:EE:FF"])
    assert error.value.code == 2


def test_pep723_dependencies() -> None:
    import tomllib

    source = inspect.getsource(probe)
    metadata = source.split("# /// script\n", 1)[1].split("# ///", 1)[0]
    parsed = tomllib.loads(
        "\n".join(line.removeprefix("# ") for line in metadata.splitlines())
    )
    dependencies = cast(list[str], parsed["dependencies"])
    assert {dep.split(">=")[0] for dep in dependencies} == {
        "bleak",
        "bleak-retry-connector",
    }
    assert parsed["requires-python"] == ">=3.13"


async def test_unready_adapter_has_bounded_scan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import asyncio

    async def unready(
        *, timeout: float, return_adv: bool
    ) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
        await asyncio.Event().wait()
        raise AssertionError("Unreachable")

    monkeypatch.setattr(BleakScanner, "discover", unready)
    monkeypatch.setattr(probe, "SCAN_SETUP_TIMEOUT", 0, raising=False)
    result = await asyncio.wait_for(
        probe.probe(scan_seconds=0.01, json_output=True), timeout=0.2
    )
    assert result == 1
    report = json.loads(capsys.readouterr().out)
    assert "scan" in report["error"].lower()
    assert "timed out" in report["error"].lower()
