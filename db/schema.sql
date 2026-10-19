-- =====================================================================
-- Database schema for the IoT data collection system
-- Loaded automatically by the PostgreSQL container on first start
-- (anything in /docker-entrypoint-initdb.d runs once on an empty DB).
-- =====================================================================

-- One row per physical (or simulated) device.
-- The ingestor registers a device automatically the first time it hears from it.
CREATE TABLE IF NOT EXISTS devices (
    device_id     TEXT PRIMARY KEY,                 -- e.g. 'motor-01' (also part of the MQTT topic)
    description   TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per measurement (a "time-series" table).
CREATE TABLE IF NOT EXISTS telemetry (
    id              BIGSERIAL PRIMARY KEY,
    device_id       TEXT        NOT NULL REFERENCES devices(device_id),
    measured_at     TIMESTAMPTZ NOT NULL,             -- when the gateway read the device
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),-- when the database stored it
    seq             BIGINT      NOT NULL,             -- device sample counter (detects gaps)

    -- the four values the task asks for
    voltage_v       REAL,      -- stator voltage magnitude   [V]
    current_a       REAL,      -- stator current magnitude   [A]
    power_w         REAL,      -- electrical active power    [W]
    temperature_c   REAL,      -- stator winding temperature [degC]

    -- extra context from the same dataset
    ambient_temp_c  REAL,      -- [degC]
    coolant_temp_c  REAL,      -- [degC]
    motor_speed_rpm REAL,      -- [rpm]
    torque_nm       REAL,      -- [Nm]
    profile_id      INTEGER,   -- measurement session in the original dataset

    -- MQTT QoS 1 is "at least once": the same message can arrive twice.
    -- This constraint makes the insert idempotent (duplicates are ignored).
    -- A device can't produce two readings at the exact same instant, and a
    -- redelivered message carries the same timestamp as the original.
    -- The unique index behind this constraint also serves our main query
    -- pattern: "data for device X in time range Y".
    CONSTRAINT telemetry_device_time_uniq UNIQUE (device_id, measured_at)
);

-- Convenience view: one-minute averages per device (good for dashboards).
CREATE OR REPLACE VIEW telemetry_1min AS
SELECT device_id,
       date_trunc('minute', measured_at) AS minute,
       count(*)                          AS samples,
       avg(voltage_v)::REAL              AS avg_voltage_v,
       avg(current_a)::REAL              AS avg_current_a,
       avg(power_w)::REAL                AS avg_power_w,
       max(temperature_c)::REAL          AS max_temperature_c
FROM telemetry
GROUP BY device_id, date_trunc('minute', measured_at);
