"""Sensors for Powerbill Forecast."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import PowerbillCoordinator

MONEY = "money"  # placeholder unit, replaced by the configured currency
PRICE = "price"  # currency per kWh


@dataclass(frozen=True, kw_only=True)
class PowerbillSensorDescription(SensorEntityDescription):
    """Describes one Powerbill sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _bill_attrs(key: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def attrs(d: dict[str, Any]) -> dict[str, Any]:
        b = d[key]
        return {
            "kwh": b["kwh"],
            "energy": b["energy"],
            "ft": b["ft"],
            "service_fee": b["service_fee"],
            "vat": b["vat"],
            "tier": b["current_tier"],
            "tariff": d["tariff"],
        }

    return attrs


SENSORS: tuple[PowerbillSensorDescription, ...] = (
    PowerbillSensorDescription(
        key="forecast_bill",
        name="Forecast bill",
        icon="mdi:crystal-ball",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=MONEY,
        suggested_display_precision=2,
        value_fn=lambda d: d["forecast_bill"]["total"],
        attrs_fn=_bill_attrs("forecast_bill"),
    ),
    PowerbillSensorDescription(
        key="current_bill",
        name="Current bill",
        icon="mdi:receipt-text",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=MONEY,
        suggested_display_precision=2,
        value_fn=lambda d: d["bill"]["total"],
        attrs_fn=_bill_attrs("bill"),
    ),
    PowerbillSensorDescription(
        key="previous_bill",
        name="Previous cycle bill",
        icon="mdi:receipt-text-clock",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=MONEY,
        suggested_display_precision=2,
        value_fn=lambda d: d["previous_total"],
        attrs_fn=lambda d: {
            "kwh": d["previous_kwh"],
            "cycle_start": (d.get("previous") or {}).get("cycle_start"),
            "cycle_end": (d.get("previous") or {}).get("cycle_end"),
            "ft": (d.get("previous") or {}).get("ft"),
            "closed_at": (d.get("previous") or {}).get("closed_at"),
            "reading": (d.get("previous") or {}).get("reading"),
            "ha_kwh": (d.get("previous") or {}).get("ha_kwh"),
            "utility_kwh": (d.get("previous") or {}).get("utility_kwh"),
            "energy": ((d.get("previous") or {}).get("bill") or {}).get("energy"),
            "vat": ((d.get("previous") or {}).get("bill") or {}).get("vat"),
        },
    ),
    PowerbillSensorDescription(
        key="ft",
        name="Ft surcharge",
        icon="mdi:gas-station",
        native_unit_of_measurement=PRICE,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["ft"],
        attrs_fn=lambda d: {k: v for k, v in d["ft_info"].items() if k != "value"},
    ),
    PowerbillSensorDescription(
        key="cycle_energy",
        name="Cycle energy",
        icon="mdi:lightning-bolt",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d["kwh"],
    ),
    PowerbillSensorDescription(
        key="forecast_energy",
        name="Forecast energy",
        icon="mdi:lightning-bolt-outline",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d["forecast"]["kwh"],
        attrs_fn=lambda d: {"daily_rate": d["forecast"]["daily_rate"], "recent_daily": d["recent_daily"]},
    ),
    PowerbillSensorDescription(
        key="current_tier",
        name="Current tier",
        icon="mdi:stairs-up",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["bill"]["current_tier"],
        attrs_fn=lambda d: {
            "tier_count": d["bill"]["tier_count"],
            "rate": d["tiers"][d["bill"]["current_tier"] - 1]["rate"],
            "forecast_tier": d["forecast_bill"]["current_tier"],
        },
    ),
    PowerbillSensorDescription(
        key="kwh_to_next_tier",
        name="Energy to next tier",
        icon="mdi:stairs-box",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d["bill"]["kwh_to_next_tier"],
        attrs_fn=lambda d: {"days_to_next_tier": d["days_to_next_tier"], "next_rate": d["bill"]["next_rate"]},
    ),
    PowerbillSensorDescription(
        key="marginal_price",
        name="Price of next kWh",
        icon="mdi:cash-plus",
        native_unit_of_measurement=PRICE,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["bill"]["marginal_price"],
        attrs_fn=lambda d: {"next_tier_price": d["bill"]["next_marginal_price"], "includes": "rate + Ft + VAT"},
    ),
    PowerbillSensorDescription(
        key="average_price",
        name="Average price",
        icon="mdi:cash-multiple",
        native_unit_of_measurement=PRICE,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["bill"]["average_price"],
    ),
    PowerbillSensorDescription(
        key="days_remaining",
        name="Days left in cycle",
        icon="mdi:calendar-clock",
        native_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=1,
        value_fn=lambda d: d["forecast"]["days_remaining"],
        attrs_fn=lambda d: {"cycle_start": d["cycle_start"], "cycle_end": d["cycle_end"]},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PowerbillCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PowerbillSensor(coordinator, entry, desc) for desc in SENSORS)


class PowerbillSensor(CoordinatorEntity[PowerbillCoordinator], SensorEntity):
    """One value of the bill forecast."""

    _attr_has_entity_name = True
    # the card payload changes constantly and would bloat the database
    _unrecorded_attributes = frozenset({"card_data"})

    def __init__(
        self, coordinator: PowerbillCoordinator, entry: ConfigEntry, description: PowerbillSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="mb26-dev",
            model=coordinator.tariff_name,
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )
        unit = description.native_unit_of_measurement
        if unit == MONEY:
            self._attr_native_unit_of_measurement = coordinator.currency or None
        elif unit == PRICE:
            self._attr_native_unit_of_measurement = f"{coordinator.currency}/kWh" if coordinator.currency else "/kWh"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if not data:
            return None
        attrs = self.entity_description.attrs_fn(data) if self.entity_description.attrs_fn else {}
        if self.entity_description.key == "forecast_bill":
            attrs["card_data"] = data
        return attrs
