"""
profile command: Generate a data quality profile for processed files.

Produces a comprehensive report including:
- Variable-level statistics (count, mean, std, min, max, percentiles)
- Missing value analysis per column
- Outlier detection (IQR method)
- Coordinate coverage summary with bounding box
- Temporal coverage and gap analysis
- Data type inventory
- Overall quality grade

Output: data_quality_profile.json + data_quality_report.md
"""

import json
from pathlib import Path

import click
import pandas as pd

from ocean_curator.utils import (
    get_submission_dir,
    ensure_subdirs,
    log_provenance,
    now_iso,
    setup_logger,
)


def profile_numeric(series: pd.Series) -> dict:
    """Compute comprehensive statistics for a numeric column."""
    clean = pd.to_numeric(series, errors="coerce")
    valid = clean.dropna()
    total = len(series)
    missing = total - len(valid)

    if len(valid) == 0:
        return {
            "type": "numeric",
            "total": total,
            "valid": 0,
            "missing": missing,
            "missing_pct": 100.0,
        }

    q1 = float(valid.quantile(0.25))
    q3 = float(valid.quantile(0.75))
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outliers = int(((valid < lower_fence) | (valid > upper_fence)).sum())

    return {
        "type": "numeric",
        "total": total,
        "valid": len(valid),
        "missing": missing,
        "missing_pct": round(missing / total * 100, 2) if total else 0,
        "mean": round(float(valid.mean()), 4),
        "std": round(float(valid.std()), 4),
        "min": round(float(valid.min()), 4),
        "p25": round(q1, 4),
        "median": round(float(valid.median()), 4),
        "p75": round(q3, 4),
        "max": round(float(valid.max()), 4),
        "iqr": round(iqr, 4),
        "outliers_iqr": outliers,
        "outlier_pct": round(outliers / len(valid) * 100, 2) if len(valid) else 0,
    }


def profile_categorical(series: pd.Series) -> dict:
    """Profile a categorical/string column."""
    total = len(series)
    non_null = series.dropna()
    non_empty = non_null[non_null.astype(str).str.strip() != ""]
    missing = total - len(non_empty)
    unique = non_empty.nunique()
    top = non_empty.value_counts().head(5).to_dict()

    return {
        "type": "categorical",
        "total": total,
        "valid": len(non_empty),
        "missing": missing,
        "missing_pct": round(missing / total * 100, 2) if total else 0,
        "unique": unique,
        "top_values": {str(k): int(v) for k, v in top.items()},
    }


def profile_temporal(series: pd.Series) -> dict:
    """Profile a datetime column."""
    try:
        parsed = pd.to_datetime(series.astype(str), errors="coerce", format="mixed")
    except (TypeError, ValueError):
        parsed = pd.to_datetime(series.astype(str), errors="coerce")
    valid = parsed.dropna()
    total = len(series)
    missing = total - len(valid)

    if len(valid) == 0:
        return {
            "type": "temporal",
            "total": total,
            "valid": 0,
            "missing": missing,
            "missing_pct": 100.0,
        }

    # Gap analysis: sort and find consecutive differences
    sorted_times = valid.sort_values()
    if len(sorted_times) > 1:
        diffs = sorted_times.diff().dropna()
        median_gap = diffs.median()
        max_gap = diffs.max()
        # Gaps larger than 3x median
        large_gaps = diffs[diffs > 3 * median_gap]
    else:
        median_gap = pd.Timedelta(0)
        max_gap = pd.Timedelta(0)
        large_gaps = pd.Series(dtype="timedelta64[ns]")

    return {
        "type": "temporal",
        "total": total,
        "valid": len(valid),
        "missing": missing,
        "missing_pct": round(missing / total * 100, 2) if total else 0,
        "earliest": str(valid.min()),
        "latest": str(valid.max()),
        "span": str(valid.max() - valid.min()),
        "median_interval": str(median_gap),
        "max_gap": str(max_gap),
        "large_gaps": len(large_gaps),
    }


def is_temporal_column(series: pd.Series, col_name: str) -> bool:
    """Heuristic: is this column likely a timestamp?"""
    # Only consider temporal if the column name suggests it
    temporal_keywords = ("date", "time", "timestamp", "datetime")
    name_match = any(kw in col_name.lower() for kw in temporal_keywords)
    if not name_match:
        return False

    # If the dtype is already numeric, it's not temporal
    if pd.api.types.is_numeric_dtype(series):
        return False

    # Try parsing a sample of string values
    sample = series.dropna().astype(str).head(10)
    if len(sample) == 0:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    except (TypeError, ValueError):
        try:
            parsed = pd.to_datetime(sample, errors="coerce")
        except Exception:
            return False
    valid = parsed.dropna()
    if len(valid) == 0:
        return False
    # Sanity check: parsed dates should be in a reasonable range
    min_year = valid.min().year
    max_year = valid.max().year
    if min_year < 1900 or max_year > 2100:
        return False
    return len(valid) / len(sample) > 0.5


