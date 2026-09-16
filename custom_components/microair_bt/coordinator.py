"""Advertisement-gated polling for a single EasyStart.

Two acquisition modes share this coordinator:

- **connect-per-poll** (default): every read resolves a fresh route, connects,
  reads, and disconnects, so Home Assistant re-picks the best proxy each cycle
  and no idle GATT connection is ever held.
- **live** (opt-in): while live mode is enabled, one background task holds a
  single connection open through one proxy and reads ``ReadLive`` on a fast
  timer, for near-real-time current. The task runs only while live mode is on
  (it exits when live mode is turned off) and only connects while the unit is
  powered and polling is not paused.
"""

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
    CONF_LIVE_INTERVAL,
    CONF_LIVE_MODE,
    CONF_NOMINAL_VOLTAGE,
    CONF_POLL_INTERVAL,
    CONF_POLLING_ENABLED,
    CONF_POWER_FACTOR,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_NOMINAL_VOLTAGE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POWER_FACTOR,
    DOMAIN,
    EEPROM_REFRESH_INTERVAL,
    MAX_BACKOFF,
    MIN_LIVE_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .microair.client import MicroAirClient
from .microair.protocol import EepromData, LiveData, ProtocolError

_LOGGER = logging.getLogger(__name__)

# Minimum spacing between EEPROM read attempts in live mode, so a link that
# cannot carry the ~1 KB ReadEEP transfer degrades to live-only instead of
# reconnecting in a tight loop.
LIVE_EEPROM_RETRY = 60.0


class _LiveReconnect(Exception):
    """Internal: end this live session and reconnect promptly, without backoff.

    Raised when the link itself is healthy but an EEPROM refresh dropped a frame
    (which tears the connection down); live telemetry must not be penalised.
    """


@dataclass(frozen=True)
class MicroAirData:
    # None until a complete EEPROM image has been read on this link; live
    # telemetry does not wait for it.
    eeprom: EepromData | None
    live: LiveData


type MicroAirConfigEntry = ConfigEntry[MicroAirCoordinator]


