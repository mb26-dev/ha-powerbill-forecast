"""Button to close the billing cycle when the meter reader has been."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VERSION
from .coordinator import PowerbillCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PowerbillCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MeterReadButton(coordinator, entry)])


class MeterReadButton(ButtonEntity):
    """Press when the utility has read the meter: the bill is closed right now."""

    _attr_has_entity_name = True
    _attr_name = "Meter read now"
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: PowerbillCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_meter_read"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="mb26-dev",
            model=coordinator.tariff_name,
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        await self._coordinator.async_meter_reading()