def profile_file(csv_path: Path, logger) -> dict:
    """Generate a complete quality profile for a single CSV file."""
    df = pd.read_csv(csv_path)
    profile = {
        "file": csv_path.name,
        "rows": len(df),
        "columns": len(df.columns),
        "total_cells": len(df) * len(df.columns),
        "total_missing": int(df.isnull().sum().sum()),
        "completeness_pct": round(
            (1 - df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100, 2
        ),
        "duplicate_rows": int(df.duplicated().sum()),
        "variables": {},
    }

    # Spatial summary
    lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
    lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
    if lat_col and lon_col:
        lats = pd.to_numeric(df[lat_col], errors="coerce").dropna()
        lons = pd.to_numeric(df[lon_col], errors="coerce").dropna()
        if len(lats) and len(lons):
            profile["spatial_coverage"] = {
                "south_lat": round(float(lats.min()), 4),
                "north_lat": round(float(lats.max()), 4),
                "west_lon": round(float(lons.min()), 4),
                "east_lon": round(float(lons.max()), 4),
                "unique_positions": int(
                    df[[lat_col, lon_col]].drop_duplicates().shape[0]
                ),
            }

    # Profile each variable
    for col in df.columns:
        if is_temporal_column(df[col], col):
            profile["variables"][col] = profile_temporal(df[col])
        elif pd.api.types.is_numeric_dtype(df[col]):
            profile["variables"][col] = profile_numeric(df[col])
        else:
            # Try numeric conversion
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() / max(len(df), 1) > 0.5:
                profile["variables"][col] = profile_numeric(df[col])
            else:
                profile["variables"][col] = profile_categorical(df[col])

    # Compute overall quality grade
    completeness = profile["completeness_pct"]
    dup_pct = profile["duplicate_rows"] / max(profile["rows"], 1) * 100
    total_outliers = sum(
        v.get("outliers_iqr", 0)
        for v in profile["variables"].values()
        if v["type"] == "numeric"
    )
    outlier_pct = total_outliers / max(profile["total_cells"], 1) * 100

    if completeness >= 98 and dup_pct == 0 and outlier_pct < 1:
        grade = "A"
    elif completeness >= 95 and dup_pct < 1 and outlier_pct < 3:
        grade = "B"
    elif completeness >= 90 and dup_pct < 5:
        grade = "C"
    else:
        grade = "D"

    profile["quality_grade"] = grade
    profile["quality_notes"] = []
    if completeness < 95:
        profile["quality_notes"].append(
            f"Completeness is {completeness}% — consider investigating missing values"
        )
    if dup_pct > 0:
        profile["quality_notes"].append(
            f"{profile['duplicate_rows']} duplicate rows detected ({dup_pct:.1f}%)"
        )
    if outlier_pct > 2:
        profile["quality_notes"].append(
            f"{total_outliers} statistical outliers detected across numeric columns"
        )

    logger.info(
        "Profiled: %s — Grade %s (%d rows, %.1f%% complete, %d outliers)",
        csv_path.name, grade, len(df), completeness, total_outliers,
    )

    return profile


def generate_profile_report(profiles: list[dict]) -> str:
    """Generate a Markdown quality report from profiles."""
    lines = [
        "# Data Quality Profile Report\n",
        f"**Generated:** {now_iso()}",
        "**Tool:** ocean-curation-pipeline-toolkit\n",
        "---\n",
    ]

    for p in profiles:
        lines.append(f"## {p['file']}\n")
        lines.append(f"**Rows:** {p['rows']} | **Columns:** {p['columns']} "
                      f"| **Completeness:** {p['completeness_pct']}% "
                      f"| **Quality Grade:** {p['quality_grade']}\n")

        if p.get("spatial_coverage"):
            sc = p["spatial_coverage"]
            lines.append(f"**Spatial Coverage:** "
                          f"[{sc['south_lat']}°N, {sc['north_lat']}°N] × "
                          f"[{sc['west_lon']}°E, {sc['east_lon']}°E] "
                          f"({sc['unique_positions']} unique positions)\n")

        if p.get("quality_notes"):
            lines.append("**Issues:**\n")
            for note in p["quality_notes"]:
                lines.append(f"- {note}")
            lines.append("")

        lines.append("### Variable Summary\n")
        lines.append("| Variable | Type | Valid | Missing | Notes |")
        lines.append("|----------|------|------:|--------:|-------|")

        for var_name, stats in p["variables"].items():
            vtype = stats["type"]
            valid = stats["valid"]
            missing = stats["missing"]
            notes = ""

            if vtype == "numeric":
                notes = (
                    f"range [{stats.get('min', '?')}..{stats.get('max', '?')}], "
                    f"μ={stats.get('mean', '?')}"
                )
                if stats.get("outliers_iqr", 0) > 0:
                    notes += f", **{stats['outliers_iqr']} outliers**"
            elif vtype == "temporal":
                notes = f"{stats.get('earliest', '?')} → {stats.get('latest', '?')}"
                if stats.get("large_gaps", 0) > 0:
                    notes += f", **{stats['large_gaps']} large gaps**"
            elif vtype == "categorical":
                notes = f"{stats.get('unique', '?')} unique values"

            lines.append(f"| {var_name} | {vtype} | {valid} | {missing} | {notes} |")

        lines.append("\n---\n")

    return "\n".join(lines)


def run_profile(config: dict):
    """Execute the data quality profile step."""
    submission_dir = get_submission_dir(config)
    subdirs = ensure_subdirs(submission_dir)
    logger = setup_logger(subdirs["logs"])

    logger.info("Generating data quality profile...")

    processed_dir = subdirs["processed"]
    profiles = []

    for csv_path in sorted(processed_dir.glob("*.csv")):
        profile = profile_file(csv_path, logger)
        profiles.append(profile)

    # Write JSON profile
    json_path = subdirs["logs"] / "data_quality_profile.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, default=str)

    # Write Markdown report
    md_path = subdirs["docs"] / "DATA_QUALITY_REPORT.md"
    md_content = generate_profile_report(profiles)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    log_provenance(subdirs["logs"], {
        "action": "quality_profile",
        "files_profiled": len(profiles),
        "grades": {p["file"]: p["quality_grade"] for p in profiles},
    })

    grades = " | ".join(f"{p['file']}: {p['quality_grade']}" for p in profiles)
    logger.info("Quality profile complete. Grades: %s", grades)
    click.echo(f"✓ Profile: {len(profiles)} files profiled — {grades}")
