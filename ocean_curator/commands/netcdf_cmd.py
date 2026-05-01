"""
netcdf command: Export processed data to CF-1.8 compliant NetCDF-4.

Produces a self-describing NetCDF file with:
- CF-1.8 and ACDD-1.3 global attributes
- Standard oceanographic variable names and units
- Coordinate reference system metadata
- Compression (zlib level 4) for storage efficiency
- Proper fill values and valid_range attributes

This is a critical data curation skill: many PIs submit CSV/Excel but
oceanographic archives increasingly require NetCDF format.
"""

import json
from pathlib import Path

import click
import numpy as np
import pandas as pd

from ocean_curator.utils import (
    get_submission_dir,
    ensure_subdirs,
    log_provenance,
    now_iso,
    setup_logger,
)

# CF standard name mapping for common oceanographic variables
CF_VARIABLE_MAP = {
    "temperature": {
        "standard_name": "sea_water_temperature",
        "long_name": "Sea Water Temperature",
        "units": "degree_Celsius",
        "valid_range": [-2.0, 40.0],
    },
    "salinity": {
        "standard_name": "sea_water_practical_salinity",
        "long_name": "Sea Water Practical Salinity",
        "units": "1",  # PSS-78 is dimensionless
        "valid_range": [0.0, 42.0],
        "comment": "Practical salinity on PSS-78 scale",
    },
    "dissolved_oxygen": {
        "standard_name": "mass_concentration_of_oxygen_in_sea_water",
        "long_name": "Dissolved Oxygen Concentration",
        "units": "mg L-1",
        "valid_range": [0.0, 15.0],
    },
    "ph": {
        "standard_name": "sea_water_ph_reported_on_total_scale",
        "long_name": "Sea Water pH (Total Scale)",
        "units": "1",
        "valid_range": [7.0, 9.0],
    },
    "total_alkalinity": {
        "standard_name": "sea_water_alkalinity_expressed_as_mole_equivalent",
        "long_name": "Total Alkalinity",
        "units": "umol kg-1",
        "valid_range": [2000.0, 2600.0],
    },
    "no3": {
        "standard_name": "mole_concentration_of_nitrate_in_sea_water",
        "long_name": "Nitrate Concentration",
        "units": "umol L-1",
        "valid_range": [0.0, 50.0],
    },
    "po4": {
        "standard_name": "mole_concentration_of_phosphate_in_sea_water",
        "long_name": "Phosphate Concentration",
        "units": "umol L-1",
        "valid_range": [0.0, 5.0],
    },
    "depth": {
        "standard_name": "depth",
        "long_name": "Depth Below Sea Surface",
        "units": "m",
        "positive": "down",
        "axis": "Z",
        "valid_range": [0.0, 11000.0],
    },
    "latitude": {
        "standard_name": "latitude",
        "long_name": "Latitude",
        "units": "degrees_north",
        "axis": "Y",
        "valid_range": [-90.0, 90.0],
    },
    "longitude": {
        "standard_name": "longitude",
        "long_name": "Longitude",
        "units": "degrees_east",
        "axis": "X",
        "valid_range": [-180.0, 180.0],
    },
}


def _match_cf_variable(col_name: str) -> dict | None:
    """Match a column name to a CF standard variable definition."""
    cl = col_name.lower().replace(" ", "_")
    for key, attrs in CF_VARIABLE_MAP.items():
        if key in cl:
            return attrs
    return None


