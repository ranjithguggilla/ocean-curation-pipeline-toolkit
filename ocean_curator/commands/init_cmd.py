"""
init command: Create submission scaffold and copy raw files.

This is the first step of the pipeline. It:
1. Creates the versioned output directory structure
2. Copies raw files from source paths into raw/
3. Initializes the processing log
4. Writes an initial manifest with raw file inventory
"""

import json
import shutil
import sys
from pathlib import Path

import click
import yaml

from ocean_curator import __version__
from ocean_curator.utils import (
    get_files_config,
    get_submission_dir,
    ensure_subdirs,
    log_provenance,
    now_iso,
    setup_logger,
    sha256_file,
)


def run_init(config: dict):
    """Execute the init step."""
    submission_dir = get_submission_dir(config)

    # Safety: never silently overwrite
    if submission_dir.exists():
        click.echo(
            f"ERROR: Submission directory already exists: {submission_dir}\n"
            f"Remove it or bump dataset.version in config.yaml.",
            err=True,
        )
        sys.exit(1)

    # Create directory tree
    subdirs = ensure_subdirs(submission_dir)
    logger = setup_logger(subdirs["logs"])
    logger.info("ocean-curation-pipeline-toolkit v%s — init", __version__)
    logger.info("Submission directory: %s", submission_dir)

    # Compute config hash for reproducibility
    config_yaml = yaml.dump(config, default_flow_style=False)
    import hashlib
    config_hash = hashlib.sha256(config_yaml.encode()).hexdigest()[:16]
    logger.info("Config hash (first 16 chars): %s", config_hash)

    # Copy raw files
    project_root = Path(config["_project_root"])
    raw_manifest = []

    for file_entry in get_files_config(config):
        source = project_root / file_entry["source_path"]
        if not source.exists():
            logger.error("Raw file not found: %s", source)
            sys.exit(1)

        dest_name = source.name
        dest = subdirs["raw"] / dest_name
        shutil.copy2(source, dest)

        file_size = dest.stat().st_size
        file_hash = sha256_file(dest)
        logger.info(
            "Copied: %s → %s (%d bytes, sha256=%s)",
            source, dest.relative_to(submission_dir), file_size, file_hash[:16],
        )

        raw_manifest.append({
            "original_path": str(source),
            "archive_path": str(dest.relative_to(submission_dir)),
            "name": file_entry["name"],
            "format": file_entry["format"],
            "target_format": file_entry.get("target_format", file_entry["format"]),
            "description": file_entry.get("description", ""),
            "size_bytes": file_size,
            "sha256": file_hash,
            "role": "raw_data",
        })

    # Write initial manifest
    manifest = {
        "toolkit_version": __version__,
        "created": now_iso(),
        "config_hash": config_hash,
        "dataset_version": config["dataset"]["version"],
        "dataset_title": config["dataset"]["title"],
        "files": raw_manifest,
    }

    manifest_path = submission_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    logger.info("Manifest written: %s", manifest_path.name)

    # Log provenance
    log_provenance(subdirs["logs"], {
        "action": "init",
        "toolkit_version": __version__,
        "config_hash": config_hash,
        "files_copied": len(raw_manifest),
    })

    # Copy config into docs/ for reference
    config_dest = subdirs["docs"] / "config_snapshot.yaml"
    with open(config_dest, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)

    logger.info("Init complete. %d raw files staged.", len(raw_manifest))
    click.echo(f"✓ Initialized: {submission_dir}")
