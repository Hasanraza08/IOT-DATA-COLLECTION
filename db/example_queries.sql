-- Example queries. Run all of them with:
--   docker compose exec -T postgres psql -U iot -d iot < db/example_queries.sql

-- 1. How much data do we have?
SELECT device_id, count(*) AS readings, min(measured_at) AS first, max(measured_at) AS last
FROM telemetry GROUP BY device_id;

-- 2. The 10 latest readings
SELECT measured_at, voltage_v, current_a, power_w, temperature_c
FROM telemetry WHERE device_id = 'motor-01'
ORDER BY measured_at DESC LIMIT 10;

-- 3. Averages over the last 5 minutes
SELECT round(avg(voltage_v)::numeric, 1)   AS avg_voltage_v,
       round(avg(current_a)::numeric, 1)   AS avg_current_a,
       round(avg(power_w)::numeric, 0)     AS avg_power_w,
       round(max(temperature_c)::numeric, 1) AS max_temperature_c
FROM telemetry
WHERE device_id = 'motor-01' AND measured_at > now() - interval '5 minutes';

-- 4. One-minute summary (uses the view from schema.sql)
SELECT * FROM telemetry_1min ORDER BY minute DESC LIMIT 10;

-- 5. Overheating alarm: readings where the winding is above 100 degC
SELECT measured_at, temperature_c, power_w
FROM telemetry WHERE temperature_c > 100
ORDER BY measured_at DESC LIMIT 10;

-- 6. Data quality: gaps in the device sample counter (lost samples)
SELECT seq AS gap_after_seq, next_seq - seq - 1 AS missing_samples
FROM (SELECT seq, lead(seq) OVER (PARTITION BY device_id ORDER BY measured_at) AS next_seq
      FROM telemetry) t
WHERE next_seq - seq > 1;

-- 7. Latency: how long from gateway reading to database insert
SELECT round(avg(extract(epoch FROM received_at - measured_at) * 1000)::numeric, 1) AS avg_latency_ms
FROM telemetry WHERE measured_at > now() - interval '5 minutes';