class MicroAirCoordinator(DataUpdateCoordinator[MicroAirData | None]):
    """Own the unit's lock and route across both acquisition modes."""

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
        self._live_task: asyncio.Task[None] | None = None
        # Set to interrupt the live loop's sleep so it re-evaluates its gates
        # promptly (a fresh advert, a paused switch, an options change, stop).
        self._wake = asyncio.Event()
        self._eeprom: EepromData | None = None
        self._eeprom_at = 0.0
        self._eeprom_next_try = 0.0
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def polling_enabled(self) -> bool:
        return bool(self.entry.options.get(CONF_POLLING_ENABLED, True))

    @property
    def allow_running(self) -> bool:
        return bool(self.entry.options.get(CONF_ALLOW_RUNNING, False))

    @property
    def nominal_voltage(self) -> float:
        return float(
            self.entry.options.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE)
        )

    @property
    def power_factor(self) -> float:
        return float(self.entry.options.get(CONF_POWER_FACTOR, DEFAULT_POWER_FACTOR))

    @property
    def live_mode(self) -> bool:
        return bool(self.entry.options.get(CONF_LIVE_MODE, False))

    @property
    def live_interval(self) -> int:
        return max(
            MIN_LIVE_INTERVAL,
            int(self.entry.options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)),
        )

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
        # In live mode the live task drives all I/O, so skip the initial poll.
        if self.live_mode:
            self._start_live_task()
        else:
            await self.async_refresh()

    @callback
    def _start_live_task(self) -> None:
        """Run the held-connection loop, unless it is already running. The loop
        exits on its own when live mode is turned off, so it is never a perpetual
        background task in connect-per-poll mode."""
        if self.stopping or (
            self._live_task is not None and not self._live_task.done()
        ):
            return
        self._live_task = self.hass.async_create_background_task(
            self._async_live_loop(), f"{DOMAIN} live {self.address}"
        )

    @callback
    def async_options_updated(self) -> None:
        """React to an options change without reloading the entry.

        Starts or wakes the live task when live mode is on, and resumes
        connect-per-poll (letting a running live task exit) when it is off.
        """
        self._wake.set()
        if self.live_mode:
            self._start_live_task()
        else:
            self.update_interval = None
            self._async_schedule_poll()
        self.async_update_listeners()

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
        if self.live_mode:
            self._start_live_task()
            self._wake.set()
        else:
            self._async_schedule_poll()

    @callback
    def _async_schedule_poll(self) -> None:
        if (
            self.stopping
            or self.live_mode
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
        if self.live_mode:
            self._wake.set()
        self.async_set_update_error(UpdateFailed("EasyStart is not advertising"))

    async def _async_update_data(self) -> MicroAirData | None:
        # In live mode the background task owns all I/O; never let a stale
        # connect-per-poll timer open a second connection to a single central.
        if self.live_mode:
            self.update_interval = None
            if self.data is None:
                raise UpdateFailed("EasyStart live mode is starting")
            return self.data
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
                live, eeprom = await self._async_read()
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

    async def _async_live_loop(self) -> None:
        """Hold one connection open and push ReadLive on a fast timer.

        Runs only while live mode is on (it exits when live mode is turned off,
        so it is never a perpetual background task), and only connects while the
        unit is powered and polling is not paused. On any link error it releases
        the connection and backs off; a dropped EEPROM refresh reconnects
        promptly without penalising live telemetry.
        """
        try:
            while not self.stopping and self.live_mode:
                self.powered = bluetooth.async_address_present(
                    self.hass, self.address, connectable=False
                )
                if not (self.polling_enabled and self.powered):
                    await self._sleep(self.live_interval)
                    continue
                try:
                    await self._async_live_session()
                except _LiveReconnect:
                    continue
                except (BleakError, OSError, ProtocolError, UpdateFailed) as error:
                    self.powered = bluetooth.async_address_present(
                        self.hass, self.address, connectable=False
                    )
                    self._failures = min(self._failures + 1, 8)
                    backoff = min(MAX_BACKOFF, self.live_interval * 2**self._failures)
                    self.async_set_update_error(
                        UpdateFailed(f"EasyStart live link lost; backing off: {error}")
                    )
                    await self._sleep(backoff)
        except asyncio.CancelledError:
            raise

    async def _async_live_session(self) -> None:
        """One held-connection session: connect, then loop ReadLive until a gate
        drops or the link fails. Holds the lock so the single BLE central is not
        contended; explicit writes are rejected while live mode is active."""
        async with self.lock:
            if not (
                self.live_mode
                and self.polling_enabled
                and self.powered
                and not self.stopping
            ):
                return
            client = self.client_for_current_route()
            async with client.transaction():
                # Refresh the near-static EEPROM image when due. A dropped frame
                # tears the link down, so reconnect promptly and keep serving
                # live-only rather than blocking on the big transfer. The retry
                # cooldown bounds attempts (a bootstrap image is never "not due"),
                # so a link that cannot carry ReadEEP does not become a
                # connect / fail / reconnect storm.
                if self._live_eeprom_due():
                    self._eeprom_next_try = monotonic() + LIVE_EEPROM_RETRY
                    try:
                        self.cache_eeprom(await client.read_eeprom())
                    except (BleakError, OSError, ProtocolError) as error:
                        _LOGGER.debug(
                            "live EEPROM refresh failed; serving live-only: %s", error
                        )
                        raise _LiveReconnect from error
                while not self.stopping and self.live_mode and self.polling_enabled:
                    live = await client.read_live()
                    self._failures = 0
                    self.async_set_updated_data(MicroAirData(self._eeprom, live))
                    await self._sleep(self.live_interval)

    async def _sleep(self, seconds: float) -> None:
        """Sleep, but return early if the loop is woken to re-evaluate its gates."""
        self._wake.clear()
        try:
            async with asyncio.timeout(seconds):
                await self._wake.wait()
        except TimeoutError:
            pass

    def _live_eeprom_due(self) -> bool:
        """As _eeprom_due, but rate-limited so a link that cannot carry ReadEEP
        does not retry on every reconnect (a missing image is always "due")."""
        return monotonic() >= self._eeprom_next_try and self._eeprom_due()

    def _eeprom_due(self) -> bool:
        return (
            self._eeprom is None
            or monotonic() - self._eeprom_at >= EEPROM_REFRESH_INTERVAL
        )

    async def _async_read(self) -> tuple[LiveData, EepromData | None]:
        """Read live telemetry every poll; read the EEPROM image only when due.

        The small ReadLive reply is read first so a dropped frame in the long
        ReadEEP transfer never costs the poll. A failed refresh keeps the
        cached image; a failed bootstrap read gets one immediate retry on a
        fresh connection and otherwise leaves the EEPROM fields unknown.
        """
        client = self.client_for_current_route()
        async with client.transaction():
            live = await client.read_live()
            if not self._eeprom_due():
                return live, self._eeprom
            try:
                eeprom = await client.read_eeprom()
            except (BleakError, OSError, ProtocolError) as error:
                _LOGGER.debug("EEPROM read failed after live read: %s", error)
                if self._eeprom is not None:
                    return live, self._eeprom
            else:
                self.cache_eeprom(eeprom)
                return live, eeprom
        # Bootstrap: no image yet. One retry, then continue with live data only.
        retry = self.client_for_current_route()
        try:
            async with retry.transaction():
                eeprom = await retry.read_eeprom()
        except (BleakError, OSError, ProtocolError) as error:
            _LOGGER.warning(
                "EasyStart EEPROM image not readable yet (%s); model, firmware "
                "and startup mask stay unknown until a complete read succeeds",
                error,
            )
            return live, None
        self.cache_eeprom(eeprom)
        return live, eeprom

    def cache_eeprom(self, eeprom: EepromData) -> None:
        """Record a verified image; explicit writes call this after readback."""
        self._eeprom = eeprom
        self._eeprom_at = monotonic()

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
        # Wake the live task so it drops (or re-establishes) its held connection
        # promptly, then drain any in-flight transaction before returning
        # maintenance control to the operator.
        self._wake.set()
        async with self.lock:
            self._next_poll = 0.0
        self.async_update_listeners()
        if enabled and not self.live_mode:
            self._async_schedule_poll()

    async def async_shutdown(self) -> None:
        self.stopping = True
        self._wake.set()
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        tasks = [
            task
            for task in (self._poll_task, self._live_task)
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self.lock:
            pass
        await super().async_shutdown()
