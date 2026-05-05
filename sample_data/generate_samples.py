#!/usr/bin/env python3
"""
Generate realistic sample data for the ocean-curation-pipeline-toolkit demo.

Creates two files that mimic what a PI might actually submit to a data repository:
1. A messy Excel workbook with common problems curators encounter
2. A cleaner CSV that still needs header normalization and timestamp fixing

Data simulates a Gulf of Mexico research cruise (GOMECC-style) with:
- CTD station casts at multiple depths
- Water chemistry samples (carbonate system, dissolved oxygen, nutrients)
- Realistic coordinate coverage: western Gulf near Texas coast

This is SYNTHETIC data for demonstration. Real data should be sourced from
oceanographic data repositories like NOAA NCEI for production use.
"""

import random
import numpy as np
import pandas as pd
from pathlib import Path

random.seed(42)
np.random.seed(42)

OUT_DIR = Path(__file__).parent / "raw"
OUT_DIR.mkdir(exist_ok=True)

# ── Gulf of Mexico station coordinates (realistic cruise track) ──────────
STATIONS = [
    {"id": "GOM-001", "lat": 27.500, "lon": -96.500, "name": "Corpus Christi Shelf"},
    {"id": "GOM-002", "lat": 27.750, "lon": -95.800, "name": "Matagorda Slope"},
    {"id": "GOM-003", "lat": 28.100, "lon": -94.500, "name": "Galveston Approach"},
    {"id": "GOM-004", "lat": 27.200, "lon": -93.200, "name": "Central Gulf Mid"},
    {"id": "GOM-005", "lat": 26.800, "lon": -92.000, "name": "De Soto Canyon West"},
    {"id": "GOM-006", "lat": 27.000, "lon": -91.500, "name": "Mississippi Fan"},
    {"id": "GOM-007", "lat": 28.500, "lon": -93.800, "name": "Louisiana Shelf"},
    {"id": "GOM-008", "lat": 29.000, "lon": -94.200, "name": "Sabine Pass"},
]

DEPTHS = [5, 10, 25, 50, 100, 200, 500, 1000]
BASE_DATE = pd.Timestamp("2021-07-18 06:00")


def realistic_temperature(depth, lat):
    """Generate realistic Gulf of Mexico temperature profile."""
    surface = 29.5 - (lat - 27) * 0.3 + np.random.normal(0, 0.3)
    if depth <= 50:
        return round(surface - depth * 0.12 + np.random.normal(0, 0.2), 2)
    elif depth <= 200:
        return round(15.0 - (depth - 50) * 0.03 + np.random.normal(0, 0.3), 2)
    elif depth <= 500:
        return round(10.0 - (depth - 200) * 0.008 + np.random.normal(0, 0.15), 2)
    else:
        return round(4.5 - (depth - 500) * 0.001 + np.random.normal(0, 0.1), 2)


def realistic_salinity(depth, lat):
    """Generate realistic Gulf salinity profile."""
    surface = 35.0 + np.random.normal(0, 0.3)
    if depth <= 50:
        return round(surface + depth * 0.015 + np.random.normal(0, 0.1), 3)
    else:
        return round(35.8 + (depth - 50) * 0.0005 + np.random.normal(0, 0.05), 3)


def realistic_do(depth, temp):
    """Generate dissolved oxygen from depth and temperature."""
    if depth <= 25:
        return round(7.0 - temp * 0.02 + np.random.normal(0, 0.3), 2)
    elif depth <= 200:
        return round(4.0 - (depth - 25) * 0.01 + np.random.normal(0, 0.2), 2)
    else:
        return round(2.5 + np.random.normal(0, 0.3), 2)


# ── Generate messy Excel workbook ────────────────────────────────────────
rows = []
time_offset = 0

for stn in STATIONS:
    cast_time = BASE_DATE + pd.Timedelta(hours=time_offset)
    for depth in DEPTHS:
        if depth > 500 and stn["lat"] > 28.5:
            continue  # Shallow stations don't have deep casts

        temp = realistic_temperature(depth, stn["lat"])
        sal = realistic_salinity(depth, stn["lat"])
        do_val = realistic_do(depth, temp)
        ph = round(8.15 - depth * 0.0003 + np.random.normal(0, 0.02), 3)
        talk = round(2300 + depth * 0.08 + np.random.normal(0, 10), 1)
        nitrate = round(max(0.1, 0.5 + depth * 0.025 + np.random.normal(0, 0.5)), 2)
        phosphate = round(max(0.01, 0.05 + depth * 0.002 + np.random.normal(0, 0.03)), 3)

        # ── Introduce intentional messiness ──
        # Problem 1: Inconsistent date formats
        date_formats = [
            cast_time.strftime("%m/%d/%Y %H:%M"),
            cast_time.strftime("%Y-%m-%d %H:%M:%S"),
            cast_time.strftime("%d-%b-%Y %H:%M"),
            cast_time.strftime("%m/%d/%y %I:%M %p"),
        ]
        date_str = random.choice(date_formats)

        # Problem 2: Missing values (randomly ~5%)
        if random.random() < 0.05:
            do_val = ""
        if random.random() < 0.03:
            ph = ""
        if random.random() < 0.04:
            nitrate = ""

        # Problem 3: Whitespace issues
        station_val = stn["id"] if random.random() > 0.1 else f"  {stn['id']}  "

        # Problem 4: Occasional wrong decimal separator
        if random.random() < 0.03 and isinstance(temp, float):
            temp = str(temp).replace(".", ",")

        rows.append({
            "Station  ID": station_val,  # Problem 5: space in header
            "Latitude (°N)": stn["lat"],
            "Longitude (°W)": stn["lon"],  # Problem 6: Sign convention issue
            "Depth (m)": depth,
            "Date/Time": date_str,
            "Temperature (°C)": temp,
            "Salinity (PSU)": sal,
            "Dissolved Oxygen (mg/L)": do_val,
            "pH": ph,
            "Total Alkalinity (µmol/kg)": talk,
            "NO3 (µmol/L)": nitrate,
            "PO4 (µmol/L)": phosphate,
            "QC Flag": random.choice([1, 1, 1, 1, 2, 2, 3]),
        })

    time_offset += random.uniform(4, 8)

