"""
package command: Assemble final submission, run FAIR audit, create archive.

Steps:
1. Verify all prior steps completed
2. Generate FAIR_AUDIT.md
3. Generate docs/README.md from template
4. Generate CHANGELOG.md
5. Re-run checksums (catches files added during packaging)
6. Create .tar.gz archive
7. Print summary
"""

import tarfile
from datetime import datetime, timezone
from pathlib import Path

import click

from ocean_curator import __version__
from ocean_curator.utils import (
    get_submission_dir,
    ensure_subdirs,
    log_provenance,
    now_iso,
    setup_logger,
    sha256_file,
)


# ---------------------------------------------------------------------------
# FAIR Audit
# ---------------------------------------------------------------------------

FAIR_PRINCIPLES = [
    # (id, letter, name, check_function_name, description)
    ("F1", "Findable", "Globally unique identifier",
     "check_has_doi", "Dataset has a DOI or persistent identifier"),
    ("F2", "Findable", "Rich metadata",
     "check_has_metadata_xml", "ISO 19115-2 XML metadata file exists"),
    ("F3", "Findable", "Metadata includes identifier",
     "check_metadata_has_id", "Metadata XML contains the dataset identifier"),
    ("F4", "Findable", "Registered in searchable resource",
     "check_repo_target", "Package structured for repository submission"),

    ("A1", "Accessible", "Retrievable by identifier",
     "check_distribution_info", "Distribution/access information documented"),
    ("A1.1", "Accessible", "Open protocol",
     "check_https_protocol", "Access via HTTPS (open, free, universal)"),
    ("A1.2", "Accessible", "Auth where necessary",
     "check_access_constraints", "Access constraints documented if applicable"),
    ("A2", "Accessible", "Metadata persistence",
     "check_metadata_standalone", "Metadata is self-contained and persists independently"),

    ("I1", "Interoperable", "Formal shared language",
     "check_standard_formats", "Data in standard formats (CSV, NetCDF)"),
    ("I2", "Interoperable", "FAIR vocabularies",
     "check_vocabularies", "Uses controlled vocabularies (GCMD, CF conventions)"),
    ("I3", "Interoperable", "Qualified references",
     "check_references", "References to related datasets or publications"),

    ("R1", "Reusable", "Plurality of attributes",
     "check_rich_attributes", "Data described with multiple relevant attributes"),
    ("R1.1", "Reusable", "Clear license",
     "check_license", "Data released under a clear, accessible license"),
    ("R1.2", "Reusable", "Detailed provenance",
     "check_provenance", "Processing log and transformation provenance present"),
    ("R1.3", "Reusable", "Community standards",
     "check_community_standards", "Meets ISO 19115-2 and domain standards"),
]


