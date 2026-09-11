"""Midea local C3 device."""

import json
import logging
from enum import StrEnum
from typing import Any, ClassVar, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDevice, MideaDeviceInitKwargs

from .message import (
    C3DeviceMode,
    C3PoolDeviceMode,
    C3PoolPerfMode,
    C3SilentLevel,
    MessageC3Response,
    MessageQuery,
    MessageQueryBasic,
    MessageQueryDisinfect,
    MessageQueryECO,
    MessageQueryPoolExtended,
    MessageQueryPoolSerial,
    MessageQuerySilence,
    MessageQueryUnitPara,
    MessageSet,
    MessageSetDisinfect,
    MessageSetECO,
    MessageSetPool,
    MessageSetSilent,
    is_pool_subtype,
)

_LOGGER = logging.getLogger(__name__)

# The pool heat pump refuses the 0xA0 appliance query and answers only whole
# degree setpoints, so it uses a coarser step than the HVAC heat pump.
POOL_TEMPERATURE_STEP = 1.0
HVAC_TEMPERATURE_STEP = 0.5


class DeviceAttributes(StrEnum):
    """Midea C3 device attributes."""

    zone1_power = "zone1_power"
    zone2_power = "zone2_power"
    dhw_power = "dhw_power"
    zone1_curve = "zone1_curve"
    zone2_curve = "zone2_curve"
    disinfect = "disinfect"
    fast_dhw = "fast_dhw"
    zone_temp_type = "zone_temp_type"
    zone1_room_temp_mode = "zone1_room_temp_mode"
    zone2_room_temp_mode = "zone2_room_temp_mode"
    zone1_water_temp_mode = "zone1_water_temp_mode"
    zone2_water_temp_mode = "zone2_water_temp_mode"
    mode = "mode"
    mode_auto = "mode_auto"
    zone_target_temp = "zone_target_temp"
    dhw_target_temp = "dhw_target_temp"
    room_target_temp = "room_target_temp"
    zone_heating_temp_max = "zone_heating_temp_max"
    zone_heating_temp_min = "zone_heating_temp_min"
    zone_cooling_temp_max = "zone_cooling_temp_max"
    zone_cooling_temp_min = "zone_cooling_temp_min"
    tank_actual_temperature = "tank_actual_temperature"
    room_temp_max = "room_temp_max"
    room_temp_min = "room_temp_min"
    dhw_temp_max = "dhw_temp_max"
    dhw_temp_min = "dhw_temp_min"
    target_temperature = "target_temperature"
    temperature_max = "temperature_max"
    temperature_min = "temperature_min"
    status_heating = "status_heating"
    status_dhw = "status_dhw"
    status_tbh = "status_tbh"
    status_ibh = "status_ibh"
    total_energy_consumption = "total_energy_consumption"
    total_produced_energy = "total_produced_energy"
    outdoor_temperature = "outdoor_temperature"
    temp_tw_in = "temp_tw_in"
    temp_tw_out = "temp_tw_out"
    comp_run_freq = "comp_run_freq"
    unit_mode_run = "unit_mode_run"
    fan_speed = "fan_speed"
    temp_t1 = "temp_t1"
    temp_t2 = "temp_t2"
    temp_t2b = "temp_t2b"
    temp_t3 = "temp_t3"
    temp_tp = "temp_tp"
    temp_th = "temp_th"
    temp_tf = "temp_tf"
    pressure_high = "pressure_high"
    pressure_low = "pressure_low"
    odu_voltage = "odu_voltage"
    odu_comp_current = "odu_comp_current"
    odu_target_fre = "odu_target_fre"
    exv_current = "exv_current"
    fg_capacity_need = "fg_capacity_need"
    instant_power0 = "instant_power0"
    silent_mode = "silent_mode"
    silent_level = "silent_level"
    eco_mode = "eco_mode"
    tbh = "tbh"
    error_code = "error_code"
    error_code_display="error_code_display"
    error_description = "error_description"
    # Pool heat pump only (subtype 513). See pool_protocol_decoding.md.
    power = "power"
    boost_mode = "boost_mode"
    performance_mode = "performance_mode"
    compressor_running = "compressor_running"
    compressor_run_hours = "compressor_run_hours"
    water_flow = "water_flow"
    main_board_sw_version = "main_board_sw_version"
    controller_sw_version = "controller_sw_version"
    
    sn_code = "sn_code"
    # Still being decoded, exposed so they can be logged and reviewed.
    pool_unknown_basic_temp = "pool_unknown_basic_temp"
    pool_unknown_basic_22 = "pool_unknown_basic_22"
    pool_unknown_16_36_37 = "pool_unknown_16_36_37"
    pool_mode = "pool_mode"
    # Pool-specific temperature fields to avoid colliding with HVAC list types
    pool_target_temperature = "pool_target_temperature"
    pool_temperature_max = "pool_temperature_max"
    pool_temperature_min = "pool_temperature_min"
    


