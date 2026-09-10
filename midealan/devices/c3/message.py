"""Midea local C3 message."""

from enum import IntEnum

from midealan.const import DeviceType
from midealan.message import (
    ListTypes,
    MessageBody,
    MessageRequest,
    MessageResponse,
    MessageType,
)

TEMP_NEG_VALUE = 127
# Outdoor fan speed is transmitted as RPM / 10.
FAN_SPEED_FACTOR = 10

# Subtypes that are pool heat pumps rather than the standard C3 HVAC heat
# pump. They share device type 0xC3 but use a completely different body
# layout, so the decoder must be told which variant it is looking at; the
# frames themselves carry nothing that distinguishes them.
POOL_SUBTYPES = frozenset({513})

# --- Pool heat pump body layout ---------------------------------------------
# All offsets below are documented in pool_protocol_decoding.md and are counted
# from the start of the body, i.e. index 0 is the body-type byte. The library
# strips the trailing checksum, so a 52 byte pool body arrives here as 51 bytes
# (indices 0..50) and the note's indices can be used unchanged.
#
# Both pool bodies transmit temperatures as `celsius + 35`.
POOL_TEMP_OFFSET = 35

# Body 0x01 - basic status.
POOL_BASIC_MIN_LENGTH = 23
POOL_BASIC_MODE = 2
POOL_BASIC_TARGET_TEMP = 3
POOL_BASIC_TEMP_MAX = 4
POOL_BASIC_TEMP_MIN = 5
# Same value (28C) in heat and cool, 50C in pump mode. Purpose unknown, exposed
# so it can be logged and reviewed.
POOL_BASIC_UNKNOWN_TEMP = 6
POOL_BASIC_ERROR_CODE = 15
POOL_BASIC_RUN_STATUS = 16
# Disproved as a temperature (read 222 during an E8 fault). Meaning unknown,
# exposed raw for logging.
POOL_BASIC_UNKNOWN_22 = 22
POOL_BASIC_COMP_RUN_HOURS = 47
# Bit 7 of the run-status byte is set while the compressor runs.
POOL_RUN_STATUS_COMPRESSOR = 0x80

# Body 0x02 - extended status.
POOL_EXT_MIN_LENGTH = 27
POOL_EXT_AMBIENT_TEMP = 22
POOL_EXT_TEMP_TW_IN = 25
POOL_EXT_TEMP_TW_OUT = 26
POOL_EXT_CURRENT_INPUT = 28
POOL_EXT_VOLTAGE = 30
POOL_EXT_MAIN_BOARD_SW = 34
POOL_EXT_CONTROLLER_SW = 40
POOL_EXT_SUPER_SILENT = 41
POOL_EXT_PERF_MODE = 42
# Matches the app's "Water flow: 1 m3/h"; still a candidate, the unit has only
# ever been observed at a single flow rate.
POOL_EXT_WATER_FLOW = 43

# Body 0x0C - the appliance serial number, 36 bytes: the body type, a flags
# byte, then printable ASCII, NUL terminated and NUL padded. Confirmed on
# hardware 2026-09-04: `0c 01 "W7841101449FA9020100005" 00...`.
#
# Unlike the HVAC X10 serial blocks this one is NOT dash-padded and is not
# located by scanning: it sits at a fixed offset in a body that carries
# nothing else, so it is simply sliced. (Scanning for padding is what the
# upstream C3 ASCII work had to abandon; a fixed slice cannot be thrown off
# by a neighbouring block being populated.)
POOL_SERIAL_DATA_OFFSET = 2
POOL_SERIAL_MAX_LENGTH = 32
POOL_SERIAL_MIN_LENGTH = POOL_SERIAL_DATA_OFFSET + 1


def parse_pool_serial(body: bytearray) -> str | None:
    """Decode the ASCII serial number carried by the pool 0x0C body.

    Returns None for a truncated body, an empty block, or anything that is
    not printable ASCII, rather than raising or returning partial text.
    """
    if len(body) < POOL_SERIAL_MIN_LENGTH:
        return None
    block = bytes(
        body[
            POOL_SERIAL_DATA_OFFSET : POOL_SERIAL_DATA_OFFSET + POOL_SERIAL_MAX_LENGTH
        ],
    )
    terminator = block.find(0)
    if terminator != -1:
        block = block[:terminator]
    candidate = block.strip()
    if not candidate:
        return None
    try:
        decoded = candidate.decode("ascii")
    except UnicodeDecodeError:
        return None
    return decoded if decoded.isprintable() else None


def is_pool_subtype(subtype: int | None) -> bool:
    """Return True if the subtype identifies a C3 pool heat pump."""
    return subtype in POOL_SUBTYPES


