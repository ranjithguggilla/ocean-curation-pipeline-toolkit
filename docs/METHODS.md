# Methods Report: ocean-curation-pipeline-toolkit

**Author:** Ranjith Guggilla  
**Affiliation:** Data Curation Professional  
**Date:** May 2026  
**Version:** 1.0.0

---

## 1. Purpose

This document describes the methods implemented in `ocean-curation-pipeline-toolkit`,
a Python/Bash pipeline that automates the preparation of oceanographic
datasets for archival submission to the Gulf of Mexico Research Initiative
oceanographic data repository and similar scientific data
repositories. The toolkit addresses a recurring challenge in research data
management: transforming heterogeneous raw data files from principal
investigators into standardized, FAIR-compliant submission packages with
machine-readable metadata.

## 2. Design Rationale

Data curators routinely receive datasets as ad-hoc Excel spreadsheets and
CSV files with inconsistent formatting. Common issues include:

- Mixed date/time formats within a single column
- Whitespace artifacts and leading/trailing spaces in station identifiers
- Non-standard header naming incompatible with CF (Climate and Forecast)
  conventions
- Missing or placeholder values without clear NA representation
- No accompanying metadata document or provenance trail
- No fixity information (checksums) for long-term integrity verification

Each issue, individually minor, compounds across hundreds of annual
submissions into significant curator effort. This toolkit encodes
institutional knowledge of these common problems into repeatable,
auditable processing steps.

## 3. Pipeline Architecture

The pipeline executes eight sequential stages, each producing documented
outputs in a versioned submission directory:

```
init → validate → transform → profile → checksum → metadata → netcdf → package
```

**3.1 Init.** Creates a versioned submission directory structure mirroring
the standard submission package format (`raw/`, `processed/`, `metadata/`, `docs/`,
`logs/`, `netcdf/`). Copies raw input files into `raw/` with SHA-256
checksums recorded at ingestion time. Writes an initial `manifest.json`
documenting file provenance.

**3.2 Validate.** Performs structural and semantic checks on raw files:
character encoding detection (using chardet); CSV/Excel parseability;
required column presence; geophysical value range validation against
configurable bounds (e.g., latitude 18°–31°N for Gulf of Mexico data);
duplicate row detection; merged-cell and hidden-sheet detection in Excel
workbooks. All results are written to `validation_report.json` with
per-check pass/fail status and diagnostic detail.

**3.3 Transform.** Normalizes raw data into archive-ready formats:
Excel-to-CSV conversion (UTF-8, Unix line endings); header normalization
to lowercase snake_case per CF naming conventions; timestamp
standardization to ISO 8601 (`YYYY-MM-DDThh:mm:ssZ`); coordinate
validation to decimal degrees (EPSG:4326); whitespace stripping.
Every transformation is logged with full provenance in
`provenance.jsonl` (JSON Lines format).

**3.4 Profile.** Generates a data quality report including per-variable
statistics (count, mean, standard deviation, quartiles), missing value
analysis, outlier detection using the interquartile range (IQR) method,
spatial coverage bounding box, temporal coverage span with gap detection,
and an overall quality grade (A through D). Outputs both machine-readable
JSON (`data_quality_profile.json`) and human-readable Markdown.

**3.5 Checksum.** Computes SHA-256 hashes for all files in the submission
directory, writing a BSD-format manifest (`checksums.sha256`) and
updating `manifest.json`. SHA-256 was selected per standard fixity
requirements and NDSA Levels of Digital Preservation guidelines.

**3.6 Metadata.** Generates ISO 19115-2:2009 XML metadata using a Jinja2
template engine. Spatial and temporal extents are auto-detected from
processed data files and merged with curator-provided values from
`config.yaml` (curator values take precedence). The generated XML includes
responsible party information, GCMD Science Keywords, platform and
instrument identifiers, data lineage with processing steps, distribution
and license information, and identifier references. Validation is
performed against the ISO 19139 XSD schema when network access is
available, falling back to structural validation (required element
presence) when offline.

**3.7 NetCDF.** Exports processed CSV data to CF-1.8 compliant NetCDF-4
files with zlib compression (level 4). Variables are mapped to CF
standard names where recognized (e.g., `temperature` → `sea_water_temperature`,
`salinity` → `sea_water_practical_salinity`). ACDD-1.3 global attributes
are populated from the pipeline configuration. This step bridges the
common PI submission format (CSV) with the scientific community's
preferred self-describing binary format.

**3.8 Package.** Assembles the final submission package: generates a
FAIR principle audit report (evaluating all 15 sub-principles), creates
a dataset README, writes a CHANGELOG, runs a final checksum pass over
all deliverables, and produces a compressed archive (`.tar.gz`).

## 4. Standards Compliance

| Standard | Scope | Implementation |
|----------|-------|----------------|
| ISO 19115-2:2009 | Geospatial metadata | Jinja2-rendered XML, XSD-validated |
| CF Conventions 1.8 | NetCDF variable naming | Standard name table lookup |
| ACDD 1.3 | NetCDF global attributes | Auto-populated from config |
| FAIR Principles | Data management | 15-point self-audit |
| SHA-256 | Data integrity | BSD-format checksum manifest |
| ISO 8601 | Timestamps | Enforced during transform |
| EPSG:4326 | Coordinate reference | Validated during transform |

## 5. Technology Stack

- **Python 3.10+**: pandas, lxml, Jinja2, netCDF4, chardet, click, xarray
- **Bash**: Pipeline orchestration script (`run.sh`)
- **YAML**: Pipeline configuration (`config.yaml`)
- **GitHub Actions**: CI pipeline running pytest and XML validation

## 6. Reproducibility

The pipeline is fully deterministic: given the same input files and
`config.yaml`, it produces byte-identical output (verified by checksum
comparison across runs). The `provenance.jsonl` log records every
processing action with timestamps, function identifiers, and parameter
values. The config snapshot included in each package captures the exact
configuration used.

## 7. Sample Data

The included sample data simulates a GOMECC-4 (Gulf of Mexico Ecosystems
and Carbon Cycle) cruise dataset with intentional quality issues:

- Mixed date/time formats across rows
- Whitespace artifacts in station identifiers
- Missing values in dissolved oxygen, pH, and nutrient columns
- Duplicate observation rows
- Empty trailing row
- Non-standard header naming with special characters

These issues are representative of real-world submissions encountered
during oceanographic data curation. The sample data generator
(`sample_data/generate_samples.py`) documents each intentional problem.

For production use, replace sample files with actual datasets from
NOAA NCEI or similar repositories, or directly from principal
investigators.

## 8. Limitations

- Schema validation requires network access to fetch OGC XSD schemas;
  offline operation falls back to structural validation only.
- The CF standard name mapping covers common oceanographic variables;
  domain-specific variables may require manual attribute assignment.
- Excel formula cells are evaluated by openpyxl rather than preserved;
  original formulas are not captured in provenance.
- The toolkit processes tabular data (CSV/Excel); binary formats
  (raw CTD .hex/.cnv, ADCP .000) require format-specific preprocessing
  outside this pipeline.

## 9. References

- ISO 19115-2:2009. *Geographic information — Metadata — Part 2:
  Extensions for imagery and gridded data.*
- Eaton, B., et al. (2024). *CF Conventions and Metadata, Version 1.11.*
  http://cfconventions.org
- Wilkinson, M.D., et al. (2016). The FAIR Guiding Principles for
  scientific data management and stewardship. *Scientific Data*, 3, 160018.

  https://data.griidc.org
- NDSA Levels of Digital Preservation, Version 2.0 (2019).
  https://ndsa.org/publications/levels-of-digital-preservation/
