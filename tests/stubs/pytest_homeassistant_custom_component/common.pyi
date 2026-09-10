"""Signatures verified against pytest-homeassistant-custom-component 0.13.308."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import Integration

class MockConfigEntry(ConfigEntry[Any]):
    def __init__(
        self,
        *,
        data: Mapping[str, Any] | None = ...,
        domain: str = ...,
        options: Mapping[str, Any] | None = ...,
        title: str = ...,
        unique_id: str | None = ...,
    ) -> None: ...
    def add_to_hass(self, hass: HomeAssistant) -> None: ...

class MockModule:
    def __init__(self, domain: str | None = ...) -> None: ...

def mock_integration(hass: HomeAssistant, module: MockModule) -> Integration: ...
def async_fire_time_changed(hass: HomeAssistant, utc_datetime: datetime) -> None: ...
