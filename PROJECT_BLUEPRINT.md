# Project 1 Blueprint — `ocean-curation-pipeline-toolkit`

## FAIR Data Packaging Pipeline for Oceanographic Dataset Curation

---

## 1. Problem Statement

Scientific data repositories receive raw datasets from Principal Investigators in wildly
inconsistent formats: Excel files with merged cells, CSVs with non-standard headers, no
metadata, no checksums, no provenance documentation. A data curator's core job is
turning that mess into an archive-ready, FAIR-compliant submission package with
ISO 19115-2 XML metadata, SHA-256 fixity manifests, and standardized directory structures.

This tool automates that entire workflow end-to-end.

---

## 2. Architecture Overview

```
Raw PI Data (Excel/CSV/TSV)
        │
        ▼
┌────────────────────────────────────────────────────┐
│  ocean-curation-pipeline init                      │  ← Create project scaffold from config.yaml
└──────────────────────┬─────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────┐
│  ocean-curation-pipeline validate                  │  ← Check raw files: encoding, headers, types, gaps
└──────────────────────┬─────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────┐
│  ocean-curation-pipeline transform                 │  ← Convert to archive-ready formats (CSV→NetCDF, etc.)
└──────────────────────┬─────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────┐
│  ocean-curation-pipeline checksum                  │  ← SHA-256 every file, write checksums.sha256
└──────────────────────┬─────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────┐
│  ocean-curation-pipeline metadata                  │  ← Generate ISO 19115-2 XML from config + data
└──────────────────────┬─────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────┐
│  ocean-curation-pipeline package                   │  ← Assemble final submission directory + FAIR audit
└──────────────────────┬─────────────────────────────┘
           │
           ▼
  submission_v1.0.0/
  ├── raw/
  ├── processed/
  ├── metadata/
  │   └── iso19115-2.xml
  ├── docs/
  │   ├── README.md
  │   └── METHODS.md
  ├── logs/
  │   └── processing.log
  ├── manifest.json
  ├── checksums.sha256
  ├── FAIR_AUDIT.md
  └── CHANGELOG.md
```

---

## 3. Data Source Selection

### Primary: NOAA NCEI Water Quality Data

Use the **GOMECC-4** (Gulf of Mexico Ecosystems and Carbon Cycle) cruise dataset:
- URL: https://www.ncei.noaa.gov/access/ocean-carbon-acidification-data-system/
- Why: Gulf of Mexico = HRI geographic relevance. Real cruise data. Messy enough
  to demonstrate transformation skills. Publicly available.

### Alternative: Published Oceanographic Dataset
- Browse: https://www.ncei.noaa.gov/ or similar data repositories
- Pick any dataset with DOI to study the "finished product" structure
- Then find the original raw data (often linked in the metadata) to use as input

### What to download for sample_data/:
1. Go to oceanographic data repositories (NCEI, NOAA, etc.)
2. Download one small cruise dataset (< 50 MB)
3. Place raw files in `sample_data/raw/`
4. Document the source URL and access date in `sample_data/SOURCE.md`

---

## 4. Config YAML Specification

The `config.yaml` drives the entire pipeline. See `config.yaml` in the repo root
for the full template with comments.

Key sections:
- `dataset`: title, abstract, keywords, PI info, temporal/spatial extent
- `files`: list of raw input files with expected format and target format
- `metadata`: ISO 19115-2 field values
- `transform`: rules for each file conversion
- `quality`: validation rules (required columns, value ranges, etc.)

---

## 5. Module-by-Module Technical Specification

### 5.1 `ocean-curation-pipeline init`
**Purpose:** Create the submission scaffold directory and copy raw files.

**Logic:**
1. Read config.yaml
2. Create versioned output directory: `submission_v{version}/`
3. Create subdirectories: raw/, processed/, metadata/, docs/, logs/
4. Copy raw files from source paths into raw/
5. Initialize processing.log with timestamp, tool version, config hash
6. Write initial manifest.json with raw file inventory

**Key decisions:**
- Version comes from config.yaml `dataset.version` field
- If output dir exists, abort with error (no silent overwrite)
- Log every file copy with source path, destination, byte count

### 5.2 `ocean-curation-pipeline validate`
**Purpose:** Check raw files for completeness, encoding, structural issues.