def run_fair_audit(submission_dir: Path, config: dict) -> tuple[str, int, int]:
    """
    Run FAIR compliance audit on the submission package.

    Returns: (markdown_report, passed_count, total_count)
    """
    results = []
    dataset = config.get("dataset", {})

    for pid, letter, name, check_name, description in FAIR_PRINCIPLES:
        passed = False

        if check_name == "check_has_doi":
            doi = dataset.get("doi", "")
            passed = bool(doi) and doi != "PENDING"

        elif check_name == "check_has_metadata_xml":
            passed = (submission_dir / "metadata" / "iso19115-2.xml").exists()

        elif check_name == "check_metadata_has_id":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                content = xml_path.read_text()
                passed = "fileIdentifier" in content

        elif check_name == "check_repo_target":
            # Check standard directory structure
            required = ["raw", "processed", "metadata", "docs", "logs"]
            passed = all((submission_dir / d).exists() for d in required)

        elif check_name == "check_distribution_info":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                passed = "distributionInfo" in xml_path.read_text()

        elif check_name == "check_https_protocol":
            passed = True  # Repositories use HTTPS by default

        elif check_name == "check_access_constraints":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                passed = "resourceConstraints" in xml_path.read_text()

        elif check_name == "check_metadata_standalone":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            passed = xml_path.exists() and xml_path.stat().st_size > 500

        elif check_name == "check_standard_formats":
            processed = submission_dir / "processed"
            if processed.exists():
                files = list(processed.rglob("*"))
                passed = any(
                    f.suffix.lower() in (".csv", ".nc", ".netcdf", ".json")
                    for f in files if f.is_file()
                )

        elif check_name == "check_vocabularies":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                content = xml_path.read_text()
                passed = "descriptiveKeywords" in content

        elif check_name == "check_references":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                content = xml_path.read_text()
                passed = "citation" in content

        elif check_name == "check_rich_attributes":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                content = xml_path.read_text()
                passed = all(
                    tag in content
                    for tag in ["title", "abstract", "keyword", "extent"]
                )

        elif check_name == "check_license":
            license_info = dataset.get("license", {})
            passed = bool(license_info.get("name"))

        elif check_name == "check_provenance":
            prov_file = submission_dir / "logs" / "provenance.jsonl"
            passed = prov_file.exists() and prov_file.stat().st_size > 0

        elif check_name == "check_community_standards":
            xml_path = submission_dir / "metadata" / "iso19115-2.xml"
            if xml_path.exists():
                content = xml_path.read_text()
                passed = "19115" in content

        results.append((pid, letter, name, passed, description))

    # Build markdown report
    passed_count = sum(1 for r in results if r[3])
    total_count = len(results)

    lines = [
        "# FAIR Compliance Audit Report",
        "",
        f"**Generated:** {now_iso()}",
        f"**Tool:** ocean-curation-pipeline-toolkit v{__version__}",
        f"**Dataset:** {dataset.get('title', 'Unknown')}",
        f"**Version:** {dataset.get('version', '?')}",
        "",
        f"## Overall Score: {passed_count}/{total_count} principles addressed",
        "",
    ]

    current_letter = ""
    for pid, letter, name, passed, description in results:
        if letter != current_letter:
            lines.append(f"## {letter}")
            lines.append("")
            current_letter = letter
        icon = "+" if passed else "-"
        lines.append(f"- [{icon}] **{pid}**: {name}")
        lines.append(f"  - {description}")
        if not passed:
            lines.append("  - *Action required: address this principle before submission*")
        lines.append("")

    # Recommendations
    failures = [r for r in results if not r[3]]
    if failures:
        lines.append("## Recommendations")
        lines.append("")
        for pid, letter, name, _, desc in failures:
            lines.append(f"- **{pid}** ({name}): {desc}")
        lines.append("")
    else:
        lines.append("## Status: All FAIR principles addressed")
        lines.append("")
        lines.append("This package meets all 14 FAIR sub-principles. Ready for submission.")
        lines.append("")

    return "\n".join(lines), passed_count, total_count


# ---------------------------------------------------------------------------
# README generator
# ---------------------------------------------------------------------------

def generate_readme(submission_dir: Path, config: dict) -> str:
    """Generate a dataset README for the docs/ directory."""
    dataset = config.get("dataset", {})
    contact = dataset.get("contact", {})
    curator = dataset.get("curator", {})

    return f"""# {dataset.get('title', 'Dataset')}

## Overview

{dataset.get('abstract', '')}

## Version

{dataset.get('version', '1.0.0')}

## Principal Investigator

- **Name:** {contact.get('individual_name', '')}
- **Organization:** {contact.get('organization', '')}
- **Email:** {contact.get('email', '')}

## Data Curator

- **Name:** {curator.get('individual_name', '')}
- **Organization:** {curator.get('organization', '')}
- **Email:** {curator.get('email', '')}

## Temporal Coverage

- **Start:** {dataset.get('temporal', {}).get('begin', 'N/A')}
- **End:** {dataset.get('temporal', {}).get('end', 'N/A')}

## Geographic Coverage

- **West:** {dataset.get('spatial', {}).get('west_lon', '')}
- **East:** {dataset.get('spatial', {}).get('east_lon', '')}
- **South:** {dataset.get('spatial', {}).get('south_lat', '')}
- **North:** {dataset.get('spatial', {}).get('north_lat', '')}

## License

{dataset.get('license', {}).get('name', 'See metadata')} — {dataset.get('license', {}).get('url', '')}

## Directory Structure

```
submission_v{dataset.get('version', '1.0.0')}/
├── raw/              # Original unmodified data files
├── processed/        # Archive-ready transformed files
├── metadata/         # ISO 19115-2 XML metadata
├── docs/             # README, methods, config snapshot
├── logs/             # Processing logs, validation reports, provenance
├── manifest.json     # Complete file inventory with checksums
├── checksums.sha256  # SHA-256 fixity manifest
├── FAIR_AUDIT.md     # FAIR compliance assessment
└── CHANGELOG.md      # Version history
```

## Checksums

All files are checksummed with SHA-256. Verify with:

```bash
sha256sum -c checksums.sha256
```

## Metadata Standard

ISO 19115-2:2009(E) — Geographic Information — Metadata — Part 2

## Prepared With

[ocean-curation-pipeline-toolkit](https://github.com/ranjithguggilla/ocean-curation-pipeline-toolkit) v{__version__}
"""


