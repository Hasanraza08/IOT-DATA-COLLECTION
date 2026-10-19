"""SECTION 2 - The simulated IoT device (a Modbus TCP *server*).

A real motor drive or energy meter exposes its live measurements in Modbus
registers and waits for someone to ask for them. This script behaves the same
way: it replays the Kaggle dataset row by row, writing each row into the
registers, and answers any Modbus client that connects.

Run:  python src/device_simulator.py
"""
import asyncio
import logging

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

import config
from dataset import load_telemetry
from register_map import BLOCK_SIZE, BLOCK_START, encode

log = logging.getLogger("device")

# Modbus "function code" we write into. With SimDevice's shared memory the same
# registers answer both "read holding registers" (FC3) and "read input registers" (FC4).
FC_READ_INPUT_REGISTERS = 4


async def replay_dataset(server: ModbusTcpServer, data) -> None:
    """Every UPDATE_INTERVAL_S, load the next dataset row into the registers."""
    seq = 0
    rows = data.to_dict("records")
    log.info("Replaying %d samples every %.2fs (loops forever)", len(rows), config.UPDATE_INTERVAL_S)
    while True:
        for row in rows:
            seq = (seq + 1) % 2**32                      # UINT32 wraps around
            registers = encode({**row, "seq": seq})
            await server.async_setValues(config.MODBUS_UNIT_ID, FC_READ_INPUT_REGISTERS,
                                         BLOCK_START, registers)
            if seq % 20 == 0:
                log.info("seq=%d  U=%.1fV  I=%.1fA  P=%.0fW  T=%.1fC", seq, row["voltage_v"],
                         row["current_a"], row["power_w"], row["temperature_c"])
            await asyncio.sleep(config.UPDATE_INTERVAL_S)


async def main() -> None:
    data = load_telemetry(config.DATASET_PATH, config.DATASET_PROFILE_ID)

    # One device with unit id 1 and a block of 16-bit registers starting at 0.
    device = SimDevice(
        config.MODBUS_UNIT_ID,
        SimData(BLOCK_START, count=BLOCK_SIZE, values=0, datatype=DataType.REGISTERS),
    )
    server = ModbusTcpServer(device, address=("0.0.0.0", config.MODBUS_PORT))
    log.info("Modbus TCP device '%s' listening on port %d (unit id %d)",
             config.DEVICE_ID, config.MODBUS_PORT, config.MODBUS_UNIT_ID)

    feeder = asyncio.create_task(replay_dataset(server, data))
    try:
        await server.serve_forever()
    finally:
        feeder.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