**Checks to implement:**
- File exists and is readable
- File encoding is UTF-8 (or detect and flag non-UTF-8)
- CSV: consistent column count across rows, no completely empty rows
- Excel: identify sheets, warn about merged cells, formulas, hidden sheets
- Timestamps: parseable, consistent format, no future dates
- Coordinates: lat in [-90, 90], lon in [-180, 180]
- Required columns present (from config.yaml `quality.required_columns`)
- Value ranges (from config.yaml `quality.value_ranges`)
- No duplicate records (configurable key columns)

**Output:** `logs/validation_report.json` with pass/fail per check, per file.

### 5.3 `ocean-curation-pipeline transform`
**Purpose:** Convert raw files to archive-ready formats.

**Transformations:**
- Excel → CSV (one sheet per file, UTF-8, standard line endings)
- CSV header normalization (lowercase, underscores, no spaces)
- Timestamp standardization to ISO 8601
- Coordinate normalization to decimal degrees
- Unit standardization (document original and target units)
- Optional: CSV → CF-compliant NetCDF (using xarray)

**Provenance:** Each transformation writes a log entry:
```json
{
  "timestamp": "2026-05-13T14:30:00Z",
  "action": "header_normalize",
  "input_file": "raw/Station_Data (2).xlsx",
  "output_file": "processed/station_data.csv",
  "details": {"original_headers": [...], "normalized_headers": [...]}
}
```

### 5.4 `ocean-curation-pipeline checksum`
**Purpose:** Generate SHA-256 checksums for every file in the package.

**Logic:**
1. Walk all files in raw/, processed/, metadata/, docs/
2. Compute SHA-256 for each
3. Write `checksums.sha256` in BSD-style format:
   `SHA256 (relative/path/to/file) = <hash>`
4. Also write `manifest.json` with file inventory:
   ```json
   {
     "files": [
       {
         "path": "processed/station_data.csv",
         "sha256": "abc123...",
         "size_bytes": 45678,
         "format": "text/csv",
         "role": "processed_data"
       }
     ]
   }
   ```

### 5.5 `ocean-curation-pipeline metadata`
**Purpose:** Generate ISO 19115-2 XML metadata from config + data inspection.

**Logic:**
1. Read config.yaml metadata section
2. Auto-detect from data: temporal extent (min/max dates), spatial extent
   (bounding box from coordinates), variable names, units
3. Merge auto-detected values with config values (config wins on conflict)
4. Render ISO 19115-2 XML using Jinja2 template
5. Validate generated XML against ISO 19115-2 XSD schema
6. Write to metadata/iso19115-2.xml

**Critical fields to populate:**
- fileIdentifier, language, characterSet
- contact (PI info from config)
- dateStamp
- identificationInfo (title, abstract, keywords, extent)
- distributionInfo
- dataQualityInfo (lineage → processing steps)
- acquisitionInformation (instruments, platforms)

### 5.6 `ocean-curation-pipeline package`
**Purpose:** Final assembly, FAIR audit, and packaging.

**Logic:**
1. Verify all prior steps completed (check for required files)
2. Generate FAIR_AUDIT.md (see FAIR Scorecard section below)
3. Copy/generate docs/README.md from template
4. Generate CHANGELOG.md
5. Run final checksum pass (catches any files added during packaging)
6. Create .tar.gz archive of the submission directory
7. Print summary to console

---

## 6. FAIR Scorecard Specification

The FAIR audit prints a structured assessment:

```markdown
# FAIR Compliance Audit Report
Generated: 2026-05-13T14:30:00Z
Tool: ocean-curation-pipeline-toolkit v1.0.0

## Findable
- [✓] F1: Dataset has a globally unique identifier (DOI placeholder)
- [✓] F2: Rich metadata describes the dataset (ISO 19115-2 XML present)
- [✓] F3: Metadata includes the dataset identifier
- [✓] F4: Metadata is registered in a searchable resource (data repository catalog)

## Accessible
- [✓] A1: Dataset retrievable by identifier via standardized protocol
- [✓] A1.1: Protocol is open, free, universally implementable (HTTPS)
- [✓] A1.2: Protocol allows authentication where necessary
- [✓] A2: Metadata remains accessible even if data is no longer available

## Interoperable
- [✓] I1: Data uses formal, accessible, shared language (CSV/NetCDF)
- [✓] I2: Data uses vocabularies that follow FAIR principles (CF conventions)
- [✓] I3: Data includes qualified references to other data

## Reusable
- [✓] R1: Data has plurality of accurate, relevant attributes
- [✓] R1.1: Data released with clear, accessible usage license
- [✓] R1.2: Data associated with detailed provenance (processing log)
- [✓] R1.3: Data meets domain-relevant community standards (ISO 19115-2)

Overall Score: 14/14 principles addressed
```