def pool_temperature(raw: int) -> float:
    """Decode a pool heat pump temperature byte to degrees celsius."""
    return float(raw - POOL_TEMP_OFFSET)


class C3PoolDeviceMode(IntEnum):
    """C3 pool heat pump mode, body 0x01 byte 2."""

    OFF = 0x00
    HEAT = 0x01
    COOL = 0x03
    PUMP = 0x04


class C3PoolPerfMode(IntEnum):
    """C3 pool heat pump performance level, body 0x02 byte 42.

    This is an enum of the *active* level, not a bitfield: silent and boost are
    mutually exclusive on this unit.
    """

    IDLE = 0x00
    SILENT = 0x01
    BOOST = 0x02
    NORMAL = 0x03







"""
Midea C3 pool heat pump — error number lookup.

Maps the "Error number in message" value to its (Error Code, Description).
Fault descriptions from the pool heat pump service manual, keyed by the
two-character code shown on the wired controller.

"""

ERROR_TABLE = {
    0:  ("",   "None"),
    2:  ("bA", "Ambient temp. sensor (T4) out of operation range"),
    3:  ("C7", "High temperature protection of inverter module"),
    4:  ("E0", "Water flow malfunction (after 3 times E8)"),
    5:  ("E2", "Communication malfunction between controller and main control board"),
    6:  ("E3", "Total outlet water temp. sensor (T1) malfunction"),
    7:  ("E5", "Air side heat exchanger temperature sensor (T3) malfunction"),
    8:  ("E6", "The ambient temperature sensor (T4) malfunction"),
    9:  ("E8", "Water flow malfunction"),
    10: ("E9", "Suction temperature sensor (Th) malfunction"),
    11: ("EA", "Discharge temperature sensor (Tp) malfunction"),
    12: ("Ed", "Inlet water temp. sensor (Tw_in) malfunction"),
    13: ("EE", "EEprom malfunction"),
    14: ("F1", "DC bus low voltage protection"),
    15: ("F6", "EXV1 fault"),
    16: ("H1", "Communication malfunction between main control board and inverter board"),
    17: ("H2", "Liquid refrigerant temp. sensor (T2) malfunction"),
    18: ("H3", "Gas refrigerant temp. sensor (T2B) malfunction"),
    19: ("H4", "Three times L0 protects"),
    20: ("H6", "The DC fan malfunction"),
    21: ("H7", "Voltage protection"),
    22: ("H8", "HP pressure sensor malfunction"),
    23: ("HA", "Outlet water temp. sensor (Tw_out) malfunction"),
    24: ("Hb", "Three times PP protection and Tw_out below 7 \u2103"),
    25: ("HF", "Inverter module board EEprom malfunction"),
    26: ("HH", "10 times H6 in 2 hours"),
    27: ("HP", "Low pressure protection in cooling mode"),
    28: ("P0", "Low pressure switch protection"),
    29: ("P1", "High pressure switch protection"),
    30: ("P3", "Compressor overcurrent protection"),
    31: ("P4", "Comp discharge temp. too high protection"),
    32: ("P5", "|Tw_out - Tw_in| value too big protection"),
    33: ("Pb", "Anti-freeze mode"),
    34: ("PP", "|Tw_out - Tw_in| abnormal protection"),
    35: ("Pd", "High temperature protection of air side heat exchanger temperature (T3)"),
    36: ("L0", "Inverter or compressor protection"),
    37: ("L1", "DC bus low voltage protection"),
    38: ("L2", "DC bus high voltage protection"),
    39: ("L3", "Current sampling error of PFC circuit"),
    40: ("L4", "Rotating stall protection"),
    41: ("L5", "Zero speed protection"),
    42: ("L7", "Phase loss protection of compressor"),
}


def pool_error_display_code(raw: int) -> str:
    """Return the display code for a raw pool error byte ("" when healthy)."""
    try:
        return ERROR_TABLE[raw][0]
    except KeyError:
        return f"?? (0x{raw:02X})"


def pool_error_description(raw: int) -> str:
    """Return the manual description for a raw pool error byte."""
    try:
        return ERROR_TABLE[raw][1]
    except KeyError:
        return f"Unknown error"





class C3SilentLevel(IntEnum):
    """C3 Silent Level."""

    OFF = 0x0
    SILENT = 0x1
    SUPER_SILENT = 0x3


class C3DeviceMode(IntEnum):
    """C3 Device Mode."""

    COOL = 2
    HEAT = 3


