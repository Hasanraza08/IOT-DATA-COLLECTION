"""Load the Kaggle "Electric Motor Temperature" dataset and derive the telemetry.

Dataset: https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature
File:    measures_v2.csv  (sensor recordings of a permanent-magnet synchronous
         motor on a test bench, sampled at 2 Hz, grouped into sessions by profile_id)

The motor controller measures voltage and current as two components each
(d and q axis, a standard way to describe 3-phase quantities). We combine them
into the single numbers the task asks for:

    voltage  |u| = sqrt(u_d^2 + u_q^2)
    current  |i| = sqrt(i_d^2 + i_q^2)
    power    P   = 1.5 * (u_d*i_d + u_q*i_q)     (amplitude-invariant dq transform)

Temperature is taken from the stator winding sensor (the hottest, most
important temperature in a motor).
"""
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["u_d", "u_q", "i_d", "i_q", "stator_winding",
                    "ambient", "coolant", "motor_speed", "torque"]


def load_telemetry(path: str, profile_id: str = "") -> pd.DataFrame:
    """Read the CSV and return one row per sample with our telemetry columns."""
    csv = Path(path)
    if not csv.exists():
        raise FileNotFoundError(
            f"Dataset not found at '{csv}'. Download measures_v2.csv from "
            "https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature "
            "and put it in the data/ folder (see README, step 2)."
        )

    raw = pd.read_csv(csv)
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Dataset is missing columns {missing}; found {list(raw.columns)}")

    if "profile_id" not in raw.columns:
        raw["profile_id"] = 0
    if profile_id:
        raw = raw[raw["profile_id"] == int(profile_id)]
        if raw.empty:
            raise ValueError(f"No rows with profile_id={profile_id}")

    df = pd.DataFrame({
        "voltage_v":       np.hypot(raw["u_d"], raw["u_q"]),
        "current_a":       np.hypot(raw["i_d"], raw["i_q"]),
        "power_w":         1.5 * (raw["u_d"] * raw["i_d"] + raw["u_q"] * raw["i_q"]),
        "temperature_c":   raw["stator_winding"],
        "ambient_temp_c":  raw["ambient"],
        "coolant_temp_c":  raw["coolant"],
        "motor_speed_rpm": raw["motor_speed"],
        "torque_nm":       raw["torque"],
        "profile_id":      raw["profile_id"].astype(int),
    })
    return df.dropna().reset_index(drop=True)