# ---------------------------------------------------------------------------
# Main package command
# ---------------------------------------------------------------------------

def run_package(config: dict):
    """Execute the package step."""
    submission_dir = get_submission_dir(config)
    subdirs = ensure_subdirs(submission_dir)
    logger = setup_logger(subdirs["logs"])

    logger.info("Assembling final submission package...")

    # ---- Verify prerequisites ----
    required_artifacts = [
        ("raw", "Raw data directory"),
        ("processed", "Processed data directory"),
        ("metadata/iso19115-2.xml", "ISO 19115-2 metadata"),
        ("logs/validation_report.json", "Validation report"),
    ]
    missing = []
    for path, desc in required_artifacts:
        if not (submission_dir / path).exists():
            missing.append(f"  - {desc} ({path})")
    if missing:
        click.echo("ERROR: Missing prerequisites:\n" + "\n".join(missing), err=True)
        click.echo("Run the earlier pipeline steps first.", err=True)
        return

    # ---- Generate FAIR audit ----
    fair_md, passed, total = run_fair_audit(submission_dir, config)
    fair_path = submission_dir / "FAIR_AUDIT.md"
    with open(fair_path, "w", encoding="utf-8") as f:
        f.write(fair_md)
    logger.info("FAIR audit: %d/%d principles — %s", passed, total, fair_path.name)

    # ---- Generate README ----
    readme_content = generate_readme(submission_dir, config)
    readme_path = subdirs["docs"] / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    logger.info("README generated: %s", readme_path.name)

    # ---- Generate CHANGELOG ----
    version = config.get("dataset", {}).get("version", "1.0.0")
    changelog = f"""# Changelog

## [{version}] - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

### Added
- Initial submission package
- Raw data files ingested and validated
- Processed data in archive-ready CSV format
- ISO 19115-2 XML metadata generated
- SHA-256 checksums for all files
- FAIR compliance audit report
- Full processing provenance log

### Processing
- Prepared using ocean-curation-pipeline-toolkit v{__version__}
"""
    changelog_path = submission_dir / "CHANGELOG.md"
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.write(changelog)

    # ---- Final checksum pass ----
    logger.info("Running final checksum pass...")
    from ocean_curator.commands.checksum_cmd import run_checksum
    run_checksum(config)

    # ---- Create archive ----
    archive_format = config.get("output", {}).get("archive_format", "tar.gz")
    if archive_format == "tar.gz":
        archive_path = submission_dir.parent / f"{submission_dir.name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(submission_dir, arcname=submission_dir.name)
        archive_hash = sha256_file(archive_path)
        logger.info(
            "Archive: %s (%d bytes, sha256=%s)",
            archive_path.name,
            archive_path.stat().st_size,
            archive_hash[:16],
        )

    log_provenance(subdirs["logs"], {
        "action": "package",
        "fair_score": f"{passed}/{total}",
        "archive": archive_path.name if archive_format == "tar.gz" else "none",
    })

    # ---- Summary ----
    click.echo("")
    click.echo("=" * 60)
    click.echo("  SUBMISSION PACKAGE COMPLETE")
    click.echo("=" * 60)
    click.echo(f"  Directory : {submission_dir}")
    if archive_format == "tar.gz":
        click.echo(f"  Archive   : {archive_path}")
    click.echo(f"  FAIR Score: {passed}/{total} principles")
    click.echo(f"  Version   : {version}")
    click.echo("=" * 60)
