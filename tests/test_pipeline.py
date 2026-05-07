"""
Test suite for ocean-curation-pipeline-toolkit.

Tests cover:
- Config loading
- File validation (encoding, structure, ranges)
- Header normalization
- Checksum computation
- ISO 19115-2 XML generation and validation
- FAIR audit scoring
- Full pipeline integration
"""

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from ocean_curator.utils import sha256_file
from ocean_curator.commands.transform_cmd import normalize_header


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_csv(tmp_dir):
    """Create a sample CSV file with oceanographic-style data."""
    data = {
        "Station": ["A1", "A2", "A3", "A4", "A5"],
        "Latitude": [27.5, 27.6, 27.7, 27.8, 27.9],
        "Longitude": [-96.5, -96.4, -96.3, -96.2, -96.1],
        "Depth (m)": [10.0, 25.0, 50.0, 100.0, 200.0],
        "Temperature (°C)": [28.5, 27.2, 22.1, 15.3, 8.7],
        "Salinity (PSU)": [35.1, 35.2, 35.5, 35.8, 35.9],
        "Date/Time": [
            "07/18/2021 08:30",
            "07/18/2021 10:15",
            "07/18/2021 12:00",
            "07/18/2021 14:30",
            "07/18/2021 16:00",
        ],
    }
    df = pd.DataFrame(data)
    path = tmp_dir / "station_data.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def sample_config(tmp_dir, sample_csv):
    """Create a minimal config for testing."""
    config = {
        "dataset": {
            "title": "Test Gulf of Mexico Water Quality Dataset",
            "abstract": "Test dataset for pipeline validation.",
            "version": "0.0.1-test",
            "language": "eng",
            "character_set": "utf8",
            "topic_category": "oceans",
            "progress": "completed",
            "contact": {
                "individual_name": "Test PI",
                "organization": "Test University",
                "role": "principalInvestigator",
                "email": "test@test.edu",
            },
            "curator": {
                "individual_name": "Test Curator",
                "organization": "Data Repository",
                "email": "curator@test.edu",
            },
            "temporal": {"begin": "2021-07-18", "end": "2021-08-15"},
            "spatial": {
                "west_lon": -97.0, "east_lon": -96.0,
                "south_lat": 27.0, "north_lat": 28.0,
            },
            "keywords": {
                "theme": ["ocean chemistry", "water quality"],
                "place": ["Gulf of Mexico"],
            },
            "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
            "doi": "10.xxxx/test",
        },
        "files": [{
            "name": "station_data.csv",
            "source_path": str(sample_csv),
            "format": "text/csv",
            "target_format": "text/csv",
        }],
        "transform": {
            "normalize_headers": True,
            "strip_whitespace": True,
            "standardize_timestamps": {"input_format": "%m/%d/%Y %H:%M"},
            "encoding": "utf-8",
            "line_ending": "unix",
        },
        "quality": {
            "required_columns": ["station", "latitude", "longitude"],
            "value_ranges": {
                "latitude": [-90.0, 90.0],
                "longitude": [-180.0, 180.0],
            },
        },
        "metadata": {
            "hierarchy_level": "dataset",
            "lineage": {
                "statement": "Test processing.",
                "process_steps": [
                    {"description": "Test step", "date_time": "2026-05-13", "processor": "test"}
                ],
            },
        },
        "output": {"base_dir": str(tmp_dir / "output")},
        "_project_root": str(tmp_dir),
        "_config_path": str(tmp_dir / "config.yaml"),
    }
    return config


# ---------------------------------------------------------------------------
# Unit tests: Header normalization
# ---------------------------------------------------------------------------

class TestHeaderNormalization:
    def test_basic(self):
        assert normalize_header("Station Name") == "station_name"

    def test_special_chars(self):
        assert normalize_header("Temperature (°C)") == "temperature_c"

    def test_hyphens_dots(self):
        assert normalize_header("salinity-psu.avg") == "salinity_psu_avg"

    def test_extra_spaces(self):
        assert normalize_header("  Depth (m)  ") == "depth_m"

    def test_multiple_underscores(self):
        assert normalize_header("lat___lon") == "lat_lon"

    def test_empty(self):
        assert normalize_header("") == ""


# ---------------------------------------------------------------------------
# Unit tests: Checksum
# ---------------------------------------------------------------------------

class TestChecksum:
    def test_known_hash(self, tmp_dir):
        """Verify SHA-256 against known value."""
        test_file = tmp_dir / "test.txt"
        content = b"Hello, Ocean Curator!\n"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        actual = sha256_file(test_file)
        assert actual == expected

    def test_empty_file(self, tmp_dir):
        """Empty file has the well-known SHA-256 of empty input."""
        test_file = tmp_dir / "empty.txt"
        test_file.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_file(test_file) == expected


