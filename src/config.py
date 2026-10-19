"""Central settings for all three services.

Every value can be overridden with an environment variable, so the same code
runs on your laptop (defaults below) and inside Docker (values set in
docker-compose.yml) without editing any file.
"""
import os


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


# --- the simulated device ------------------------------------------------
DEVICE_ID = _env("DEVICE_ID", "motor-01")               # name used in MQTT topic + DB
DATASET_PATH = _env("DATASET_PATH", "data/measures_v2.csv")
DATASET_PROFILE_ID = _env("DATASET_PROFILE_ID", "")     # replay only one session ("" = all)
UPDATE_INTERVAL_S = float(_env("UPDATE_INTERVAL_S", "0.5"))  # dataset is sampled at 2 Hz

# --- Modbus TCP (device <-> gateway) -------------------------------------
# 502 is the official Modbus port, but ports below 1024 need admin rights,
# so we use 5020 for development.
MODBUS_HOST = _env("MODBUS_HOST", "127.0.0.1")
MODBUS_PORT = int(_env("MODBUS_PORT", "5020"))
MODBUS_UNIT_ID = int(_env("MODBUS_UNIT_ID", "1"))       # "slave id" of the device
POLL_INTERVAL_S = float(_env("POLL_INTERVAL_S", "0.5"))

# --- MQTT (gateway -> broker -> ingestor) --------------------------------
MQTT_HOST = _env("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(_env("MQTT_PORT", "1883"))
MQTT_TOPIC_ROOT = _env("MQTT_TOPIC_ROOT", "factory")
MQTT_QOS = int(_env("MQTT_QOS", "1"))


def telemetry_topic(device_id: str) -> str:
    return f"{MQTT_TOPIC_ROOT}/{device_id}/telemetry"     # factory/motor-01/telemetry


def status_topic(device_id: str) -> str:
    return f"{MQTT_TOPIC_ROOT}/{device_id}/status"        # factory/motor-01/status


# --- PostgreSQL ----------------------------------------------------------
DATABASE_URL = _env("DATABASE_URL", "postgresql://iot:iot@127.0.0.1:5432/iot")
