"""Shared utilities for all pipeline commands."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logger(log_dir: Path, name: str = "ocean_curator") -> logging.Logger:
    """Configure logger to write to both console and log file."""
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured — just ensure file handler points to right dir
        return logger
    logger.setLevel(logging.DEBUG)

    # Console handler (INFO+)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(ch)

    # File handler (DEBUG+)
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / "processing.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_submission_dir(config: dict) -> Path:
    """Return the versioned submission output directory path."""
    base = Path(config.get("_project_root", "."))
    output_base = base / config.get("output", {}).get("base_dir", "output")
    version = config.get("dataset", {}).get("version", "0.0.1")
    return output_base / f"submission_v{version}"


def ensure_subdirs(submission_dir: Path) -> dict[str, Path]:
    """Create standard data curation submission subdirectories."""
    subdirs = {}
    for name in ("raw", "processed", "metadata", "docs", "logs"):
        d = submission_dir / name
        d.mkdir(parents=True, exist_ok=True)
        subdirs[name] = d
    return subdirs


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

HASH_ALGORITHM = "sha256"
CHUNK_SIZE = 8192


def sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def now_iso() -> str:
    """Current UTC timestamp in ISO 8601."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Provenance log
# ---------------------------------------------------------------------------


def log_provenance(log_dir: Path, entry: dict):
    """Append a JSON-lines provenance entry to provenance.jsonl."""
    entry["timestamp"] = now_iso()
    provenance_file = log_dir / "provenance.jsonl"
    with open(provenance_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def get_files_config(config: dict) -> list[dict]:
    """Return the list of file entries from config."""
    return config.get("files", [])


def get_quality_config(config: dict) -> dict:
    """Return quality/validation rules."""
    return config.get("quality", {})


def get_transform_config(config: dict) -> dict:
    """Return transformation rules."""
    return config.get("transform", {})