class MessageC3Base(MessageRequest):
    """C3 message base."""

    def __init__(
        self,
        protocol_version: int,
        message_type: MessageType,
        body_type: ListTypes,
    ) -> None:
        """Initialize C3 message base."""
        super().__init__(
            device_type=DeviceType.C3,
            protocol_version=protocol_version,
            message_type=message_type,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        raise NotImplementedError


class MessageQuery(MessageC3Base):
    """C3 message query."""

    def __init__(self, protocol_version: int, body_type: ListTypes) -> None:
        """Initialize C3 message query."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([])


class MessageQueryBasic(MessageQuery):
    """C3 Message query basic."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query basic."""
        super().__init__(protocol_version, ListTypes.X01)


class MessageQuerySilence(MessageQuery):
    """C3 Message query silence."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X05)


class MessageQueryECO(MessageQuery):
    """C3 Message query ECO."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X07)


class MessageQueryInstall(MessageQuery):
    """C3 Message query INSTALL."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X08)


class MessageQueryDisinfect(MessageQuery):
    """C3 Message query Disinfect."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X09)


class MessageQueryUnitPara(MessageQuery):
    """C3 Message query UNITPARA."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X10)


class MessageQueryHMIPara(MessageQuery):
    """C3 Message query HMIPARA."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query silence."""
        super().__init__(protocol_version, ListTypes.X0A)


class MessageQueryPoolExtended(MessageQuery):
    """C3 Message query pool extended status.

    Pool heat pumps answer a 0x02 body with the ambient/water temperatures,
    silent and boost state, current, voltage and SW versions. Their basic
    status uses body 0x01, so MessageQueryBasic is reused for that.
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query pool extended status."""
        super().__init__(protocol_version, ListTypes.X02)


class MessageQueryPoolSerial(MessageQuery):
    """C3 Message query pool serial number.

    Body 0x0C answers with the appliance serial as ASCII. It never changes,
    so the device asks for it once at connect time (build_init_query) rather
    than on every refresh.
    """

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message query pool serial number."""
        super().__init__(protocol_version, ListTypes.X0C)


class MessageSet(MessageC3Base):
    """C3 message set."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )
        self.zone1_power = False
        self.zone2_power = False
        self.dhw_power = False
        self.mode = 0
        self.zone_target_temp = [25.0, 25.0]
        self.dhw_target_temp = 40.0
        self.room_target_temp = 25.0
        self.zone1_curve = False
        self.zone2_curve = False
        self.fast_dhw = False
        self.tbh = False

    @property
    def _body(self) -> bytearray:
        # Byte 1
        zone1_power = 0x01 if self.zone1_power else 0x00
        zone2_power = 0x02 if self.zone2_power else 0x00
        dhw_power = 0x04 if self.dhw_power else 0x00
        # Byte 7
        zone1_curve = 0x01 if self.zone1_curve else 0x00
        zone2_curve = 0x02 if self.zone2_curve else 0x00
        tbh = 0x04 if self.tbh else 0x00
        fast_dhw = 0x08 if self.fast_dhw else 0x00
        room_target_temp = int(self.room_target_temp * 2)
        zone1_target_temp = int(self.zone_target_temp[0])
        zone2_target_temp = int(self.zone_target_temp[1])
        dhw_target_temp = int(self.dhw_target_temp)
        return bytearray(
            [
                zone1_power | zone2_power | dhw_power,
                self.mode,
                zone1_target_temp,
                zone2_target_temp,
                dhw_target_temp,
                room_target_temp,
                zone1_curve | zone2_curve | tbh | fast_dhw,
            ],
        )


class MessageSetSilent(MessageC3Base):
    """C3 message set silent."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set silent."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X05,
        )
        self.silent_mode = False
        self.silent_level = C3SilentLevel.OFF

    @property
    def _body(self) -> bytearray:
        return bytearray(
            [
                self.silent_level if self.silent_mode else C3SilentLevel.OFF,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ],
        )


class MessageSetECO(MessageC3Base):
    """C3 message set eco."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set eco."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X07,
        )
        self.eco_mode = False

    @property
    def _body(self) -> bytearray:
        eco_mode = 0x01 if self.eco_mode else 0

        return bytearray([eco_mode, 0x00, 0x00, 0x00, 0x00, 0x00])


class MessageSetDisinfect(MessageC3Base):
    """C3 message set Disinfect."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize C3 message set eco."""
        super().__init__(
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X09,
        )
        self.disinfect = False

    @property
    def _body(self) -> bytearray:
        disinfect = 0x01 if self.disinfect else 0

        return bytearray([disinfect, 0x00, 0x00, 0x00])


