"""Advertisement-gated, transaction-scoped polling for a single EasyStart."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALLOW_RUNNING,
    CONF_POLL_INTERVAL,
    CONF_POLLING_ENABLED,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_BACKOFF,
    MIN_POLL_INTERVAL,
)
from .microair.client import MicroAirClient
from .microair.protocol import EepromData, LiveData, ProtocolError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MicroAirData:
    eeprom: EepromData
    live: LiveData


type MicroAirConfigEntry = ConfigEntry[MicroAirCoordinator]


class MicroAirCoordinator(DataUpdateCoordinator[MicroAirData | None]):
    """Own the unit's lock and route; never retain an idle GATT connection."""

    def __init__(self, hass: HomeAssistant, entry: MicroAirConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self.lock = asyncio.Lock()
        self.powered = False
        self.stopping = False
        self._next_poll = 0.0
        self._failures = 0
        self._poll_task: asyncio.Task[None] | None = None
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def polling_enabled(self) -> bool:
        return bool(self.entry.options.get(CONF_POLLING_ENABLED, True))

    @property
    def allow_running(self) -> bool:
        return bool(self.entry.options.get(CONF_ALLOW_RUNNING, False))

    @property
    def poll_interval(self) -> int:
        return max(
            MIN_POLL_INTERVAL,
            int(self.entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)),
        )

    async def async_start(self) -> None:
        self._unsubscribers = [
            bluetooth.async_register_callback(
                self.hass,
                self._async_advertisement,
                {"address": self.address, "connectable": False},
                bluetooth.BluetoothScanningMode.PASSIVE,
            ),
            bluetooth.async_track_unavailable(
                self.hass, self._async_unavailable, self.address, connectable=False
            ),
        ]
        # Unlike first_refresh, an absent unit must not prevent setup: its
        # maintenance switch has to remain available even while unpowered.
        await self.async_refresh()

    @callback
    def _async_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if self.stopping:
            return
        self.powered = True
        self.async_update_listeners()
        self._async_schedule_poll()

    @callback
    def _async_schedule_poll(self) -> None:
        if (
            self.stopping
            or not self.polling_enabled
            or not self.powered
            or self.lock.locked()
            or monotonic() < self._next_poll
            or (self._poll_task is not None and not self._poll_task.done())
        ):
            return
        self._poll_task = self.hass.async_create_background_task(
            self.async_refresh(), f"{DOMAIN} poll {self.address}"
        )

    @callback
    def _async_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        self.powered = False
        self._next_poll = 0.0
        self.update_interval = None
        self.async_set_update_error(UpdateFailed("EasyStart is not advertising"))

    async def _async_update_data(self) -> MicroAirData | None:
        async with self.lock:
            self.powered = bluetooth.async_address_present(
                self.hass, self.address, connectable=False
            )
            if self.stopping or not self.polling_enabled:
                self.update_interval = None
                raise UpdateFailed("EasyStart polling is paused")
            if not self.powered:
                self.update_interval = None
                raise UpdateFailed(
                    "EasyStart is not advertising (unpowered or out of range)"
                )
            if monotonic() < self._next_poll:
                self.update_interval = timedelta(
                    seconds=max(1, self._next_poll - monotonic())
                )
                # Retain the failed state during backoff; no stale success.
                if not self.last_update_success:
                    raise UpdateFailed("EasyStart is backing off after a failed read")
                return self.data
            try:
                client = self.client_for_current_route()
                async with client.transaction():
                    eeprom = await client.read_eeprom()
                    live = await client.read_live()
            except (BleakError, OSError, ProtocolError, UpdateFailed) as error:
                self._failures = min(self._failures + 1, 8)
                backoff = min(MAX_BACKOFF, self.poll_interval * 2**self._failures)
                self._next_poll = monotonic() + backoff
                self.update_interval = timedelta(seconds=backoff)
                raise UpdateFailed(
                    f"EasyStart GATT busy or unavailable; backing off: {error}"
                ) from error
            self._failures = 0
            self._next_poll = monotonic() + self.poll_interval
            # HA filters unchanged advertisements. Its coordinator timer wakes
            # only while powered, rechecking presence and the gate before I/O.
            self.update_interval = timedelta(seconds=self.poll_interval)
            return MicroAirData(eeprom, live)

    def client_for_current_route(self) -> MicroAirClient:
        """Caller holds lock; resolve anew for both polling and explicit writes."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed("No connectable Bluetooth route to EasyStart")
        # Single attempt: do not try to evict an OEM-app connection. The next
        # advertisement after backoff may schedule another read transaction.
        return MicroAirClient(device, max_attempts=1)

    async def async_set_polling(self, enabled: bool) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, CONF_POLLING_ENABLED: enabled},
        )
        if not enabled:
            self.update_interval = None
        # Persist the gate immediately, then drain any transaction already in
        # flight before returning maintenance control to the operator.
        async with self.lock:
            self._next_poll = 0.0
        self.async_update_listeners()
        if enabled:
            self._async_schedule_poll()

    async def async_shutdown(self) -> None:
        self.stopping = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
        async with self.lock:
            pass
        await super().async_shutdown()
