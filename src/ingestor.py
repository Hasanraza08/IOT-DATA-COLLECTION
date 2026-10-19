"""SECTION 5 - The ingestor: MQTT in, PostgreSQL out.

Subscribes to the telemetry of ALL devices (MQTT wildcard '+'), checks each
message, and stores it as a row in the `telemetry` table.

Run:  python src/ingestor.py
"""
import json
import logging
import math
import time

import paho.mqtt.client as mqtt
import psycopg

import config
from register_map import FLOAT_FIELDS

log = logging.getLogger("ingestor")

INSERT_DEVICE = "INSERT INTO devices (device_id) VALUES (%s) ON CONFLICT DO NOTHING"

COLUMNS = ["device_id", "measured_at", "seq", *FLOAT_FIELDS, "profile_id"]
INSERT_TELEMETRY = (
    f"INSERT INTO telemetry ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
    # QoS 1 may deliver a message twice -> ignore the duplicate instead of failing
    "ON CONFLICT (device_id, measured_at) DO NOTHING"
)


class Database:
    """Small wrapper that reconnects automatically if PostgreSQL restarts."""

    def __init__(self, url: str):
        self.url, self.conn, self.known_devices = url, None, set()

    def _connect(self):
        while self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg.connect(self.url, autocommit=True)
                log.info("Connected to PostgreSQL")
            except psycopg.OperationalError as exc:
                log.warning("PostgreSQL not reachable (%s) - retrying in 3s", exc)
                time.sleep(3)

    def insert(self, row: dict) -> bool:
        """Insert one reading. Returns False if it was a duplicate."""
        while True:
            self._connect()
            try:
                with self.conn.cursor() as cur:
                    if row["device_id"] not in self.known_devices:
                        cur.execute(INSERT_DEVICE, (row["device_id"],))
                        self.known_devices.add(row["device_id"])
                    cur.execute(INSERT_TELEMETRY, [row[c] for c in COLUMNS])
                    return cur.rowcount == 1
            except psycopg.OperationalError as exc:      # connection lost -> retry
                log.warning("Lost DB connection (%s) - reconnecting", exc)
                self.conn.close()


def parse_message(payload: bytes) -> dict:
    """Validate the JSON before it touches the database. Raises ValueError if bad."""
    try:
        msg = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not JSON: {exc}") from exc
    for key in ["device_id", "ts", "seq", *FLOAT_FIELDS]:
        if key not in msg:
            raise ValueError(f"missing field '{key}'")
    for key in FLOAT_FIELDS:
        if not isinstance(msg[key], (int, float)) or not math.isfinite(msg[key]):
            raise ValueError(f"field '{key}' is not a finite number: {msg[key]!r}")
    row = {k: msg.get(k) for k in COLUMNS if k != "measured_at"}
    row["measured_at"] = msg["ts"]          # ISO-8601 string; PostgreSQL parses it
    return row


def main() -> None:
    db = Database(config.DATABASE_URL)
    subscription = f"{config.MQTT_TOPIC_ROOT}/+/telemetry"   # '+' = any device
    stats = {"stored": 0, "duplicates": 0, "rejected": 0}

    # clean_session=False + fixed client_id = "persistent session":
    # if the ingestor is down, the broker keeps its QoS 1 messages until it returns.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingestor-1",
                         clean_session=False)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(c, _userdata, flags, reason_code, _props):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("Connected to MQTT (resumed session: %s), subscribing to '%s'",
                 flags.session_present, subscription)
        c.subscribe(subscription, qos=config.MQTT_QOS)
        c.subscribe(f"{config.MQTT_TOPIC_ROOT}/+/status", qos=1)

    def on_message(_c, _userdata, msg):
        if msg.topic.endswith("/status"):
            log.info("Device status %s -> %s", msg.topic, msg.payload.decode())
            return
        try:
            row = parse_message(msg.payload)
        except ValueError as exc:
            stats["rejected"] += 1
            log.warning("Rejected message on %s: %s", msg.topic, exc)
            return
        if not db.insert(row):
            stats["duplicates"] += 1
            return
        stats["stored"] += 1
        if stats["stored"] % 20 == 0:
            log.info("stored=%(stored)d duplicates=%(duplicates)d rejected=%(rejected)d", stats)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    main()
