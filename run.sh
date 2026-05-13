#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ocean-curation-pipeline-toolkit — Full Pipeline Driver Script
# ═══════════════════════════════════════════════════════════════════════
#
# Usage:
#   ./run.sh                    # Run with default config.yaml
#   ./run.sh /path/to/my.yaml   # Run with custom config
#
# Pipeline steps:
#   1. init       — Create submission scaffold, copy raw files
#   2. validate   — Check encoding, structure, ranges, duplicates
#   3. transform  — Normalize headers, timestamps, coordinates
#   4. profile    — Generate data quality statistics and grade
#   5. checksum   — Compute SHA-256 hashes for all files
#   6. metadata   — Render ISO 19115-2 XML with auto-detected extent
#   7. netcdf     — Export to CF-1.8 compliant NetCDF-4
#   8. package    — FAIR audit, README, CHANGELOG, tar.gz archive
#
# Requirements:
#   - Python 3.10+ with dependencies (pip install -e ".[dev]")
#   - Bash 4+
#
# Exit codes:
#   0  — Pipeline completed successfully
#   1  — Pipeline failed at some step
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
CONFIG="${1:-config.yaml}"
# Prefer python3 so ./run.sh uses the same interpreter users install with
# (pip install -e ".[dev]" / python3 -m pip ...). Plain "python" may be a
# different version (e.g. 3.13 vs 3.11) without netCDF4 installed.
if command -v python3 &> /dev/null; then
    PYTHON=(python3)
elif command -v python &> /dev/null; then
    PYTHON=(python)
else
    PYTHON=()
fi
TOOL="${PYTHON[0]:-python3} -m griidc_pack"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'  # No Color

# ── Preflight checks ────────────────────────────────────────────────
if [[ ! -f "$CONFIG" ]]; then
    echo -e "${RED}ERROR: Config file not found: $CONFIG${NC}"
    echo "Usage: $0 [config.yaml]"
    exit 1
fi

if [[ ${#PYTHON[@]} -eq 0 ]]; then
    echo -e "${RED}ERROR: python3 or python not found in PATH${NC}"
    exit 1
fi

# Verify the package is installed (same interpreter as pipeline steps)
if ! "${PYTHON[0]}" -c "import griidc_pack" 2>/dev/null; then
    echo -e "${YELLOW}Package not installed. Installing...${NC}"
    "${PYTHON[0]}" -m pip install -e ".[dev]" --quiet
fi

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║         ocean-curation-pipeline-toolkit — Pipeline Runner    ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  Config : $CONFIG"
echo "║  Date   : $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "║  Host   : $(hostname)"
echo "║  Python : $("${PYTHON[0]}" --version 2>&1)"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Pipeline execution ───────────────────────────────────────────────
STEPS=(
    "init:Create submission scaffold"
    "validate:Validate raw files"
    "transform:Normalize data formats"
    "profile:Generate quality profile"
    "checksum:Compute SHA-256 hashes"
    "metadata:Generate ISO 19115-2 XML"
    "netcdf:Export CF-1.8 NetCDF-4"
    "package:Assemble submission package"
)

TOTAL=${#STEPS[@]}
CURRENT=0
START_TIME=$(date +%s)

for step_entry in "${STEPS[@]}"; do
    IFS=':' read -r step_cmd step_desc <<< "$step_entry"
    CURRENT=$((CURRENT + 1))

    echo -e "${CYAN}[${CURRENT}/${TOTAL}] ${step_desc}...${NC}"

    if $TOOL -c "$CONFIG" "$step_cmd"; then
        echo -e "${GREEN}  ✓ ${step_desc} — done${NC}"
    else
        echo -e "${RED}  ✗ ${step_desc} — FAILED${NC}"
        echo -e "${RED}Pipeline aborted at step ${CURRENT}/${TOTAL}.${NC}"
        exit 1
    fi

    echo ""
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   PIPELINE COMPLETE                         ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  Steps     : ${TOTAL}/${TOTAL} successful"
echo "║  Elapsed   : ${ELAPSED}s"
echo "║  Config    : ${CONFIG}"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "Output directory:"
ls -la output/ 2>/dev/null || echo "  (check config for output location)"