def pool_attributes() -> dict[DeviceAttributes, Any]:
    """Return the attribute set of a C3 pool heat pump.

    The pool heat pump shares almost nothing with the HVAC heat pump: no zones,
    no DHW, no curves. Giving it its own attribute set keeps the HVAC-only keys
    from showing up as permanently-None entries.
    """
    return {
        DeviceAttributes.power: False,
        DeviceAttributes.pool_mode: C3PoolDeviceMode.OFF,
        # Pool uses separate names to avoid colliding with HVAC per-zone list
        DeviceAttributes.pool_target_temperature: None,
        DeviceAttributes.pool_temperature_max: None,
        DeviceAttributes.pool_temperature_min: None,
        # "ambient" in the app; the T4 outdoor sensor.
        DeviceAttributes.outdoor_temperature: None,
        DeviceAttributes.temp_tw_in: None,
        DeviceAttributes.temp_tw_out: None,
        DeviceAttributes.silent_mode: False,
        DeviceAttributes.silent_level: C3SilentLevel.OFF.name,
        DeviceAttributes.boost_mode: False,
        DeviceAttributes.performance_mode: C3PoolPerfMode.IDLE.name,
        DeviceAttributes.compressor_running: False,
        DeviceAttributes.compressor_run_hours: None,
        DeviceAttributes.odu_comp_current: None,
        DeviceAttributes.odu_voltage: None,
        DeviceAttributes.water_flow: None,
        DeviceAttributes.main_board_sw_version: None,
        DeviceAttributes.controller_sw_version: None,
        # From body 0x0C, asked for once at connect time. This is the
        # appliance's own SN, not the Wi-Fi module serial that discovery
        # reports as MideaDevice.serial_number.
        DeviceAttributes.sn_code: None,
        DeviceAttributes.error_code: 0,
        DeviceAttributes.error_code_display: None,
        DeviceAttributes.error_description: None,
        
        
        DeviceAttributes.pool_unknown_basic_temp: None,
        DeviceAttributes.pool_unknown_basic_22: None,
        
        DeviceAttributes.pool_unknown_16_36_37: None,
        DeviceAttributes.pressure_high: None,
        DeviceAttributes.pressure_low: None,
        
        
        
    }


