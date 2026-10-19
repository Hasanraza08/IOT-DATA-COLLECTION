# IoT Data Collection System with Modbus, MQTT and PostgreSQL

This project collects live telemetry from an industrial motor, namely voltage, current, power and temperature, and stores every reading in a PostgreSQL database so that it can be queried at any time.

Since I did not have access to a real motor, I built a simulated device in Python that replays a real world dataset, the [Electric Motor Temperature](https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature) dataset from Kaggle. It contains more than 185 hours of sensor recordings from a permanent magnet synchronous motor on a test bench, sampled twice per second, so the simulated device behaves exactly like the real motor did during the measurements.

## How the System Works

The data passes through five stages, and each stage has one clear job.

1. **Simulated motor** (`src/device_simulator.py`). It reads one row of the dataset every 0.5 seconds and writes the values into its Modbus registers, in the same way a real motor drive or energy meter would.
2. **Gateway** (`src/gateway.py`). It polls the motor over Modbus every 0.5 seconds, converts the raw register values into named measurements, adds a timestamp and publishes the result as a JSON message over MQTT.
3. **MQTT broker** (Mosquitto). It receives every message from the gateway and delivers it to all programs that have subscribed to it.
4. **Ingestor** (`src/ingestor.py`). It subscribes to the telemetry messages, checks that each message is complete and valid, and writes it into the database.
5. **PostgreSQL database**. It stores every reading permanently, where it can be queried with SQL.

In short, the motor speaks Modbus, the gateway translates Modbus into MQTT, and the ingestor translates MQTT into SQL.

## Project Structure

| File or folder | Purpose |
|---|---|
| `src/config.py` | All settings, such as ports, addresses and database login |
| `src/dataset.py` | Reads the Kaggle file and calculates voltage, current, power and temperature |
| `src/register_map.py` | Defines which value is stored in which Modbus register |
| `src/device_simulator.py` | The simulated motor, which acts as a Modbus server |
| `src/gateway.py` | Reads the motor over Modbus and publishes the values over MQTT |
| `src/ingestor.py` | Receives the MQTT messages and saves them in PostgreSQL |
| `db/schema.sql` | Creates the database tables |
| `db/example_queries.sql` | Ready to use SQL queries |
| `mosquitto/mosquitto.conf` | Settings of the MQTT broker |
| `tests/test_core.py` | Unit tests |
| `data/` | The place for the dataset file `measures_v2.csv` |
| `docs/LEARNING_GUIDE.md` | My notes explaining each part of the project |
| `docker-compose.yml` and `Dockerfile` | Start the complete system with Docker |
| `requirements.txt` | Python libraries used in the project |

## How to Run the Project

The only programs required are Docker Desktop and Git.

**Step 1. Download the code**

```bash
git clone https://github.com/<your-username>/iot-data-collection.git
cd iot-data-collection
```

**Step 2. Download the dataset**

Download `measures_v2.csv` from [Kaggle](https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature) and place it in the `data` folder. The file is too large for GitHub, which is why it is not included in this repository.

**Step 3. Start the system**

```bash
docker compose --profile app up --build
```

This single command starts the MQTT broker, the database and the three Python programs. After about 30 seconds, log lines similar to the following appear, although the numbers will be different.

```
device-1    | seq=180  U=129.8V  I=151.6A  P=26924W  T=36.0C
gateway-1   | Published 180 messages (last seq=180)
ingestor-1  | stored=180 duplicates=0 rejected=0
```

The three counters always match, which shows that every reading made its way from the motor into the database.

**Step 4. Query the data**

Open a second terminal in the same folder and run the following command to see the five latest readings.

```bash
docker compose exec postgres psql -U iot -d iot -c "SELECT measured_at, voltage_v, current_a, power_w, temperature_c FROM telemetry ORDER BY measured_at DESC LIMIT 5;"
```

All example queries can be run at once. The first command is for Mac and Linux, and the second one is for Windows PowerShell.

```bash
docker compose exec -T postgres psql -U iot -d iot < db/example_queries.sql
Get-Content db/example_queries.sql | docker compose exec -T postgres psql -U iot -d iot
```

The MQTT messages can also be watched live while the system is running.

```bash
docker compose exec mosquitto mosquitto_sub -t "factory/#" -v
```

**Step 5. Stop the system**