# ---------------------------------------------------------------------------
# Unit tests: CSV validation
# ---------------------------------------------------------------------------

class TestCSVValidation:
    def test_valid_csv(self, sample_csv):
        """Sample CSV should be parseable."""
        df = pd.read_csv(sample_csv)
        assert len(df) == 5
        assert "Station" in df.columns

    def test_coordinate_ranges(self, sample_csv):
        """Coordinates should be within valid ranges."""
        df = pd.read_csv(sample_csv)
        assert df["Latitude"].between(-90, 90).all()
        assert df["Longitude"].between(-180, 180).all()

    def test_no_duplicates(self, sample_csv):
        """Sample data should have no duplicate rows."""
        df = pd.read_csv(sample_csv)
        assert not df.duplicated().any()


# ---------------------------------------------------------------------------
# Unit tests: ISO 19115-2 XML
# ---------------------------------------------------------------------------

class TestMetadataXML:
    def test_template_renders(self, sample_config):
        """ISO 19115-2 template should render without errors."""
        from ocean_curator.commands.metadata_cmd import render_iso19115

        import logging
        logger = logging.getLogger("test")

        extent = {
            "west_lon": -97.0, "east_lon": -96.0,
            "south_lat": 27.0, "north_lat": 28.0,
            "begin": "2021-07-18", "end": "2021-08-15",
        }

        xml_str = render_iso19115(sample_config, extent, logger)
        assert "gmi:MI_Metadata" in xml_str
        assert "fileIdentifier" in xml_str
        assert "Test Gulf of Mexico" in xml_str

    def test_xml_wellformed(self, sample_config):
        """Generated XML should be well-formed."""
        from lxml import etree
        from ocean_curator.commands.metadata_cmd import render_iso19115

        import logging
        logger = logging.getLogger("test")

        extent = {"west_lon": -97, "east_lon": -96, "south_lat": 27, "north_lat": 28}
        xml_str = render_iso19115(sample_config, extent, logger)

        # Should not raise
        doc = etree.fromstring(xml_str.encode("utf-8"))
        assert doc.tag.endswith("MI_Metadata")

    def test_required_elements_present(self, sample_config):
        """All ISO 19115-2 required elements should be present."""
        from lxml import etree
        from ocean_curator.commands.metadata_cmd import render_iso19115

        import logging
        logger = logging.getLogger("test")

        extent = {"west_lon": -97, "east_lon": -96, "south_lat": 27, "north_lat": 28}
        xml_str = render_iso19115(sample_config, extent, logger)
        doc = etree.fromstring(xml_str.encode("utf-8"))

        ns = {"gmd": "http://www.isotc211.org/2005/gmd"}
        for elem_name in ["fileIdentifier", "contact", "dateStamp", "identificationInfo"]:
            found = doc.find(f".//gmd:{elem_name}", ns)
            assert found is not None, f"Missing required element: {elem_name}"


# ---------------------------------------------------------------------------
# Integration test: Full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_init_creates_structure(self, sample_config):
        """Init should create the expected directory structure."""
        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.utils import get_submission_dir

        run_init(sample_config)

        sub_dir = get_submission_dir(sample_config)
        assert sub_dir.exists()
        for dirname in ("raw", "processed", "metadata", "docs", "logs"):
            assert (sub_dir / dirname).exists(), f"Missing: {dirname}"
        assert (sub_dir / "manifest.json").exists()

    def test_full_pipeline_produces_package(self, sample_config):
        """Full pipeline should produce a complete submission package."""
        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.commands.validate_cmd import run_validate
        from ocean_curator.commands.transform_cmd import run_transform
        from ocean_curator.commands.checksum_cmd import run_checksum
        from ocean_curator.commands.metadata_cmd import run_metadata
        from ocean_curator.commands.netcdf_cmd import run_netcdf
        from ocean_curator.commands.profile_cmd import run_profile
        from ocean_curator.commands.package_cmd import run_package
        from ocean_curator.utils import get_submission_dir

        # Run all steps
        run_init(sample_config)
        run_validate(sample_config)
        run_transform(sample_config)
        run_profile(sample_config)
        run_checksum(sample_config)
        run_metadata(sample_config)
        run_netcdf(sample_config)
        run_package(sample_config)

        sub_dir = get_submission_dir(sample_config)

        # Check all expected outputs exist
        assert (sub_dir / "metadata" / "iso19115-2.xml").exists()
        assert (sub_dir / "checksums.sha256").exists()
        assert (sub_dir / "manifest.json").exists()
        assert (sub_dir / "FAIR_AUDIT.md").exists()
        assert (sub_dir / "CHANGELOG.md").exists()
        assert (sub_dir / "docs" / "README.md").exists()

        # Check manifest has files
        with open(sub_dir / "manifest.json") as f:
            manifest = json.load(f)
        assert manifest["total_files"] > 0

        # Check FAIR audit passes most principles
        fair_content = (sub_dir / "FAIR_AUDIT.md").read_text()
        assert "[+]" in fair_content


