from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class CmccSensorDescription(SensorEntityDescription):
    value: Callable[[dict], object]
    attributes: Callable[[dict], dict] | None = None


MONEY = {
    "device_class": SensorDeviceClass.MONETARY,
    "native_unit_of_measurement": "CNY",
    "suggested_display_precision": 2,
}
FLOW = {
    "device_class": SensorDeviceClass.DATA_SIZE,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfInformation.MEGABYTES,
    "suggested_unit_of_measurement": UnitOfInformation.GIGABYTES,
    "suggested_display_precision": 2,
}


def _flow(key: str) -> Callable[[dict], object]:
    return lambda d: (d["flow"] or {}).get(key)


SENSORS = [
    CmccSensorDescription(key="balance", translation_key="balance", icon="mdi:wallet",
                          value=lambda d: d["balance"],
                          attributes=lambda d: {"as_of": d["fee_time"]}, **MONEY),
    CmccSensorDescription(key="consumed", translation_key="consumed", icon="mdi:cash-minus",
                          value=lambda d: d["consumed"], **MONEY),
    CmccSensorDescription(key="flow_remaining", translation_key="flow_remaining", icon="mdi:signal-cellular-3",
                          value=_flow("remain_mb"),
                          attributes=lambda d: {"packages": (d["flow"] or {}).get("items", [])}, **FLOW),
    CmccSensorDescription(key="flow_used", translation_key="flow_used", icon="mdi:chart-donut",
                          value=_flow("used_mb"), **FLOW),
    CmccSensorDescription(key="flow_total", translation_key="flow_total", icon="mdi:database",
                          value=_flow("total_mb"), **FLOW),
    CmccSensorDescription(key="points", translation_key="points", icon="mdi:star-circle",
                          state_class=SensorStateClass.MEASUREMENT, value=lambda d: d["points"]),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CmccSensor(coordinator, description) for description in SENSORS]
                       + [CmccUpdatedSensor(coordinator)])


class CmccEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        # Stable ids independent of the UI language, e.g. sensor.cmcc_1234_balance.
        self.entity_id = f"sensor.cmcc_{entry.unique_id[-4:]}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="中国移动",
            model="手机号码",
            entry_type=DeviceEntryType.SERVICE,
        )


class CmccSensor(CmccEntity, SensorEntity):
    entity_description: CmccSensorDescription

    def __init__(self, coordinator, description: CmccSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator.data)


class CmccUpdatedSensor(CmccEntity, SensorEntity):
    _attr_translation_key = "updated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "updated")
        self._updated = dt_util.utcnow()

    def _handle_coordinator_update(self) -> None:
        self._updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        return self._updated

    @property
    def extra_state_attributes(self):
        return {"errors": self.coordinator.data["errors"]} if self.coordinator.data["errors"] else None
