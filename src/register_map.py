"""Modbus register map: which value lives at which register address.

In real life this table comes from the device manufacturer's manual. Both the
device (simulator) and the gateway import THIS file, so they always agree.

Modbus registers are only 16 bits wide. A decimal number like 231.7 V needs a
32-bit float, so each float occupies TWO consecutive registers
("big-endian word order": high word first, the most common convention).
"""
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient

DT = ModbusTcpClient.DATATYPE          # FLOAT32, UINT32, UINT16, ...


@dataclass(frozen=True)
class Register:
    name: str        # key used in the MQTT JSON and DB column name
    address: int     # first register (0-based)
    datatype: DT
    unit: str
    description: str

    @property
    def size(self) -> int:              # how many 16-bit registers it needs
        return self.datatype.value[1]


REGISTERS: list[Register] = [
    Register("voltage_v",       0, DT.FLOAT32, "V",    "Stator voltage magnitude"),
    Register("current_a",       2, DT.FLOAT32, "A",    "Stator current magnitude"),
    Register("power_w",         4, DT.FLOAT32, "W",    "Electrical active power"),
    Register("temperature_c",   6, DT.FLOAT32, "degC", "Stator winding temperature"),
    Register("ambient_temp_c",  8, DT.FLOAT32, "degC", "Ambient temperature"),
    Register("coolant_temp_c", 10, DT.FLOAT32, "degC", "Coolant temperature"),
    Register("motor_speed_rpm", 12, DT.FLOAT32, "rpm", "Rotor speed"),
    Register("torque_nm",      14, DT.FLOAT32, "Nm",   "Torque"),
    Register("seq",            16, DT.UINT32,  "",     "Sample counter (increments every update)"),
    Register("profile_id",     18, DT.UINT16,  "",     "Measurement session id in the dataset"),
]

BLOCK_START = 0
BLOCK_SIZE = max(r.address + r.size for r in REGISTERS)   # 19 registers -> one read request
FLOAT_FIELDS = [r.name for r in REGISTERS if r.datatype == DT.FLOAT32]


def encode(values: dict) -> list[int]:
    """Device side: turn {'voltage_v': 231.7, ...} into a list of 16-bit registers."""
    regs = [0] * BLOCK_SIZE
    for r in REGISTERS:
        value = values[r.name]
        if r.datatype != DT.FLOAT32:
            value = int(value)
        words = ModbusTcpClient.convert_to_registers(value, r.datatype, word_order="big")
        regs[r.address - BLOCK_START : r.address - BLOCK_START + r.size] = words
    return regs


def decode(regs: list[int]) -> dict:
    """Gateway side: turn the raw registers back into named values."""
    out = {}
    for r in REGISTERS:
        words = regs[r.address - BLOCK_START : r.address - BLOCK_START + r.size]
        value = ModbusTcpClient.convert_from_registers(words, r.datatype, word_order="big")
        out[r.name] = round(value, 4) if r.datatype == DT.FLOAT32 else int(value)
    return out
