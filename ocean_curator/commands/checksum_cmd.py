"""
checksum command: Generate SHA-256 checksums and file manifest.

Produces:
- checksums.sha256: BSD-format checksum file for all data/metadata files
- Updates manifest.json with complete file inventory including hashes
"""

import json
import mimetypes

import click

from ocean_curator.utils import (
    get_submission_dir,
    ensure_subdirs,
    log_provenance,
    now_iso,
    setup_logger,
    sha256_file,
)

# Directories to include in checksumming
CHECKSUM_DIRS = ("raw", "processed", "metadata", "docs")

# Files to skip (we generate these, not checksum them)
SKIP_FILES = {"checksums.sha256", "manifest.json", "FAIR_AUDIT.md"}


def guess_role(relpath: str) -> str:
    """Assign a semantic role based on directory."""
    if relpath.startswith("raw/"):
        return "raw_data"
    elif relpath.startswith("processed/"):
        return "processed_data"
    elif relpath.startswith("metadata/"):
        return "metadata"
    elif relpath.startswith("docs/"):
        return "documentation"
    elif relpath.startswith("logs/"):
        return "provenance"
    return "other"


def run_checksum(config: dict):
    """Execute the checksum step."""
    submission_dir = get_submission_dir(config)
    subdirs = ensure_subdirs(submission_dir)
    logger = setup_logger(subdirs["logs"])

    logger.info("Computing SHA-256 checksums...")

    checksum_lines = []
    manifest_files = []

    for dir_name in CHECKSUM_DIRS:
        target_dir = submission_dir / dir_name
        if not target_dir.exists():
            continue

        for filepath in sorted(target_dir.rglob("*")):
            if not filepath.is_file():
                continue
            if filepath.name in SKIP_FILES:
                continue

            relpath = str(filepath.relative_to(submission_dir))
            digest = sha256_file(filepath)
            size = filepath.stat().st_size
            mime = mimetypes.guess_type(str(filepath))[0] or "application/octet-stream"

            # BSD-style checksum line
            checksum_lines.append(f"SHA256 ({relpath}) = {digest}")

            manifest_files.append({
                "path": relpath,
                "sha256": digest,
                "size_bytes": size,
                "format": mime,
                "role": guess_role(relpath),
            })

            logger.debug("Checksum: %s → %s", relpath, digest[:16])

    # Also checksum log files
    for filepath in sorted(subdirs["logs"].rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.name in SKIP_FILES:
            continue
        relpath = str(filepath.relative_to(submission_dir))
        digest = sha256_file(filepath)
        size = filepath.stat().st_size
        mime = mimetypes.guess_type(str(filepath))[0] or "text/plain"
        checksum_lines.append(f"SHA256 ({relpath}) = {digest}")
        manifest_files.append({
            "path": relpath,
            "sha256": digest,
            "size_bytes": size,
            "format": mime,
            "role": "provenance",
        })

    # Write checksums.sha256
    checksum_path = submission_dir / "checksums.sha256"
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(checksum_lines)) + "\n")
    logger.info("Written: %s (%d entries)", checksum_path.name, len(checksum_lines))

    # Update manifest.json
    manifest_path = submission_dir / "manifest.json"
    existing_manifest = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            existing_manifest = json.load(f)

    existing_manifest["files"] = manifest_files
    existing_manifest["checksum_generated"] = now_iso()
    existing_manifest["total_files"] = len(manifest_files)
    existing_manifest["total_bytes"] = sum(f["size_bytes"] for f in manifest_files)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(existing_manifest, f, indent=2, default=str)
    logger.info("Updated: %s", manifest_path.name)

    log_provenance(subdirs["logs"], {
        "action": "checksum",
        "files_checksummed": len(checksum_lines),
        "algorithm": "SHA-256",
    })

    click.echo(f"✓ Checksummed: {len(checksum_lines)} files")