def csv_to_netcdf(csv_path: Path, nc_path: Path, config: dict, logger) -> dict:
    """
    Convert a processed CSV to CF-1.8 compliant NetCDF-4.

    Returns provenance record.
    """
    try:
        import netCDF4
    except ImportError:
        logger.error("netCDF4 not installed. Run: pip install netCDF4")
        return {"error": "netCDF4 not installed"}

    df = pd.read_csv(csv_path)
    dataset_cfg = config.get("dataset", {})
    prov = {"input": csv_path.name, "output": nc_path.name, "variables": []}

    # Create NetCDF file
    ds = netCDF4.Dataset(str(nc_path), "w", format="NETCDF4")

    try:
        # ── Global attributes (ACDD-1.3) ─────────────────────────────
        ds.Conventions = "CF-1.8, ACDD-1.3"
        ds.title = dataset_cfg.get("title", "Untitled Dataset")
        ds.summary = dataset_cfg.get("abstract", "")
        ds.id = dataset_cfg.get("doi", "")
        ds.naming_authority = "org.griidc"
        ds.source = "in-situ observations"
        ds.processing_level = "quality-controlled"
        ds.institution = dataset_cfg.get("contact", {}).get("organization", "")
        ds.creator_name = dataset_cfg.get("contact", {}).get("individual_name", "")
        ds.creator_email = dataset_cfg.get("contact", {}).get("email", "")
        ds.creator_type = "person"
        # Publisher can be set in config or defaults to generic value
        ds.publisher_name = dataset_cfg.get("publisher", {}).get("name", "Scientific Data Repository")
        ds.publisher_url = dataset_cfg.get("publisher", {}).get("url", "")
        ds.publisher_type = "institution"
        ds.project = dataset_cfg.get("funding", {}).get("agency", "")
        ds.date_created = now_iso()
        ds.date_modified = now_iso()
        ds.date_metadata_modified = now_iso()
        ds.product_version = dataset_cfg.get("version", "1.0.0")
        ds.history = f"{now_iso()}: Converted from CSV to NetCDF-4 by ocean-curation-pipeline-toolkit"
        ds.featureType = "profile"  # CTD cast data is profile feature type
        ds.cdm_data_type = "Profile"

        # Spatial/temporal metadata
        lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
        lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
        time_col = next(
            (c for c in df.columns if any(k in c.lower() for k in ("date", "time"))),
            None,
        )

        if lat_col:
            ds.geospatial_lat_min = float(df[lat_col].min())
            ds.geospatial_lat_max = float(df[lat_col].max())
            ds.geospatial_lat_units = "degrees_north"
        if lon_col:
            ds.geospatial_lon_min = float(df[lon_col].min())
            ds.geospatial_lon_max = float(df[lon_col].max())
            ds.geospatial_lon_units = "degrees_east"
        if time_col:
            times = pd.to_datetime(df[time_col], errors="coerce").dropna()
            if len(times):
                ds.time_coverage_start = str(times.min().isoformat()) + "Z"
                ds.time_coverage_end = str(times.max().isoformat()) + "Z"

        depth_col = next((c for c in df.columns if "depth" in c.lower()), None)
        if depth_col:
            ds.geospatial_vertical_min = float(df[depth_col].min())
            ds.geospatial_vertical_max = float(df[depth_col].max())
            ds.geospatial_vertical_units = "m"
            ds.geospatial_vertical_positive = "down"

        # License
        lic = dataset_cfg.get("license", {})
        ds.license = lic.get("name", "CC-BY-4.0")

        # Keywords
        kw = dataset_cfg.get("keywords", {})
        all_kw = kw.get("theme", []) + kw.get("place", [])
        if all_kw:
            ds.keywords = ", ".join(all_kw)
            ds.keywords_vocabulary = "GCMD Science Keywords"

        # ── Dimensions ───────────────────────────────────────────────
        ds.createDimension("obs", len(df))

        # ── Variables ────────────────────────────────────────────────
        # String columns (station IDs, QC flags, etc.)
        str_cols = []
        num_cols = []
        for col in df.columns:
            if df[col].dtype == object:
                str_cols.append(col)
            else:
                num_cols.append(col)

        for col in num_cols:
            cf = _match_cf_variable(col)
            fill_val = -999.0

            var = ds.createVariable(
                col,
                "f8",
                ("obs",),
                zlib=True,
                complevel=4,
                fill_value=fill_val,
            )

            # Set CF attributes
            if cf:
                for attr_name, attr_val in cf.items():
                    if attr_name == "valid_range":
                        var.valid_range = np.array(attr_val, dtype="f8")
                    else:
                        setattr(var, attr_name, attr_val)
                prov["variables"].append({
                    "name": col,
                    "cf_standard_name": cf.get("standard_name", ""),
                })
            else:
                var.long_name = col
                prov["variables"].append({"name": col, "cf_standard_name": ""})

            # Write data
            data = pd.to_numeric(df[col], errors="coerce").values
            data = np.where(np.isnan(data), fill_val, data)
            var[:] = data

        # String variables
        for col in str_cols:
            var = ds.createVariable(col, str, ("obs",))
            var.long_name = col
            vals = df[col].fillna("").astype(str).values
            for i, v in enumerate(vals):
                var[i] = v

        logger.info(
            "NetCDF written: %s (%d obs, %d variables, %d CF-mapped)",
            nc_path.name,
            len(df),
            len(df.columns),
            sum(1 for v in prov["variables"] if v["cf_standard_name"]),
        )

    finally:
        ds.close()

    return prov


def run_netcdf(config: dict):
    """Execute the NetCDF export step."""
    submission_dir = get_submission_dir(config)
    subdirs = ensure_subdirs(submission_dir)
    logger = setup_logger(subdirs["logs"])

    logger.info("Exporting to CF-1.8 NetCDF-4...")

    processed_dir = subdirs["processed"]
    nc_dir = submission_dir / "netcdf"
    nc_dir.mkdir(exist_ok=True)

    all_prov = []
    failures: list[str] = []

    for csv_path in sorted(processed_dir.glob("*.csv")):
        nc_path = nc_dir / csv_path.with_suffix(".nc").name
        prov = csv_to_netcdf(csv_path, nc_path, config, logger)
        all_prov.append(prov)

        err = prov.get("error")
        if err:
            failures.append(f"{csv_path.name}: {err}")
            continue
        if not nc_path.is_file() or nc_path.stat().st_size == 0:
            failures.append(f"{csv_path.name}: NetCDF file missing or empty")
            continue

        log_provenance(subdirs["logs"], {
            "action": "netcdf_export",
            "input": csv_path.name,
            "output": nc_path.name,
        })

    # Write export summary
    summary_path = subdirs["logs"] / "netcdf_export.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_prov, f, indent=2, default=str)

    if failures:
        for msg in failures:
            logger.error("%s", msg)
        raise click.ClickException(
            "NetCDF export failed — " + "; ".join(failures) + ". "
            "Install netCDF4 in the same Python you use to run the pipeline "
            "(e.g. python3 -m pip install netCDF4)."
        )

    logger.info("NetCDF export complete. %d files created.", len(all_prov))
    click.echo(f"✓ NetCDF: {len(all_prov)} CF-1.8 files exported to netcdf/")