df_messy = pd.DataFrame(rows)

# Problem 7: Add duplicate rows
dup_idx = random.sample(range(len(df_messy)), 3)
df_messy = pd.concat([df_messy, df_messy.iloc[dup_idx]], ignore_index=True)

# Problem 8: Add a completely empty row
empty_row = pd.DataFrame([{c: "" for c in df_messy.columns}])
df_messy = pd.concat([df_messy, empty_row], ignore_index=True)

# Write messy Excel with problems
excel_path = OUT_DIR / "GOMECC4_cruise_watersamples_RAW.xlsx"
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    df_messy.to_excel(writer, sheet_name="Water Chemistry", index=False)
    # Problem 9: Hidden metadata sheet
    meta_df = pd.DataFrame({
        "Field": ["Cruise", "Vessel", "Chief Scientist", "Start Date", "End Date"],
        "Value": ["GOMECC-4", "R/V Ronald H. Brown", "Dr. Jane Doe",
                  "2021-07-15", "2021-08-15"],
    })
    meta_df.to_excel(writer, sheet_name="Metadata", index=False)

print(f"Created: {excel_path}  ({len(df_messy)} rows with intentional issues)")

# ── Generate cleaner CSV (station log) ──────────────────────────────────
station_rows = []
for i, stn in enumerate(STATIONS):
    station_rows.append({
        "Station ID": stn["id"],
        "Station Name": stn["name"],
        "Latitude_DD": stn["lat"],
        "Longitude_DD": stn["lon"],
        "Bottom Depth (m)": random.choice([200, 500, 1000, 1500, 2000, 3000]),
        "Date of Cast": (BASE_DATE + pd.Timedelta(hours=i * 6)).strftime("%m/%d/%Y"),
        "Number of Bottles": random.randint(8, 24),
        "CTD Serial Number": f"SBE911-{random.randint(1000, 9999)}",
        "Weather": random.choice(["Clear", "Partly Cloudy", "Overcast", "Squalls"]),
        "Sea State (Beaufort)": random.randint(1, 5),
        "Notes": random.choice([
            "", "", "",
            "Strong current at depth",
            "Wire angle >15 deg below 200m",
            "Bottle 12 did not fire",
        ]),
    })

df_stations = pd.DataFrame(station_rows)
csv_path = OUT_DIR / "station_log.csv"
df_stations.to_csv(csv_path, index=False)
print(f"Created: {csv_path}  ({len(df_stations)} stations)")

# ── Also keep a clean version of station_data.csv for backward compat ──
clean_rows = []
time_offset = 0
for stn in STATIONS:
    cast_time = BASE_DATE + pd.Timedelta(hours=time_offset)
    for depth in [5, 25, 50, 100]:
        clean_rows.append({
            "Station": stn["id"],
            "Latitude": stn["lat"],
            "Longitude": stn["lon"],
            "Depth (m)": depth,
            "Date/Time": cast_time.strftime("%m/%d/%Y %H:%M"),
            "Temperature (°C)": realistic_temperature(depth, stn["lat"]),
            "Salinity (PSU)": realistic_salinity(depth, stn["lat"]),
            "Dissolved Oxygen (mg/L)": realistic_do(depth,
                                                      realistic_temperature(depth, stn["lat"])),
            "pH": round(8.15 - depth * 0.0003 + np.random.normal(0, 0.02), 3),
            "Total Alkalinity (µmol/kg)": round(2300 + depth * 0.08
                                                 + np.random.normal(0, 10), 1),
        })
    time_offset += random.uniform(4, 8)

df_clean = pd.DataFrame(clean_rows)
csv_clean_path = OUT_DIR / "station_data.csv"
df_clean.to_csv(csv_clean_path, index=False)
print(f"Created: {csv_clean_path}  ({len(df_clean)} rows)")

print("\nSample data generation complete.")
print("Files ready in sample_data/raw/")