class C3BasicBody(MessageBody):
    """C3 Basic message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 message body."""
        super().__init__(body)
        # BodyBytes 1
        self.zone1_power = body[data_offset + 0] & 0x01 > 0
        self.zone2_power = body[data_offset + 0] & 0x02 > 0
        self.dhw_power = body[data_offset + 0] & 0x04 > 0
        self.zone1_curve = body[data_offset + 0] & 0x08 > 0
        self.zone2_curve = body[data_offset + 0] & 0x10 > 0
        self.tbh = body[data_offset + 0] & 0x20 > 0
        self.fast_dhw = body[data_offset + 0] & 0x40 > 0
        self.remote_onoff = body[data_offset + 0] & 0x80 > 0
        # BodyBytes 2
        self.heat = body[data_offset + 1] & 0x01 > 0
        self.cool = body[data_offset + 1] & 0x02 > 0
        self.dhw = body[data_offset + 1] & 0x04 > 0
        self.double_zone = body[data_offset + 1] & 0x08 > 0
        self.zone_temp_type = [
            body[data_offset + 1] & 0x10 > 0,
            body[data_offset + 1] & 0x20 > 0,
        ]
        self.room_thermal_support = body[data_offset + 1] & 0x40 > 0
        self.room_thermal_state = body[data_offset + 1] & 0x80 > 0
        # BodyBytes 3
        self.time_set = body[data_offset + 2] & 0x01 > 0
        self.silent_mode = body[data_offset + 2] & 0x02 > 0
        self.holiday_on = body[data_offset + 2] & 0x04 > 0
        self.eco_mode = body[data_offset + 2] & 0x08 > 0
        self.zone_terminal_type = body[data_offset + 2]
        # BodyBytes 4
        self.mode = body[data_offset + 3]
        self.mode_auto = body[data_offset + 4]
        # zone1, zone2
        self.zone_target_temp = [
            float(body[data_offset + 5]),
            float(body[data_offset + 6]),
        ]
        self.dhw_target_temp = float(body[data_offset + 7])
        self.room_target_temp = float(body[data_offset + 8] / 2)
        # zone1, zone2
        self.zone_heating_temp_max = [
            float(body[data_offset + 9]),
            float(body[data_offset + 13]),
        ]
        self.zone_heating_temp_min = [
            float(body[data_offset + 10]),
            float(body[data_offset + 14]),
        ]
        self.zone_cooling_temp_max = [
            float(body[data_offset + 11]),
            float(body[data_offset + 15]),
        ]
        self.zone_cooling_temp_min = [
            float(body[data_offset + 12]),
            float(body[data_offset + 16]),
        ]
        self.room_temp_max = float(body[data_offset + 17] / 2)
        self.room_temp_min = float(body[data_offset + 18] / 2)
        self.dhw_temp_max = float(body[data_offset + 19])
        self.dhw_temp_min = float(body[data_offset + 20])
        self.tank_actual_temperature = float(body[data_offset + 21])
        self.error_code = body[data_offset + 22]
        self.tbh_control = body[data_offset + 23] & 0x80 > 0
        self.SysEnergyAnaEN = body[data_offset + 23] & 0x20 > 0
        self.HMIEnergyAnaSetEN = body[data_offset + 23] & 0x40 > 0


class C3EnergyBody(MessageBody):
    """C3 Energy MSG_TYPE_UP_POWER4 message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 notify1 message body."""
        super().__init__(body)
        status_byte = body[data_offset]
        # bit0
        self.status_heating = (status_byte & 0x01) > 0
        # bit1
        self.status_cool = (status_byte & 0x02) > 0
        # bit2
        self.status_dhw = (status_byte & 0x04) > 0
        # bit3
        self.status_tbh = (status_byte & 0x08) > 0
        # bit4
        self.status_ibh = (status_byte & 0x10) > 0
        # 32 bit big-endian counters: the lua multiplies the top byte by
        # 16777216 (<< 24), not 4294967296.
        # total_energy_consumption
        self.total_energy_consumption = (
            (body[data_offset + 1] << 24)
            + (body[data_offset + 2] << 16)
            + (body[data_offset + 3] << 8)
            + (body[data_offset + 4])
        )
        # total_produced_energy
        self.total_produced_energy = (
            (body[data_offset + 5] << 24)
            + (body[data_offset + 6] << 16)
            + (body[data_offset + 7] << 8)
            + (body[data_offset + 8])
        )
        base_value = body[data_offset + 9]
        self.outdoor_temperature = float(
            (base_value - 256) if base_value > TEMP_NEG_VALUE else base_value,
        )  # outdoor_temperature is t4
        self.zone1_temp_set = float(body[data_offset + 10])
        self.zone2_temp_set = float(body[data_offset + 11])
        self.t5s = body[data_offset + 12]
        self.tas = body[data_offset + 13]