Each check maps to a concrete artifact in the package. If something's missing,
the score drops and the report says exactly what to fix.

---

## 7. ISO 19115-2 XML Reference

### Key namespaces:
- gmd: http://www.isotc211.org/2005/gmd
- gmi: http://www.isotc211.org/2005/gmi (the "-2" extension for imagery/gridded)
- gco: http://www.isotc211.org/2005/gco
- gml: http://www.opengis.net/gml/3.2

### Schema validation:
The official XSD is at:
https://schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd
https://schemas.opengis.net/iso/19139/20070417/gmi/gmi.xsd

Download these for offline validation. The tool validates against them using lxml.

### Template approach:
Use a Jinja2 template (`ocean_curator/templates/iso19115_2.xml.j2`) with
placeholders for all dynamic fields. This is cleaner than building XML
programmatically and makes the structure auditable.

---

## 8. Testing Strategy

### Unit tests (pytest):
- `test_validate.py`: Feed known-good and known-bad CSVs, verify detection
- `test_transform.py`: Round-trip transform, verify losslessness
- `test_checksum.py`: Known file → known hash
- `test_metadata.py`: Generated XML validates against XSD
- `test_fair_audit.py`: Complete package scores 14/14, incomplete scores less

### Integration test:
- `test_full_pipeline.py`: Run entire pipeline on sample_data/, verify output
  structure matches expected directory tree

### CI (GitHub Actions):
- Run pytest on push
- Validate sample XML against XSD
- Lint with ruff
- Badge: "tests passing" + "ISO 19115-2 valid"

---

## 9. Dependencies

```
# requirements.txt
click>=8.0          # CLI framework
pyyaml>=6.0         # Config parsing
lxml>=4.9           # XML generation and XSD validation
jinja2>=3.1         # XML template rendering
pandas>=2.0         # Data manipulation
openpyxl>=3.1       # Excel reading
chardet>=5.0        # Encoding detection
xarray>=2024.0      # NetCDF output (optional)
netcdf4>=1.6        # NetCDF backend
pytest>=7.0         # Testing
ruff>=0.4           # Linting
```

---

## 10. Build Sequence (Step-by-Step)

### Day 1: Scaffold + Config
- [ ] Create repo, push initial structure
- [ ] Write config.yaml with all fields documented
- [ ] Implement `ocean-curation-pipeline init` command
- [ ] Download sample data, place in sample_data/

### Day 2: Validation
- [ ] Implement all validation checks
- [ ] Write validation report output
- [ ] Test with deliberately broken files

### Day 3: Transform
- [ ] Excel → CSV converter
- [ ] Header normalizer
- [ ] Timestamp standardizer
- [ ] Coordinate normalizer
- [ ] Provenance logger

### Day 4: Checksum + Manifest
- [ ] SHA-256 walker
- [ ] checksums.sha256 writer
- [ ] manifest.json generator
- [ ] Verification command (check existing checksums)

### Day 5: ISO 19115-2 Metadata
- [ ] Build Jinja2 template (the big one — budget 4+ hours)
- [ ] Config → template variable mapper
- [ ] Auto-detection of temporal/spatial extent from data
- [ ] XSD validation integration
- [ ] Download and cache XSD schemas locally

### Day 6: Package + FAIR Audit
- [ ] FAIR scorecard generator
- [ ] README template generator
- [ ] CHANGELOG generator
- [ ] .tar.gz archiver
- [ ] Final checksum pass

### Day 7: Polish
- [ ] Write all tests
- [ ] Set up GitHub Actions CI
- [ ] Write README.md
- [ ] Write METHODS.md (technical report)
- [ ] Record a 2-min demo (optional but high-impact)
