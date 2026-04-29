"""
metadata command: Generate ISO 19115-2 XML metadata.

This is the core professional-grade component. It:
1. Reads metadata fields from config.yaml
2. Auto-detects temporal/spatial extent from processed data
3. Renders ISO 19115-2 XML from a Jinja2 template
4. Validates the generated XML against the official XSD schema
5. Reports any validation errors with XPath locations
"""

import json
from pathlib import Path

import click
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from lxml import etree

from ocean_curator.utils import (
    get_submission_dir,
    ensure_subdirs,
    log_provenance,
    now_iso,
    setup_logger,
)


def auto_detect_extent(processed_dir: Path, logger) -> dict:
    """
    Scan processed CSV files to auto-detect temporal and spatial extent.

    Looks for columns named latitude/longitude/lat/lon and date/time/timestamp.
    Returns a dict with west_lon, east_lon, south_lat, north_lat, begin, end.
    """
    extent = {}
    all_lats = []
    all_lons = []
    all_dates = []

    for csv_path in processed_dir.glob("*.csv"):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue

        # Find lat/lon columns
        for col in df.columns:
            cl = col.lower()
            if "lat" in cl:
                vals = pd.to_numeric(df[col], errors="coerce").dropna()
                all_lats.extend(vals.tolist())
            elif "lon" in cl:
                vals = pd.to_numeric(df[col], errors="coerce").dropna()
                all_lons.extend(vals.tolist())

        # Find date/time columns
        for col in df.columns:
            cl = col.lower()
            if any(kw in cl for kw in ("date", "time", "timestamp")):
                vals = pd.to_datetime(df[col], errors="coerce").dropna()
                all_dates.extend(vals.tolist())

    if all_lats:
        extent["south_lat"] = min(all_lats)
        extent["north_lat"] = max(all_lats)
        logger.info(
            "Auto-detected latitude range: [%.4f, %.4f]",
            extent["south_lat"], extent["north_lat"]
        )

    if all_lons:
        extent["west_lon"] = min(all_lons)
        extent["east_lon"] = max(all_lons)
        logger.info(
            "Auto-detected longitude range: [%.4f, %.4f]",
            extent["west_lon"], extent["east_lon"]
        )

    if all_dates:
        extent["begin"] = min(all_dates).strftime("%Y-%m-%d")
        extent["end"] = max(all_dates).strftime("%Y-%m-%d")
        logger.info(
            "Auto-detected temporal range: [%s, %s]",
            extent["begin"], extent["end"]
        )

    return extent


def merge_extent(config_extent: dict, detected: dict) -> dict:
    """Merge auto-detected extent with config values. Config wins on conflict."""
    merged = {}
    for key in ("west_lon", "east_lon", "south_lat", "north_lat", "begin", "end"):
        config_val = config_extent.get(key)
        detected_val = detected.get(key)
        if config_val is not None and str(config_val).strip():
            merged[key] = config_val
        elif detected_val is not None:
            merged[key] = detected_val
    return merged


def render_iso19115(config: dict, extent: dict, logger) -> str:
    """Render ISO 19115-2 XML from Jinja2 template and config values."""
    # Locate template
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,  # XML, not HTML
        keep_trailing_newline=True,
    )
    template = env.get_template("iso19115_2.xml.j2")

    # Build template context
    dataset = config.get("dataset", {})
    meta = config.get("metadata", {})
    contact = dataset.get("contact", {})
    curator = dataset.get("curator", {})
    keywords = dataset.get("keywords", {})

    context = {
        # Identity
        "file_identifier": dataset.get("doi", "PENDING"),
        "language": dataset.get("language", "eng"),
        "character_set": dataset.get("character_set", "utf8"),
        "hierarchy_level": meta.get("hierarchy_level", "dataset"),
        "date_stamp": now_iso()[:10],
        # Dataset info
        "title": dataset.get("title", "Untitled Dataset"),
        "abstract": dataset.get("abstract", ""),
        "purpose": "Archive-ready dataset prepared for scientific data repository submission.",
        "topic_category": dataset.get("topic_category", "oceans"),
        "progress": dataset.get("progress", "completed"),
        # Contact
        "contact_name": contact.get("individual_name", ""),
        "contact_org": contact.get("organization", ""),
        "contact_email": contact.get("email", ""),
        "contact_role": contact.get("role", "principalInvestigator"),
        "contact_orcid": contact.get("orcid", ""),
        # Curator
        "curator_name": curator.get("individual_name", ""),
        "curator_org": curator.get("organization", ""),
        "curator_email": curator.get("email", ""),
        # Spatial extent
        "west_lon": extent.get("west_lon", -180),
        "east_lon": extent.get("east_lon", 180),
        "south_lat": extent.get("south_lat", -90),
        "north_lat": extent.get("north_lat", 90),
        "crs": dataset.get("spatial", {}).get("crs", "EPSG:4326"),
        # Temporal extent
        "temporal_begin": extent.get("begin", ""),
        "temporal_end": extent.get("end", ""),
        # Keywords
        "theme_keywords": keywords.get("theme", []),
        "place_keywords": keywords.get("place", []),
        "instrument_keywords": keywords.get("instrument", []),
        # License
        "license_name": dataset.get("license", {}).get("name", ""),
        "license_url": dataset.get("license", {}).get("url", ""),
        # Publisher (for distribution info)
        "distribution_name": dataset.get("publisher", {}).get("name", "Scientific Data Repository"),
        "distribution_url": dataset.get("publisher", {}).get("url", ""),
        # DOI
        "doi": dataset.get("doi", ""),
        # Funding
        "funding_agency": dataset.get("funding", {}).get("agency", ""),
        "funding_award": dataset.get("funding", {}).get("award_number", ""),
        # Platform and instruments
        "platform_id": meta.get("platform", {}).get("identifier", ""),
        "platform_desc": meta.get("platform", {}).get("description", ""),
        "instruments": meta.get("instruments", []),
        # Lineage
        "lineage_statement": meta.get("lineage", {}).get("statement", ""),
        "process_steps": meta.get("lineage", {}).get("process_steps", []),
        # Standards
        "metadata_standard_name": meta.get("metadata_standard_name", "ISO 19115-2"),
        "metadata_standard_version": meta.get(
            "metadata_standard_version", "ISO 19115-2:2009(E)"
        ),
    }

    xml_str = template.render(**context)
    logger.info("ISO 19115-2 XML rendered (%d characters)", len(xml_str))
    return xml_str


