# /// script
# requires-python = ">=3.13"
# dependencies = ["bleak>=3.0.2", "bleak-retry-connector>=4.7.0"]
# ///
"""Read-only G1 probe for wiki/ble-transport.md and wiki/available-data.md.

Without a selector this only scans. A selector must match a candidate heard
in this scan before any GATT connection can be attempted. No Home Assistant.
"""

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTServiceCollection
from bleak.exc import BleakError

# Bound adapter startup too: Bleak's discover timeout covers only active scanning.
SCAN_SETUP_TIMEOUT = 10.0


def redact_address(address: str) -> str:
    """Keep only the first three bytes, including for macOS UUID identifiers."""
    if ":" in address:
        return ":".join(address.split(":")[:3]) + ":xx:xx:xx"
    return address.replace("-", "")[:6] + "…"


def describe_services(services: BleakGATTServiceCollection) -> list[dict[str, object]]:
    return [
        {
            "uuid": service.uuid,
            "handle": service.handle,
            "characteristics": [
                {
                    "uuid": char.uuid,
                    "handle": char.handle,
                    "properties": char.properties,
                    "descriptors": [
                        {
                            "uuid": desc.uuid,
                            "handle": desc.handle,
                            "description": desc.description,
                        }
                        for desc in char.descriptors
                    ],
                }
                for char in service.characteristics
            ],
        }
        for service in services
    ]


async def probe(
    *,
    name: str | None = None,
    address: str | None = None,
    json_output: bool = False,
    scan_seconds: float = 5.0,
) -> int:
    # PEP-723 runs in an isolated environment, but the library is this checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from custom_components.microair_bt.microair.client import (
        SERVICE_UUID,
        MicroAirClient,
    )
    from custom_components.microair_bt.microair.protocol import ProtocolError

    observations: list[dict[str, object]] = []
    notifications: list[dict[str, object]] = []
    report: dict[str, object] = {"scan": observations, "notifications": notifications}
    started = time.monotonic()
    exit_code = 0

    def message(text: str) -> None:
        report["message"] = text
        if not json_output:
            print(text)

    def notification(data: bytes) -> None:
        entry: dict[str, object] = {
            "hex": data.hex(),
            "repr": repr(data),
            "len": len(data),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
        notifications.append(entry)
        if not json_output:
            print(
                "notification "
                + " ".join(f"{key}={value}" for key, value in entry.items()),
                flush=True,
            )

    try:
        try:
            async with asyncio.timeout(scan_seconds + SCAN_SETUP_TIMEOUT):
                devices = await BleakScanner.discover(
                    timeout=scan_seconds, return_adv=True
                )
        except TimeoutError as error:
            raise TimeoutError(
                "Bluetooth scan timed out; check adapter power and permissions"
            ) from error
        matches: list[BLEDevice] = []
        candidate_count = 0
        for device, adv in devices.values():
            local_name = adv.local_name or device.name or ""
            candidate = "EasyStart_" in local_name or SERVICE_UUID in {
                uuid.lower() for uuid in adv.service_uuids
            }
            candidate_count += candidate
            entry: dict[str, object] = {
                "name": local_name,
                "address": device.address
                if candidate
                else redact_address(device.address),
                "candidate": candidate,
                "rssi": adv.rssi,
                "service_uuids": adv.service_uuids,
            }
            observations.append(entry)
            if not json_output:
                print(json.dumps(entry))
            if candidate and (
                (name is not None and name == local_name)
                or (address is not None and address.lower() == device.address.lower())
            ):
                matches.append(device)

        if name is None and address is None:
            message(
                f"Scan complete: {candidate_count} EasyStart candidate(s); scan only."
                if candidate_count
                else "No EasyStart candidates heard; no GATT connection attempted."
            )
        elif len(matches) != 1:
            message(
                "No EasyStart target heard; no GATT connection attempted."
                if not matches
                else "Multiple EasyStart targets matched; select an address."
            )
            exit_code = 1
        else:
            client = MicroAirClient(
                matches[0], max_attempts=2, on_notification=notification
            )
            async with client.transaction():
                report["mtu_size"] = client.mtu_size
                report["services"] = describe_services(client.services)
                if not json_output:
                    print(f"mtu_size={client.mtu_size}")
                    print(json.dumps(report["services"], indent=2))
                eeprom = await client.read_eeprom()
                report["eeprom"] = asdict(eeprom) | {"raw": eeprom.raw.hex()}
                if not json_output:
                    print(f"EepromData: {report['eeprom']}")
                live = await client.read_live()
                report["live"] = asdict(live) | {
                    "raw": live.raw.hex(),
                    "status": live.status.name,
                }
                if not json_output:
                    print(f"LiveData: {report['live']}")
    except (BleakError, OSError, ProtocolError, TimeoutError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
        if not json_output:
            print(f"Probe failed: {report['error']}", file=sys.stderr)
    if json_output:
        print(json.dumps(report))
    return exit_code


def positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("scan duration must be finite and positive")
    return seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--name", help="Exact advertised EasyStart name")
    selector.add_argument(
        "--address", help="Address of a candidate heard during this scan"
    )
    parser.add_argument("--json", action="store_true", help="Emit one JSON document")
    parser.add_argument("--scan-seconds", type=positive_seconds, default=5.0)
    args = parser.parse_args(argv)
    return asyncio.run(
        probe(
            name=args.name,
            address=args.address,
            json_output=args.json,
            scan_seconds=args.scan_seconds,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