class C3SilenceBody(MessageBody):
    """C3 Silence message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 query silence message body."""
        super().__init__(body)
        self.silent_mode = body[data_offset] & 0x1 > 0
        self.silent_level = C3SilentLevel(
            (body[data_offset] & 0x1) + ((body[data_offset] & 0x8) >> 2)
            if self.silent_mode
            else C3SilentLevel.OFF.value,
        ).name
        # Message protocol information:
        # silence_function_state: Byte 1, BIT 0
        # silence_timer1_state: Byte 1, BIT 1
        # silence_timer2_state: Byte 1, BIT 2
        # silence_function_level: Byte 1, BIT 3
        # silence_timer1_starthour: Byte 2
        # silence_timer1_startmin: Byte 3
        # silence_timer1_endhour: Byte 4
        # silence_timer1_endmin: Byte 5
        # silence_timer2_starthour: Byte 6
        # silence_timer2_startmin: Byte 7
        # silence_timer2_endhour: Byte 8
        # silence_timer2_endmin: Byte 9


class C3ECOBody(MessageBody):
    """C3 ECO message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 ECO message body."""
        super().__init__(body)
        self.eco_function_state = body[data_offset] & 0x01 > 0
        self.eco_timer_state = body[data_offset] & 0x02 > 0


class C3DisinfectBody(MessageBody):
    """C3 Disinfect message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 Disinfect message body."""
        super().__init__(body)
        self.disinfect = body[data_offset] & 0x01 > 0
        self.disinfect_run = body[data_offset] & 0x02 > 0
        self.disinfect_set_weekday = body[data_offset + 1]
        self.disinfect_start_hour = body[data_offset + 2]
        self.disinfect_start_minutes = body[data_offset + 3]