Press Ctrl and C in the first terminal, and then run the following command. The stored data is kept for the next start.

```bash
docker compose --profile app down
```

**Running the Python programs without Docker**

It is also possible to start only the broker and the database in Docker and run the Python programs directly, which is more convenient during development.

```bash
docker compose up -d
pip install -r requirements.txt
python src/device_simulator.py
python src/gateway.py
python src/ingestor.py
```

Each of the last three commands should be run in its own terminal. The unit tests can be run with `python -m unittest discover tests`.

## The Dataset and the Calculated Values

The Kaggle dataset does not contain columns named voltage or current. Like most motor controllers, it describes them as two components each, called the d axis and the q axis (`u_d`, `u_q` for voltage and `i_d`, `i_q` for current). I therefore calculate the four required values myself in `src/dataset.py`.

| Value | Calculation | Unit |
|---|---|---|
| Voltage | Square root of (u_d squared plus u_q squared) | Volt |
| Current | Square root of (i_d squared plus i_q squared) | Ampere |
| Power | 1.5 times (u_d times i_d plus u_q times i_q) | Watt |
| Temperature | Taken directly from the `stator_winding` column | Degrees Celsius |

In addition, the ambient temperature, coolant temperature, motor speed and torque are transmitted as well. When the simulated motor reaches the last row of the dataset, it starts again from the first row, so the data stream never stops.

## Protocol Choices

I used both protocols, each at the level where it fits best. This is also the most common setup in real factories, where machines speak Modbus and an edge gateway forwards their data over MQTT.

### Modbus TCP between the Motor and the Gateway

Modbus is the standard protocol of industrial devices such as motor drives, energy meters and PLCs, which is why the simulated motor uses it as well. If the simulator were replaced by a real device, the gateway could stay exactly the same.

In Modbus, the device never sends data on its own. It keeps its latest values in numbered registers and only answers when it is asked, so the gateway polls it every 0.5 seconds. A single register holds a whole number of 16 bits, which is not enough for a decimal value such as 129.64 V. Each decimal value is therefore stored as a 32 bit floating point number across two registers. The gateway reads all 19 registers in one request, which guarantees that voltage, current and power always belong to the same moment.

The register `seq` is a counter that increases by one with every new reading. It allows the gateway to skip readings it has already sent and to detect readings that were missed.

| Registers | Value | Data type |
|---|---|---|
| 0 and 1 | Voltage in volts | 32 bit float |
| 2 and 3 | Current in amperes | 32 bit float |
| 4 and 5 | Power in watts | 32 bit float |
| 6 and 7 | Winding temperature in degrees Celsius | 32 bit float |
| 8 and 9 | Ambient temperature in degrees Celsius | 32 bit float |
| 10 and 11 | Coolant temperature in degrees Celsius | 32 bit float |
| 12 and 13 | Motor speed in rpm | 32 bit float |
| 14 and 15 | Torque in Nm | 32 bit float |
| 16 and 17 | Reading counter `seq` | 32 bit whole number |
| 18 | Test session `profile_id` | 16 bit whole number |

The motor uses port 5020 instead of the standard Modbus port 502, because ports below 1024 require administrator rights. Modbus has no authentication, no encryption and no timestamps, which is acceptable inside a closed factory network but not beyond it. For this reason the gateway switches to MQTT for the rest of the journey.

### MQTT between the Gateway and the Ingestor

MQTT is a lightweight protocol built for IoT devices and unreliable networks. It works on the publish and subscribe principle. The gateway publishes its messages to the broker without knowing who receives them, and the ingestor subscribes to them without knowing who sends them. This means that a dashboard or an alarm system could be added later simply by subscribing, without any change to the gateway.

The readings are published on the topic `factory/motor-01/telemetry`, and the online or offline status of the gateway on `factory/motor-01/status`. The ingestor subscribes to `factory/+/telemetry`, where the plus sign stands for any device, so a second motor would be stored automatically. Each message is a JSON text in which every value has a name, as in the following example.

```json
{"device_id": "motor-01", "ts": "2026-10-16T14:20:49.580+00:00", "seq": 180,
 "voltage_v": 129.64, "current_a": 150.22, "power_w": 26914.9, "temperature_c": 63.19}
```

Since Modbus carries no time information, the gateway adds the time of each reading in UTC.