# ---------------------------------------------------------------------------
# NetCDF export tests
# ---------------------------------------------------------------------------

class TestNetCDFExport:
    def test_netcdf_creates_files(self, sample_config):
        """NetCDF export should create .nc files from processed CSVs."""
        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.commands.transform_cmd import run_transform
        from ocean_curator.commands.netcdf_cmd import run_netcdf
        from ocean_curator.utils import get_submission_dir

        run_init(sample_config)
        run_transform(sample_config)
        run_netcdf(sample_config)

        sub_dir = get_submission_dir(sample_config)
        nc_dir = sub_dir / "netcdf"
        assert nc_dir.exists()
        nc_files = list(nc_dir.glob("*.nc"))
        assert len(nc_files) > 0, "No NetCDF files generated"

    def test_netcdf_has_cf_attributes(self, sample_config):
        """Generated NetCDF should have CF-1.8 Conventions attribute."""
        import netCDF4

        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.commands.transform_cmd import run_transform
        from ocean_curator.commands.netcdf_cmd import run_netcdf
        from ocean_curator.utils import get_submission_dir

        run_init(sample_config)
        run_transform(sample_config)
        run_netcdf(sample_config)

        sub_dir = get_submission_dir(sample_config)
        nc_files = list((sub_dir / "netcdf").glob("*.nc"))
        ds = netCDF4.Dataset(str(nc_files[0]))
        assert "CF-1.8" in ds.Conventions
        assert hasattr(ds, "title")
        ds.close()

    def test_netcdf_cf_standard_names(self, sample_config):
        """NetCDF variables with recognized names should have CF standard_name."""
        import netCDF4

        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.commands.transform_cmd import run_transform
        from ocean_curator.commands.netcdf_cmd import run_netcdf
        from ocean_curator.utils import get_submission_dir

        run_init(sample_config)
        run_transform(sample_config)
        run_netcdf(sample_config)

        sub_dir = get_submission_dir(sample_config)
        nc_files = list((sub_dir / "netcdf").glob("*.nc"))
        ds = netCDF4.Dataset(str(nc_files[0]))

        cf_mapped = []
        for vname in ds.variables:
            v = ds.variables[vname]
            if hasattr(v, "standard_name"):
                cf_mapped.append(vname)

        ds.close()
        assert len(cf_mapped) >= 3, f"Expected >=3 CF-mapped variables, got {len(cf_mapped)}"


# ---------------------------------------------------------------------------
# Data quality profile tests
# ---------------------------------------------------------------------------

class TestDataProfile:
    def test_profile_creates_outputs(self, sample_config):
        """Profile should create JSON and Markdown quality reports."""
        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.commands.transform_cmd import run_transform
        from ocean_curator.commands.profile_cmd import run_profile
        from ocean_curator.utils import get_submission_dir

        run_init(sample_config)
        run_transform(sample_config)
        run_profile(sample_config)

        sub_dir = get_submission_dir(sample_config)
        assert (sub_dir / "logs" / "data_quality_profile.json").exists()
        assert (sub_dir / "docs" / "DATA_QUALITY_REPORT.md").exists()

    def test_profile_has_quality_grade(self, sample_config):
        """Profile should assign a quality grade to each file."""
        from ocean_curator.commands.init_cmd import run_init
        from ocean_curator.commands.transform_cmd import run_transform
        from ocean_curator.commands.profile_cmd import run_profile
        from ocean_curator.utils import get_submission_dir

        run_init(sample_config)
        run_transform(sample_config)
        run_profile(sample_config)

        sub_dir = get_submission_dir(sample_config)
        with open(sub_dir / "logs" / "data_quality_profile.json") as f:
            profiles = json.load(f)

        for p in profiles:
            assert "quality_grade" in p
            assert p["quality_grade"] in ("A", "B", "C", "D")
            assert "completeness_pct" in p

    def test_profile_numeric_stats(self):
        """Numeric profiler should compute correct statistics."""
        from ocean_curator.commands.profile_cmd import profile_numeric

        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 100.0])  # 100 is an outlier
        stats = profile_numeric(s)
        assert stats["type"] == "numeric"
        assert stats["valid"] == 6
        assert stats["missing"] == 0
        assert stats["outliers_iqr"] >= 1  # 100 should be flagged
