"""SECTION 3 - The edge gateway: Modbus in, MQTT out.

Factories put a small computer (the "edge gateway") next to their machines.
It does three jobs, and so does this script:

  1. POLL   - ask the device for its registers over Modbus TCP
  2. DECODE - turn raw 16-bit registers into named values using the register map
  3. PUBLISH- send the values as JSON to the MQTT broker

Run:  python src/gateway.py
"""
import json
import logging
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

import config
from register_map import BLOCK_SIZE, BLOCK_START, decode

log = logging.getLogger("gateway")


def make_mqtt_client() -> mqtt.Client:
    topic_status = config.status_topic(config.DEVICE_ID)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"gateway-{config.DEVICE_ID}")

    # "Last Will": if the gateway dies without saying goodbye, the BROKER
    # publishes "offline" for us, so everyone knows the data stopped.
    client.will_set(topic_status, "offline", qos=1, retain=True)

    # Keep up to 10k messages in memory while the broker is unreachable.
    client.max_queued_messages_set(10_000)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(c, _userdata, _flags, reason_code, _props):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("Connected to MQTT broker %s:%d", config.MQTT_HOST, config.MQTT_PORT)
        # retain=True: a client that subscribes later immediately gets the last status
        c.publish(topic_status, "online", qos=1, retain=True)

    def on_disconnect(_c, _userdata, _flags, reason_code, _props):
        log.warning("Disconnected from MQTT broker (%s) - will retry", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    client.loop_start()          # background thread handles network + reconnects
    return client


def poll_device(modbus: ModbusTcpClient) -> dict | None:
    """Read the whole register block in ONE request and decode it."""
    if not modbus.connected and not modbus.connect():
        log.warning("Device %s:%d not reachable", config.MODBUS_HOST, config.MODBUS_PORT)
        return None
    try:
        resp = modbus.read_input_registers(BLOCK_START, count=BLOCK_SIZE,
                                           device_id=config.MODBUS_UNIT_ID)
    except ModbusException as exc:
        log.warning("Modbus read failed: %s", exc)
        modbus.close()
        return None
    if resp.isError():
        log.warning("Device returned Modbus error: %s", resp)
        return None
    return decode(resp.registers)


def main() -> None:
    modbus = ModbusTcpClient(config.MODBUS_HOST, port=config.MODBUS_PORT, timeout=3)
    mqttc = make_mqtt_client()
    topic = config.telemetry_topic(config.DEVICE_ID)
    log.info("Polling every %.2fs, publishing to '%s'", config.POLL_INTERVAL_S, topic)

    last_seq, published = None, 0
    try:
        while True:
            started = time.monotonic()
            values = poll_device(modbus)

            # Only publish NEW samples (the device may not have updated yet).
            if values and values["seq"] != last_seq:
                if last_seq is not None and values["seq"] - last_seq > 1:
                    log.warning("Missed %d samples (polling slower than device?)",
                                values["seq"] - last_seq - 1)
                last_seq = values["seq"]
                # Modbus has no timestamps, so the gateway stamps the time of reading (UTC).
                payload = {
                    "device_id": config.DEVICE_ID,
                    "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    **values,
                }
                mqttc.publish(topic, json.dumps(payload), qos=config.MQTT_QOS)
                published += 1
                if published % 20 == 0:
                    log.info("Published %d messages (last seq=%d)", published, last_seq)

            # Sleep the remainder of the interval so the poll rate stays steady.
            time.sleep(max(0.0, config.POLL_INTERVAL_S - (time.monotonic() - started)))
    except KeyboardInterrupt:
        pass
    finally:
        mqttc.publish(config.status_topic(config.DEVICE_ID), "offline", qos=1, retain=True)
        mqttc.loop_stop()
        mqttc.disconnect()
        modbus.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    main()