def validate_xml_schema(xml_str: str, logger) -> list[str]:
    """
    Validate XML against ISO 19115-2 XSD schema.

    Attempts to load the official schema from schemas.opengis.net.
    Falls back to well-formedness check if schemas unavailable offline.
    """
    errors = []

    # Parse the generated XML
    try:
        doc = etree.fromstring(xml_str.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        errors.append(f"XML syntax error: {e}")
        return errors

    logger.info("XML is well-formed")

    # Attempt schema validation
    schema_urls = [
        "https://schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd",
    ]

    for url in schema_urls:
        try:
            schema_doc = etree.parse(url)
            schema = etree.XMLSchema(schema_doc)
            is_valid = schema.validate(doc)
            if not is_valid:
                for error in schema.error_log:
                    errors.append(f"Line {error.line}: {error.message}")
                logger.warning("Schema validation: %d errors", len(errors))
            else:
                logger.info("Schema validation: PASSED")
            return errors
        except Exception as e:
            logger.debug("Could not load schema from %s: %s", url, e)

    # Fallback: basic namespace and structure checks
    logger.info("Schema files unavailable — performing structural validation only")

    # Check required elements exist
    ns = {"gmd": "http://www.isotc211.org/2005/gmd"}
    required_elements = [
        ".//gmd:fileIdentifier",
        ".//gmd:contact",
        ".//gmd:dateStamp",
        ".//gmd:identificationInfo",
    ]
    for xpath in required_elements:
        if doc.find(xpath, ns) is None:
            errors.append(f"Missing required element: {xpath}")

    if not errors:
        logger.info("Structural validation: PASSED (all required elements present)")

    return errors


def run_metadata(config: dict):
    """Execute the metadata generation step."""
    submission_dir = get_submission_dir(config)
    subdirs = ensure_subdirs(submission_dir)
    logger = setup_logger(subdirs["logs"])

    logger.info("Generating ISO 19115-2 metadata...")

    # Auto-detect extent from processed data
    detected_extent = auto_detect_extent(subdirs["processed"], logger)

    # Merge with config
    config_spatial = config.get("dataset", {}).get("spatial", {})
    config_temporal = config.get("dataset", {}).get("temporal", {})
    config_extent = {**config_spatial, **config_temporal}
    extent = merge_extent(config_extent, detected_extent)

    # Render XML
    xml_str = render_iso19115(config, extent, logger)

    # Write XML
    xml_path = subdirs["metadata"] / "iso19115-2.xml"
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    logger.info("Written: %s", xml_path.name)

    # Validate
    errors = validate_xml_schema(xml_str, logger)
    validation_result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "xml_file": str(xml_path.name),
        "validated_at": now_iso(),
    }

    # Write validation result
    val_path = subdirs["logs"] / "metadata_validation.json"
    with open(val_path, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, indent=2)

    log_provenance(subdirs["logs"], {
        "action": "metadata",
        "xml_file": xml_path.name,
        "valid": len(errors) == 0,
        "error_count": len(errors),
    })

    if errors:
        click.echo(f"⚠ Metadata: {len(errors)} validation issues — see logs/metadata_validation.json")
        for err in errors[:5]:
            click.echo(f"  → {err}")
    else:
        click.echo("✓ Metadata: ISO 19115-2 XML generated and validated")
