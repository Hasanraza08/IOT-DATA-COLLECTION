"""Unit tests for the parts that don't need a broker or database.

Run:  python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dataset import load_telemetry              # noqa: E402
from ingestor import parse_message              # noqa: E402
from register_map import BLOCK_SIZE, decode, encode  # noqa: E402

SAMPLE = {
    "voltage_v": 231.5, "current_a": 12.25, "power_w": 2500.0, "temperature_c": 65.5,
    "ambient_temp_c": 24.0, "coolant_temp_c": 18.75, "motor_speed_rpm": 1500.0,
    "torque_nm": 15.5, "seq": 70000, "profile_id": 17,
}


class RegisterMapTest(unittest.TestCase):
    def test_round_trip(self):
        regs = encode(SAMPLE)
        self.assertEqual(len(regs), BLOCK_SIZE)
        self.assertTrue(all(0 <= r <= 0xFFFF for r in regs))   # valid 16-bit registers
        self.assertEqual(decode(regs), SAMPLE)

    def test_seq_above_16_bits_survives(self):
        self.assertEqual(decode(encode({**SAMPLE, "seq": 2**32 - 1}))["seq"], 2**32 - 1)


class DatasetTest(unittest.TestCase):
    def test_derived_values(self):
        csv = ("u_q,coolant,stator_winding,u_d,stator_tooth,motor_speed,i_d,i_q,pm,"
               "stator_yoke,ambient,torque,profile_id\n"
               "4,18,30,3,25,1000,0,10,40,22,20,5,2\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv)
        row = load_telemetry(f.name).iloc[0]
        self.assertAlmostEqual(row.voltage_v, 5.0)            # sqrt(3^2 + 4^2)
        self.assertAlmostEqual(row.current_a, 10.0)           # sqrt(0^2 + 10^2)
        self.assertAlmostEqual(row.power_w, 60.0)             # 1.5*(3*0 + 4*10)
        self.assertAlmostEqual(row.temperature_c, 30.0)

    def test_missing_file_has_helpful_message(self):
        with self.assertRaisesRegex(FileNotFoundError, "kaggle"):
            load_telemetry("does/not/exist.csv")


class MessageValidationTest(unittest.TestCase):
    def message(self, **overrides):
        return json.dumps({"device_id": "motor-01", "ts": "2026-01-01T00:00:00+00:00",
                           **SAMPLE, **overrides}).encode()

    def test_valid(self):
        self.assertEqual(parse_message(self.message())["voltage_v"], 231.5)

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_message(b"not json")

    def test_rejects_missing_field(self):
        msg = json.loads(self.message())
        del msg["power_w"]
        with self.assertRaisesRegex(ValueError, "power_w"):
            parse_message(json.dumps(msg).encode())

    def test_rejects_non_numeric(self):
        with self.assertRaisesRegex(ValueError, "voltage_v"):
            parse_message(self.message(voltage_v="high"))


if __name__ == "__main__":
    unittest.main()