class MideaC3Device(MideaDevice):
    """Midea C3 device."""

    _silent_modes: ClassVar[list[str]] = [
        C3SilentLevel.OFF.name,
        C3SilentLevel.SILENT.name,
        C3SilentLevel.SUPER_SILENT.name,
    ]

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize Midea C3 device."""
        # Pool heat pumps share device type 0xC3 but use different body
        # layouts and a different feature set; the subtype is the only way to
        # tell them apart, so it has to be read before the attributes are built.
        self._is_pool = is_pool_subtype(kwargs["subtype"])
        attributes: dict[DeviceAttributes, Any] = {
            DeviceAttributes.zone1_power: False,
            DeviceAttributes.zone2_power: False,
            DeviceAttributes.dhw_power: False,
            DeviceAttributes.zone1_curve: False,
            DeviceAttributes.zone2_curve: False,
            DeviceAttributes.disinfect: False,
            DeviceAttributes.fast_dhw: False,
            DeviceAttributes.zone_temp_type: [False, False],
            DeviceAttributes.zone1_room_temp_mode: False,
            DeviceAttributes.zone2_room_temp_mode: False,
            DeviceAttributes.zone1_water_temp_mode: False,
            DeviceAttributes.zone2_water_temp_mode: False,
            DeviceAttributes.silent_mode: False,
            DeviceAttributes.silent_level: C3SilentLevel.OFF.name,
            DeviceAttributes.eco_mode: False,
            DeviceAttributes.tbh: False,
            DeviceAttributes.mode: 1,
            DeviceAttributes.mode_auto: 1,
            DeviceAttributes.zone_target_temp: [25.0, 25.0],
            DeviceAttributes.dhw_target_temp: 25.0,
            DeviceAttributes.room_target_temp: 30.0,
            DeviceAttributes.zone_heating_temp_max: [55.0, 55.0],
            DeviceAttributes.zone_heating_temp_min: [25.0, 25.0],
            DeviceAttributes.zone_cooling_temp_max: [25.0, 25.0],
            DeviceAttributes.zone_cooling_temp_min: [5.0, 5.0],
            DeviceAttributes.room_temp_max: 60.0,
            DeviceAttributes.room_temp_min: 34.0,
            DeviceAttributes.dhw_temp_max: 60.0,
            DeviceAttributes.dhw_temp_min: 20.0,
            DeviceAttributes.tank_actual_temperature: None,
            DeviceAttributes.target_temperature: [25.0, 25.0],
            DeviceAttributes.temperature_max: [0.0, 0.0],
            DeviceAttributes.temperature_min: [0.0, 0.0],
            DeviceAttributes.total_energy_consumption: None,
            DeviceAttributes.status_heating: None,
            DeviceAttributes.status_dhw: None,
            DeviceAttributes.status_tbh: None,
            DeviceAttributes.status_ibh: None,
            DeviceAttributes.total_produced_energy: None,
            DeviceAttributes.outdoor_temperature: None,
            DeviceAttributes.temp_tw_in: None,
            DeviceAttributes.temp_tw_out: None,
            DeviceAttributes.comp_run_freq: None,
            DeviceAttributes.unit_mode_run: None,
            DeviceAttributes.fan_speed: None,
            DeviceAttributes.temp_t1: None,
            DeviceAttributes.temp_t2: None,
            DeviceAttributes.temp_t2b: None,
            DeviceAttributes.temp_t3: None,
            DeviceAttributes.temp_tp: None,
            DeviceAttributes.temp_th: None,
            DeviceAttributes.temp_tf: None,
            DeviceAttributes.pressure_high: None,
            DeviceAttributes.pressure_low: None,
            DeviceAttributes.odu_voltage: None,
            DeviceAttributes.odu_comp_current: None,
            DeviceAttributes.odu_target_fre: None,
            DeviceAttributes.exv_current: None,
            DeviceAttributes.fg_capacity_need: None,
            DeviceAttributes.error_code: 0,
            DeviceAttributes.error_code_display: None,
            DeviceAttributes.error_description: None,
        }
        if self._is_pool:
            attributes = pool_attributes()
        super().__init__(
            device_type=DeviceType.C3,
            **kwargs,
            attributes=attributes,
        )
        self._default_temperature_step: float = (
            POOL_TEMPERATURE_STEP if self._is_pool else HVAC_TEMPERATURE_STEP
        )
        self._temperature_step: float = self._default_temperature_step
        if self._is_pool:
            # Pool heat pumps do not answer the standard 0xA0 appliance query,
            # and sending it stops the unit serving any further query on that
            # session, so skip stage 1 of refresh_status entirely. The message
            # protocol version normally comes from that reply and so stays 0
            # here, which is what the pool captures show on the wire.
            self._appliance_query = False
        # Armed until body 0x0C answers with the serial number.
        self._pool_serial_query = self._is_pool
        _LOGGER.debug(
            "[%s] C3 subtype %s, pool heat pump: %s",
            self.device_id,
            self._subtype,
            self._is_pool,
        )
        self.set_customize(customize)

    @property
    def temperature_step(self) -> float | None:
        """Midea C3 device temperature step."""
        return self._temperature_step

    @property
    def silent_modes(self) -> list[str]:
        """Midea C3 device silent modes."""
        return MideaC3Device._silent_modes

    def build_query(self) -> list[MessageQuery]:
        """Midea C3 device build query."""
        if self._is_pool:
            # Pool heat pumps serve only the 0x01 basic and 0x02 extended
            # status bodies; the HVAC-only disinfect/silence/ECO/unitpara
            # queries have no meaning for them.
            return [
                MessageQueryBasic(self._message_protocol_version),
                MessageQueryPoolExtended(self._message_protocol_version),
            ]
        return [
            MessageQueryBasic(self._message_protocol_version),
            MessageQueryDisinfect(self._message_protocol_version),
            MessageQuerySilence(self._message_protocol_version),
            MessageQueryECO(self._message_protocol_version),
            MessageQueryUnitPara(self._message_protocol_version),
        ]

    def build_init_query(self) -> list[MessageQuery]:
        """Midea C3 device build one-time queries.

        The pool heat pump's serial number (body 0x0C) never changes, so it is
        asked for once at connect time and the arming flag is cleared as soon
        as a reply is parsed.
        """
        if self._is_pool and self._pool_serial_query:
            return [MessageQueryPoolSerial(self._message_protocol_version)]
        return []

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Midea C3 device process message."""
        message = MessageC3Response(msg, subtype=self._subtype)
        _LOGGER.debug("[%s] Received: %s", self.device_id, message)
        new_status = {}
        for status in self._attributes:
            if hasattr(message, str(status)):
                self._attributes[status] = getattr(message, str(status))
                new_status[str(status)] = getattr(message, str(status))
        if new_status.get(DeviceAttributes.sn_code.value) is not None:
            # the reply arrived, so stop offering the query
            self._pool_serial_query = False
        if "zone_temp_type" in new_status:
            for zone in [0, 1]:
                if self._attributes[DeviceAttributes.zone_temp_type][
                    zone
                ]:  # Water temp mode
                    self._attributes[DeviceAttributes.target_temperature][zone] = (
                        self._attributes[DeviceAttributes.zone_target_temp][zone]
                    )
                    if (
                        self._attributes[DeviceAttributes.mode_auto]
                        == C3DeviceMode.COOL
                    ):  # cooling mode
                        self._attributes[DeviceAttributes.temperature_max][zone] = (
                            self._attributes[DeviceAttributes.zone_cooling_temp_max][
                                zone
                            ]
                        )
                        self._attributes[DeviceAttributes.temperature_min][zone] = (
                            self._attributes[DeviceAttributes.zone_cooling_temp_min][
                                zone
                            ]
                        )
                    elif (
                        self._attributes[DeviceAttributes.mode] == C3DeviceMode.HEAT
                    ):  # heating mode
                        self._attributes[DeviceAttributes.temperature_max][zone] = (
                            self._attributes[DeviceAttributes.zone_heating_temp_max][
                                zone
                            ]
                        )
                        self._attributes[DeviceAttributes.temperature_min][zone] = (
                            self._attributes[DeviceAttributes.zone_heating_temp_min][
                                zone
                            ]
                        )
                else:  # Room temp mode
                    self._attributes[DeviceAttributes.target_temperature][zone] = (
                        self._attributes[DeviceAttributes.room_target_temp]
                    )
                    self._attributes[DeviceAttributes.temperature_max][zone] = (
                        self._attributes[DeviceAttributes.room_temp_max]
                    )
                    self._attributes[DeviceAttributes.temperature_min][zone] = (
                        self._attributes[DeviceAttributes.room_temp_min]
                    )
            if self._attributes[DeviceAttributes.zone1_power]:
                if self._attributes[DeviceAttributes.zone_temp_type][zone]:
                    self._attributes[DeviceAttributes.zone1_water_temp_mode] = True
                    self._attributes[DeviceAttributes.zone1_room_temp_mode] = False
                else:
                    self._attributes[DeviceAttributes.zone1_water_temp_mode] = False
                    self._attributes[DeviceAttributes.zone1_room_temp_mode] = True
            else:
                self._attributes[DeviceAttributes.zone1_water_temp_mode] = False
                self._attributes[DeviceAttributes.zone1_room_temp_mode] = False
            if self._attributes[DeviceAttributes.zone2_power]:
                if self._attributes[DeviceAttributes.zone_temp_type][zone]:
                    self._attributes[DeviceAttributes.zone2_water_temp_mode] = True
                    self._attributes[DeviceAttributes.zone2_room_temp_mode] = False
                else:
                    self._attributes[DeviceAttributes.zone2_water_temp_mode] = False
                    self._attributes[DeviceAttributes.zone2_room_temp_mode] = True
            else:
                self._attributes[DeviceAttributes.zone2_water_temp_mode] = False
                self._attributes[DeviceAttributes.zone2_room_temp_mode] = False
            new_status[DeviceAttributes.zone1_water_temp_mode.value] = self._attributes[
                DeviceAttributes.zone1_water_temp_mode
            ]
            new_status[DeviceAttributes.zone2_water_temp_mode.value] = self._attributes[
                DeviceAttributes.zone2_water_temp_mode
            ]
            new_status[DeviceAttributes.zone1_room_temp_mode.value] = self._attributes[
                DeviceAttributes.zone1_room_temp_mode
            ]
            new_status[DeviceAttributes.zone2_room_temp_mode.value] = self._attributes[
                DeviceAttributes.zone2_room_temp_mode
            ]

        return new_status

    def make_message_set(self) -> MessageSet:
        """Midea C3 device make message set."""
        message = MessageSet(self._message_protocol_version)
        message.zone1_power = self._attributes[DeviceAttributes.zone1_power]
        message.zone2_power = self._attributes[DeviceAttributes.zone2_power]
        message.dhw_power = self._attributes[DeviceAttributes.dhw_power]
        message.mode = self._attributes[DeviceAttributes.mode]
        message.zone_target_temp = self._attributes[DeviceAttributes.zone_target_temp]
        message.dhw_target_temp = self._attributes[DeviceAttributes.dhw_target_temp]
        message.room_target_temp = self._attributes[DeviceAttributes.room_target_temp]
        message.zone1_curve = self._attributes[DeviceAttributes.zone1_curve]
        message.zone2_curve = self._attributes[DeviceAttributes.zone2_curve]
        message.tbh = self._attributes[DeviceAttributes.tbh]
        message.fast_dhw = self._attributes[DeviceAttributes.fast_dhw]
        return message

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Midea C3 device set attribute."""
        if self._is_pool:
            if attr in (
                DeviceAttributes.power,
                DeviceAttributes.pool_mode,
                DeviceAttributes.pool_target_temperature,
            ):
                message = MessageSetPool(self._message_protocol_version)
                message.power = bool(self._attributes[DeviceAttributes.power])
                message.pool_mode = C3PoolDeviceMode(
                    self._attributes[DeviceAttributes.pool_mode]
                )
                message.target_temperature = float(
                    self._attributes[DeviceAttributes.pool_target_temperature] or 0.0
                )
                if attr == DeviceAttributes.power:
                    message.power = bool(value)
                elif attr == DeviceAttributes.pool_mode:
                    message.pool_mode = C3PoolDeviceMode(value)
                    message.power = C3PoolDeviceMode(value) != C3PoolDeviceMode.OFF
                elif attr == DeviceAttributes.pool_target_temperature:
                    message.target_temperature = float(value)
                # perf_mode is left as None here, which builds the short
                # 7-byte body (power/mode/setpoint only). Do NOT set
                # perf_mode - the full 50-byte body path has a known bug
                # where it also touches boost/silent state unexpectedly.
                self.build_send(message)
            else:
                _LOGGER.warning(
                    "[%s] Pool heat pump does not support setting %s yet",
                    self.device_id,
                    attr,
                )
            return
        message: (
            MessageSet | MessageSetECO | MessageSetSilent | MessageSetDisinfect | None
        ) = None
        if attr in [
            DeviceAttributes.zone1_power,
            DeviceAttributes.zone2_power,
            DeviceAttributes.dhw_power,
            DeviceAttributes.zone1_curve,
            DeviceAttributes.zone2_curve,
            DeviceAttributes.tbh,
            DeviceAttributes.fast_dhw,
            DeviceAttributes.dhw_target_temp,
        ]:
            message = self.make_message_set()
            setattr(message, str(attr), value)
        elif attr == DeviceAttributes.eco_mode:
            message = MessageSetECO(self._message_protocol_version)
            setattr(message, str(attr), value)
        elif attr == DeviceAttributes.disinfect:
            message = MessageSetDisinfect(self._message_protocol_version)
            setattr(message, str(attr), value)
        elif attr in [
            DeviceAttributes.silent_mode.value,
            DeviceAttributes.silent_level.value,
        ]:
            if attr == DeviceAttributes.silent_mode.value and isinstance(value, bool):
                message = MessageSetSilent(self._message_protocol_version)
                message.silent_mode = bool(value)
                message.silent_level = (
                    C3SilentLevel.SILENT
                    if value
                    and self._attributes[DeviceAttributes.silent_level]
                    == C3SilentLevel.OFF.name
                    else C3SilentLevel[self._attributes[DeviceAttributes.silent_level]]
                )
            elif attr == DeviceAttributes.silent_level.value and isinstance(value, str):
                message = MessageSetSilent(self._message_protocol_version)
                message.silent_level = C3SilentLevel[value]
                message.silent_mode = value != C3SilentLevel.OFF.name
        if message is not None:
            self.build_send(message)

    def set_mode(self, zone: int, mode: int) -> None:
        """Midea C3 device set mode."""
        message = self.make_message_set()
        if zone == 0:
            message.zone1_power = True
        else:
            message.zone2_power = True
        message.mode = mode
        self.build_send(message)

    def set_target_temperature(
        self,
        target_temperature: float,
        mode: int | None,
        zone: int | None = None,
    ) -> None:
        """Midea C3 device set target temperature."""
        if zone is None:
            raise ValueError("[C3] Parameter `zone` must be set")

        message = self.make_message_set()
        if self._attributes[DeviceAttributes.zone_temp_type][zone]:
            message.zone_target_temp[zone] = target_temperature
        else:
            message.room_target_temp = target_temperature
        if mode is not None:
            if zone == 0:
                message.zone1_power = True
            else:
                message.zone2_power = True
            message.mode = mode
        self.build_send(message)

    def set_customize(self, customize: str) -> None:
        """Midea C3 device set customize."""
        self._temperature_step = self._default_temperature_step
        if customize and len(customize) > 0:
            try:
                params = json.loads(customize)
                if params and "temperature_step" in params:
                    temp_step = params.get("temperature_step")
                    if isinstance(temp_step, float | int):
                        self._temperature_step = float(temp_step)
                    else:
                        _LOGGER.error(
                            "[%s] Invalid type for temperature_step: %s",
                            self.device_id,
                            temp_step,
                        )
            except json.JSONDecodeError:
                _LOGGER.exception(
                    "[%s] JSON decode error in set_customize",
                    self.device_id,
                )
            self.update_all({"temperature_step": self._temperature_step})


class MideaAppliance(MideaC3Device):
    """Midea C3 appliance."""
