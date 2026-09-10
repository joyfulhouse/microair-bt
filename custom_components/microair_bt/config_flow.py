"""Discover and bind one EasyStart model to each Bluetooth address."""

import re
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CONF_ALLOW_RUNNING,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MIN_POLL_INTERVAL,
)
from .microair.client import CONTROL_MODELS, MicroAirClient
from .microair.protocol import ProtocolError


class MicroAirConfigFlow(ConfigFlow, domain=DOMAIN):
    """Verify the EEPROM before allowing monitoring or control."""

    VERSION = 1

    def __init__(self) -> None:
        self._address = ""
        self._name = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MicroAirOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        self._address = discovery_info.address.upper()
        self._name = discovery_info.name
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        if not self._name.startswith("EasyStart_"):
            return self.async_abort(reason="unsupported_model")
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_bind("bluetooth_confirm")
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._address = str(user_input[CONF_ADDRESS]).strip().upper()
            if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", self._address):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(self._address)
                self._abort_if_unique_id_configured()
                # Discovery can originate at a passive proxy. Use its metadata
                # as a fallback, then resolve a connectable route for the read.
                info = bluetooth.async_last_service_info(
                    self.hass, self._address, connectable=True
                ) or bluetooth.async_last_service_info(
                    self.hass, self._address, connectable=False
                )
                self._name = info.name if info else self._address
                return await self._async_bind("user")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )

    async def _async_bind(self, step: str) -> ConfigFlowResult:
        # The one-shot model probe also accepts discovery from passive sources.
        # HA's Bleak wrapper still chooses an available connection backend;
        # a passive-only installation fails normally, without a new scanner.
        device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        ) or bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=False
        )
        try:
            if device is None:
                raise ProtocolError("No connectable Bluetooth route")
            client = MicroAirClient(device, max_attempts=1)
            async with client.transaction():
                eeprom = await client.read_eeprom()
        except (BleakError, OSError, ProtocolError):
            return self.async_show_form(
                step_id=step,
                data_schema=(
                    vol.Schema({vol.Required(CONF_ADDRESS): str})
                    if step == "user"
                    else None
                ),
                errors={"base": "cannot_connect"},
                description_placeholders={"name": self._name},
            )
        if eeprom.model not in CONTROL_MODELS:
            return self.async_abort(reason="unsupported_model")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._name,
            data={
                CONF_ADDRESS: self._address,
                "model": eeprom.model,
                "firmware": eeprom.firmware,
            },
        )


class MicroAirOptionsFlow(OptionsFlow):
    """Adjust polling and the explicit permission to write while running."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            interval = user_input[CONF_POLL_INTERVAL]
            if type(interval) is not int or interval < MIN_POLL_INTERVAL:
                errors["base"] = "invalid_interval"
            else:
                return self.async_create_entry(
                    title="", data={**self.config_entry.options, **user_input}
                )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): int,
                    vol.Required(
                        CONF_ALLOW_RUNNING,
                        default=self.config_entry.options.get(
                            CONF_ALLOW_RUNNING, False
                        ),
                    ): bool,
                }
            ),
            errors=errors,
        )