class C3UnitParaBody(MessageBody):
    """C3 UnitPara message body."""

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 UnitPara message body."""
        super().__init__(body)
        self.comp_run_freq = body[data_offset]
        self.unit_mode_run = body[data_offset + 1]
        # Outdoor fan speed, transmitted as RPM / 10 in a single byte.
        # It lives at data_offset + 2, directly after unit_mode_run; the
        # previous data_offset + 3 read a neighbouring byte that is small and
        # nearly constant while the unit runs, so fan_speed was reported as a
        # fixed low value (typically 20) regardless of the real fan command.
        self.fan_speed = body[data_offset + 2] * FAN_SPEED_FACTOR
        # lua _bodyBytes[5]; data_offset + 5 is the disabled `tempset` byte.
        self.fg_capacity_need = body[data_offset + 4]
        self.temp_t3 = body[data_offset + 6]
        self.temp_t4 = body[data_offset + 7]
        self.temp_tp = body[data_offset + 8]
        self.temp_tw_in = body[data_offset + 9]
        self.temp_tw_out = body[data_offset + 10]
        self.temp_tsolar = body[data_offset + 11]
        self.hydbox_subtype = body[data_offset + 12]
        self.fg_usb_info_connect = body[data_offset + 13]
        # self.usb_index_max  body[data_offset + 14]
        # lua _bodyBytes[17], compressor current in A. Already decoded by
        # C3UnitParaUpBody; enabled here so the polled response carries it too.
        self.odu_comp_current = body[data_offset + 16]
        self.odu_voltage = body[data_offset + 17] * 256 + body[data_offset + 18]
        self.exv_current = body[data_offset + 19] * 256 + body[data_offset + 20]
        self.odu_model = body[data_offset + 21]
        # self.unit_online_num  body[data_offset + 22]
        # self.current_code  body[data_offset + 23]
        self.temp_t1 = body[data_offset + 33]
        self.temp_tw2 = body[data_offset + 34]
        self.temp_t2 = body[data_offset + 35]
        self.temp_t2b = body[data_offset + 36]
        self.temp_t5 = body[data_offset + 37]
        self.temp_ta = body[data_offset + 38]
        self.temp_tb_t1 = body[data_offset + 39]
        self.temp_tb_t2 = body[data_offset + 40]
        self.hydrobox_capacity = body[data_offset + 41]
        self.pressure_high = body[data_offset + 42] * 256 + body[data_offset + 43]
        self.pressure_low = body[data_offset + 44] * 256 + body[data_offset + 45]
        self.temp_th = body[data_offset + 46]
        self.machine_type = body[data_offset + 47]
        self.odu_target_fre = body[data_offset + 48]
        self.dc_current = body[data_offset + 49]
        self.temp_tf = body[data_offset + 51]
        self.idu_t1s1 = body[data_offset + 52]
        self.idu_t1s2 = body[data_offset + 53]
        self.water_flower = body[data_offset + 54] * 256 + body[data_offset + 55]
        self.odu_plan_vol_lmt = body[data_offset + 56]
        # lua _bodyBytes[58] * 256 + _bodyBytes[59]; the low byte was dropped.
        self.current_unit_capacity = (
            body[data_offset + 57] * 256 + body[data_offset + 58]
        )
        self.sphera_ahs_voltage = body[data_offset + 59]
        self.temp_t4a_ver = body[data_offset + 60]
        self.water_pressure = body[data_offset + 61] * 256 + body[data_offset + 62]
        self.room_rel_hum = body[data_offset + 63]
        # lua _bodyBytes[65]; data_offset + 63 duplicated room_rel_hum.
        # On a 171H120F this byte reads 0 while the MSG_TYPE_UP_UNITPARA
        # notify reports pwmPumpOut = 99, so this firmware appears not to
        # populate it in the query response. _bodyBytes[66], which happens
        # to hold a constant 99, is marked reserved by the lua and is not
        # used here.
        self.pwm_pump_out = body[data_offset + 64]
        self.total_electricity0 = (
            (body[data_offset + 66] << 24)
            + (body[data_offset + 67] << 16)
            + (body[data_offset + 68] << 8)
            + (body[data_offset + 69])
        )
        self.total_thermal0 = (
            (body[data_offset + 70] << 24)
            + (body[data_offset + 71] << 16)
            + (body[data_offset + 72] << 8)
            + (body[data_offset + 73])
        )
        self.heat_elec_total_consum0 = (
            (body[data_offset + 74] << 24)
            + (body[data_offset + 75] << 16)
            + (body[data_offset + 76] << 8)
            + (body[data_offset + 77])
        )
        self.heat_elec_total_capacity0 = (
            (body[data_offset + 78] << 24)
            + (body[data_offset + 79] << 16)
            + (body[data_offset + 80] << 8)
            + (body[data_offset + 81])
        )
        self.instant_power0 = (body[data_offset + 82] << 8) + (body[data_offset + 83])
        self.instant_renew_power0 = (body[data_offset + 84] << 8) + (
            body[data_offset + 85]
        )
        # lua _bodyBytes[87..90] as a 32 bit value; data_offset + 84,85
        # duplicated instant_renew_power0. Read defensively: the lua frame runs
        # to _bodyBytes[191] but this parser previously stopped at
        # data_offset + 85, so shorter bodies must not raise.
        self.total_renew_power0 = (
            (self.read_byte(body, data_offset + 86) << 24)
            + (self.read_byte(body, data_offset + 87) << 16)
            + (self.read_byte(body, data_offset + 88) << 8)
            + self.read_byte(body, data_offset + 89)
        )


class C3UnitParaUpBody(MessageBody):
    """C3 UnitPara notify (MSG_TYPE_UP_UNITPARA) message body.

    The unit pushes this unsolicited between polls. It carries the same
    quantities as the X10 query response but in its own, shorter layout, so
    the attribute names deliberately match C3UnitParaBody: whichever message
    arrives last refreshes the same device attributes.

    Layout from the official C3 lua for the 171H120F module,
    MSG_TYPE_UP_UNITPARA block. The lua is 1-indexed, so _bodyBytes[N] is
    body[data_offset + N - 1].

    Only the fields C3UnitParaBody already exposes are decoded here. The lua
    block continues with a long Sys* energy-analysis section that reuses the
    same byte ranges for several different names, so it is not parsed.
    """

    def __init__(self, body: bytearray, data_offset: int = 0) -> None:
        """Initialize C3 UnitPara notify message body."""
        super().__init__(body)
        self.comp_run_freq = body[data_offset]
        self.fan_speed = body[data_offset + 1] * FAN_SPEED_FACTOR
        self.temp_t3 = body[data_offset + 2]
        self.temp_t4 = body[data_offset + 3]
        self.temp_tp = body[data_offset + 4]
        self.temp_tw_in = body[data_offset + 5]
        self.temp_tw_out = body[data_offset + 6]
        self.odu_comp_current = body[data_offset + 7]
        self.odu_voltage = body[data_offset + 8] * 256 + body[data_offset + 9]
        self.temp_t1 = body[data_offset + 10]
        self.temp_tw2 = body[data_offset + 11]
        self.temp_t2 = body[data_offset + 12]
        self.temp_t2b = body[data_offset + 13]
        self.temp_t5 = body[data_offset + 14]
        self.temp_ta = body[data_offset + 15]
        self.pressure_high = body[data_offset + 16] * 256 + body[data_offset + 17]
        self.pressure_low = body[data_offset + 18] * 256 + body[data_offset + 19]
        self.temp_th = body[data_offset + 20]
        self.odu_target_fre = body[data_offset + 21]
        self.temp_tf = body[data_offset + 22]
        self.idu_t1s1 = body[data_offset + 23]
        self.idu_t1s2 = body[data_offset + 24]
        self.water_flower = body[data_offset + 25] * 256 + body[data_offset + 26]
        self.current_unit_capacity = (
            body[data_offset + 27] * 256 + body[data_offset + 28]
        )
        self.water_pressure = body[data_offset + 29] * 256 + body[data_offset + 30]
        self.room_rel_hum = body[data_offset + 31]
        self.total_electricity0 = (
            (body[data_offset + 32] << 24)
            + (body[data_offset + 33] << 16)
            + (body[data_offset + 34] << 8)
            + (body[data_offset + 35])
        )
        self.total_thermal0 = (
            (body[data_offset + 36] << 24)
            + (body[data_offset + 37] << 16)
            + (body[data_offset + 38] << 8)
            + (body[data_offset + 39])
        )
        # NOTE: _bodyBytes[41..48] are given two conflicting meanings by the
        # lua (heatElecTotConsum0 / heatTotCapacity0 overlap SysHeatDay*), and
        # on a real unit heatElecTotConsum0 reads 0 here while the X10 query
        # reports 2249 at the same moment. Not decoded.
        self.instant_power0 = (body[data_offset + 48] << 8) + (body[data_offset + 49])
        self.instant_renew_power0 = (body[data_offset + 50] << 8) + (
            body[data_offset + 51]
        )
        self.total_renew_power0 = (
            (body[data_offset + 52] << 24)
            + (body[data_offset + 53] << 16)
            + (body[data_offset + 54] << 8)
            + (body[data_offset + 55])
        )
        self.unit_mode_run = body[data_offset + 59]


class C3PoolBasicBody(MessageBody):
    """C3 pool heat pump basic status body (body type 0x01).

    Layout documented in pool_protocol_decoding.md. It shares nothing with the
    standard C3 basic body beyond the body type, hence a separate class.
    """

    def __init__(self, body: bytearray) -> None:
        """Initialize C3 pool basic message body."""
        super().__init__(body)
        raw_mode = body[POOL_BASIC_MODE]
        self.power = raw_mode != C3PoolDeviceMode.OFF
        self.mode = raw_mode
        # The unit keeps a separate setpoint and separate limits per mode, and
        # bytes 3..5 always describe the currently selected mode.
        self.target_temperature = pool_temperature(body[POOL_BASIC_TARGET_TEMP])
        self.temperature_max = pool_temperature(body[POOL_BASIC_TEMP_MAX])
        self.temperature_min = pool_temperature(body[POOL_BASIC_TEMP_MIN])
        self.pool_unknown_basic_temp = pool_temperature(body[POOL_BASIC_UNKNOWN_TEMP])
        self.error_code = body[POOL_BASIC_ERROR_CODE]
        self.error_code_display = pool_error_display_code(self.error_code)
        self.error_description = pool_error_description(self.error_code)
        
        
        body[POOL_BASIC_ERROR_CODE]
        
        
        self.compressor_running = (
            body[POOL_BASIC_RUN_STATUS] & POOL_RUN_STATUS_COMPRESSOR > 0
        )
        self.pool_unknown_basic_22 = body[POOL_BASIC_UNKNOWN_22]
        
        self.pool_unknown_16_36_37 = body[36] << 8 | body[37]
        self.instant_power0 = body[38] << 8 | body[39]
        self.pool_unknown_16_40_41 = body[40] << 8 | body[41]

        
        
        
        # Cumulative hours; read defensively so a short body cannot raise.
        self.compressor_run_hours = self.read_byte(body, POOL_BASIC_COMP_RUN_HOURS)


class C3PoolExtendedBody(MessageBody):
    """C3 pool heat pump extended status body (body type 0x02).

    Carries every temperature sensor the app shows, the electrical readings and
    the performance level. Read only - the unit never answers a SET on 0x02.
    """

    def __init__(self, body: bytearray) -> None:
        """Initialize C3 pool extended message body."""
        super().__init__(body)
        # The app labels this "ambient"; it is the T4 outdoor sensor.
        self.outdoor_temperature = pool_temperature(body[POOL_EXT_AMBIENT_TEMP])
        self.temp_tw_in = pool_temperature(body[POOL_EXT_TEMP_TW_IN])
        self.temp_tw_out = pool_temperature(body[POOL_EXT_TEMP_TW_OUT])
        self.odu_comp_current = self.read_byte(body, POOL_EXT_CURRENT_INPUT)
        self.odu_voltage = self.read_byte(body, POOL_EXT_VOLTAGE)
        self.main_board_sw_version = self.read_byte(body, POOL_EXT_MAIN_BOARD_SW)
        self.controller_sw_version = self.read_byte(body, POOL_EXT_CONTROLLER_SW)
        self.water_flow = self.read_byte(body, POOL_EXT_WATER_FLOW)
        super_silent = self.read_byte(body, POOL_EXT_SUPER_SILENT) > 0
        raw_perf = self.read_byte(body, POOL_EXT_PERF_MODE)
        try:
            perf_mode = C3PoolPerfMode(raw_perf)
        except ValueError:
            # Keep unmapped levels visible rather than silently reporting idle.
            self.performance_mode = f"unknown_{raw_perf:#04x}"
            perf_mode = None
        else:
            self.performance_mode = perf_mode.name
        self.silent_mode = perf_mode == C3PoolPerfMode.SILENT
        self.boost_mode = perf_mode == C3PoolPerfMode.BOOST
        if not self.silent_mode:
            silent_level = C3SilentLevel.OFF
        elif super_silent:
            silent_level = C3SilentLevel.SUPER_SILENT
        else:
            silent_level = C3SilentLevel.SILENT
        self.silent_level = silent_level.name


class C3PoolSerialBody(MessageBody):
    """C3 pool heat pump serial number body (body type 0x0C).

    Deliberately NOT called ``serial_number``: ``MideaDevice.serial_number``
    already holds the 32 character Wi-Fi module serial that UDP discovery
    reports (``0000C331`` + module id + suffix). This is a different, shorter
    identifier that only the appliance itself reports, so it gets the
    ``sn_code`` name used elsewhere in the C3 for on-the-wire SN blocks.
    """

    def __init__(self, body: bytearray) -> None:
        """Initialize C3 pool serial number message body."""
        super().__init__(body)
        self.sn_code = parse_pool_serial(body)


class MessageC3Response(MessageResponse):
    """C3 message response."""

    def __init__(self, message: bytes, subtype: int = 0) -> None:
        """Initialize C3 message response.

        ``subtype`` selects the body layout. Pool heat pumps share device type
        0xC3 with the standard HVAC heat pump but lay their bodies out
        differently, and the frames carry nothing that tells them apart, so the
        device passes its subtype in (same approach as the FA MessageSet). The
        raw subtype is kept rather than a pre-computed bool so future pool
        firmwares can be distinguished here. Defaults to 0, the standard HVAC
        behaviour, for existing callers.
        """
        super().__init__(bytearray(message))
        self._subtype = subtype
        self._pool = is_pool_subtype(subtype)
        if self._pool:
            self._set_pool_body()
        elif (
            self.message_type
            in [MessageType.set, MessageType.notify1, MessageType.query]
            and self.body_type == ListTypes.X01
        ) or self.message_type == MessageType.notify2:
            self.set_body(C3BasicBody(super().body, data_offset=1))
        elif (
            self.message_type == MessageType.notify1 and self.body_type == ListTypes.X04
        ):
            self.set_body(C3EnergyBody(super().body, data_offset=1))
        elif self.message_type == MessageType.query and self.body_type == ListTypes.X05:
            self.set_body(C3SilenceBody(super().body, data_offset=1))
        elif (
            self.message_type == MessageType.notify1 and self.body_type == ListTypes.X05
        ):
            self.set_body(C3UnitParaUpBody(super().body, data_offset=1))
        elif self.body_type == ListTypes.X07:
            self.set_body(C3ECOBody(super().body, data_offset=1))
        elif self.body_type == ListTypes.X09:
            self.set_body(C3DisinfectBody(super().body, data_offset=1))
        elif self.body_type == ListTypes.X10:
            self.set_body(C3UnitParaBody(super().body, data_offset=1))
        self.set_attr()

    def _set_pool_body(self) -> None:
        """Decode a pool heat pump body.

        Pool bodies are selected by body type alone: the query response, the
        set echo and the notify that follows a set all carry the same layout.
        Anything else is left as the raw generic body.
        """
        body = super().body
        if self.body_type == ListTypes.X01 and len(body) >= POOL_BASIC_MIN_LENGTH:
            self.set_body(C3PoolBasicBody(body))
        elif self.body_type == ListTypes.X02 and len(body) >= POOL_EXT_MIN_LENGTH:
            self.set_body(C3PoolExtendedBody(body))
        elif self.body_type == ListTypes.X0C:
            self.set_body(C3PoolSerialBody(body))