I chose **QoS level 1** for all messages. With this level, every message is confirmed by the receiver and sent again until the confirmation arrives, so no reading is ever lost. The only drawback is that a message can occasionally arrive twice, which the database handles by ignoring the second copy, as described in the next section. This achieves the same result as QoS level 2 with less overhead.

Two further features make the system reliable, and I tested both of them.

1. **Persistent session.** When the ingestor is stopped, the broker keeps its messages and delivers them as soon as it reconnects. After stopping and restarting the ingestor, no readings were missing in the database.
2. **Last Will.** When the gateway connects, it asks the broker to announce it as offline if it disappears unexpectedly. When I forcibly stopped the gateway, the broker published the offline status on its own.

I did not choose HTTP because it is heavier and not designed for a continuous stream of small messages. For use in a real plant, I would add TLS encryption and user authentication to the broker.

## Database Schema

The tables are defined in [`db/schema.sql`](db/schema.sql) and are created automatically when the database starts for the first time.

**Table `devices`** holds one row per device.

| Column | Type | Meaning |
|---|---|---|
| `device_id` | TEXT, primary key | Name of the device, for example `motor-01` |
| `description` | TEXT | Optional description |
| `first_seen_at` | TIMESTAMPTZ | Time when the device was first seen |

**Table `telemetry`** holds one row per reading.

| Column | Type | Meaning |
|---|---|---|
| `id` | BIGSERIAL, primary key | Row number |
| `device_id` | TEXT, foreign key to `devices` | Device that sent the reading |
| `measured_at` | TIMESTAMPTZ | Time when the gateway read the values |
| `received_at` | TIMESTAMPTZ | Time when the database stored the row |
| `seq` | BIGINT | Reading counter of the device |
| `voltage_v` | REAL | Voltage in volts |
| `current_a` | REAL | Current in amperes |
| `power_w` | REAL | Power in watts |
| `temperature_c` | REAL | Winding temperature in degrees Celsius |
| `ambient_temp_c` | REAL | Ambient temperature in degrees Celsius |
| `coolant_temp_c` | REAL | Coolant temperature in degrees Celsius |
| `motor_speed_rpm` | REAL | Motor speed in rpm |
| `torque_nm` | REAL | Torque in Nm |
| `profile_id` | INTEGER | Test session in the original dataset |

The combination of `device_id` and `measured_at` is unique, so a device can never have two readings at the same moment.

The main decisions behind this design are the following.

1. **One column per measurement.** The set of measurements is fixed, so separate typed columns keep the table compact and the queries simple.
2. **Time stored in UTC.** The type TIMESTAMPTZ avoids any confusion with time zones or daylight saving time.
3. **Two timestamps.** The difference between `measured_at` and `received_at` shows how long a reading takes to travel through the system, which was about one second in my tests.
4. **No duplicates.** The unique rule together with `ON CONFLICT DO NOTHING` makes the database ignore a second copy of a message, which solves the only weakness of QoS level 1.
5. **Foreign key.** Every reading must belong to a device listed in the `devices` table. The ingestor registers a new device automatically the first time it receives data from it.
6. **One minute view.** The view `telemetry_1min` provides average values per minute, which is useful for dashboards.

The file [`db/example_queries.sql`](db/example_queries.sql) contains queries for the latest readings, average values, high temperature alarms, missing readings and the delay of the system.

## Error Handling

| Situation | Behaviour of the system |
|---|---|
| The motor is not reachable | The gateway logs a warning and tries again with the next poll |
| The broker is not reachable | The gateway buffers its messages and reconnects automatically |
| The ingestor is stopped | The broker keeps the messages until the ingestor returns |
| The database is not reachable | The ingestor retries every 3 seconds |
| A message is incomplete or invalid | The ingestor rejects it, so it never reaches the database |
| A message arrives twice | The database ignores the second copy |
| A reading is missed | The gateway logs a warning based on the gap in `seq` |

## Common Problems

1. **Dataset not found.** The file `data/measures_v2.csv` is missing, so Step 2 needs to be repeated.
2. **No configuration file provided.** The terminal is not open in the project folder. Moving into the folder with the `cd` command solves this.
3. **Port is already allocated.** Another program is already using port 5432 or 1883. Closing that program or changing the port in `docker-compose.yml` solves this.
4. **No rows in the database.** The logs show what is happening, and the ingestor prints a short summary every 20 stored rows.
