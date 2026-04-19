"""
CLI entry point for ocean-curation-pipeline-toolkit.

Usage:
    ocean-curation-pipeline --config config.yaml init
    ocean-curation-pipeline --config config.yaml validate
    ocean-curation-pipeline --config config.yaml transform
    ocean-curation-pipeline --config config.yaml checksum
    ocean-curation-pipeline --config config.yaml metadata
    ocean-curation-pipeline --config config.yaml package

Or run all steps:
    ./run.sh
"""

import sys
from pathlib import Path

import click
import yaml

from ocean_curator import __version__
from ocean_curator.commands.init_cmd import run_init
from ocean_curator.commands.validate_cmd import run_validate
from ocean_curator.commands.transform_cmd import run_transform
from ocean_curator.commands.checksum_cmd import run_checksum
from ocean_curator.commands.metadata_cmd import run_metadata
from ocean_curator.commands.package_cmd import run_package
from ocean_curator.commands.netcdf_cmd import run_netcdf
from ocean_curator.commands.profile_cmd import run_profile


def load_config(config_path: str) -> dict:
    """Load and validate the pipeline configuration YAML."""
    path = Path(config_path)
    if not path.exists():
        click.echo(f"ERROR: Config file not found: {config_path}", err=True)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # Inject resolved paths
    config["_config_path"] = str(path.resolve())
    config["_project_root"] = str(path.resolve().parent)
    return config


@click.group()
@click.option(
    "--config", "-c",
    default="config.yaml",
    help="Path to pipeline configuration YAML.",
    type=click.Path(exists=False),
)
@click.version_option(version=__version__, prog_name="ocean-curation-pipeline")
@click.pass_context
def cli(ctx, config):
    """ocean-curation-pipeline-toolkit: FAIR data packaging for oceanographic datasets."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)


@cli.command()
@click.pass_context
def init(ctx):
    """Create submission scaffold and copy raw files."""
    run_init(ctx.obj["config"])


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate raw files for completeness and structural integrity."""
    run_validate(ctx.obj["config"])


@cli.command()
@click.pass_context
def transform(ctx):
    """Convert raw files to archive-ready formats."""
    run_transform(ctx.obj["config"])


@cli.command()
@click.pass_context
def checksum(ctx):
    """Generate SHA-256 checksums and manifest for all files."""
    run_checksum(ctx.obj["config"])


@cli.command()
@click.pass_context
def metadata(ctx):
    """Generate ISO 19115-2 XML metadata."""
    run_metadata(ctx.obj["config"])


@cli.command()
@click.pass_context
def netcdf(ctx):
    """Export processed data to CF-1.8 compliant NetCDF-4."""
    run_netcdf(ctx.obj["config"])


@cli.command()
@click.pass_context
def profile(ctx):
    """Generate data quality profile with statistics and outlier detection."""
    run_profile(ctx.obj["config"])


@cli.command(name="package")
@click.pass_context
def package_cmd(ctx):
    """Assemble final submission package with FAIR audit."""
    run_package(ctx.obj["config"])


@cli.command()
@click.pass_context
def run_all(ctx):
    """Execute full pipeline: init → validate → transform → profile → checksum → metadata → netcdf → package."""
    config = ctx.obj["config"]
    steps = [
        ("Initializing", run_init),
        ("Validating", run_validate),
        ("Transforming", run_transform),
        ("Profiling data quality", run_profile),
        ("Checksumming", run_checksum),
        ("Generating metadata", run_metadata),
        ("Exporting NetCDF", run_netcdf),
        ("Packaging", run_package),
    ]
    for label, func in steps:
        click.echo(f"\n{'='*60}")
        click.echo(f"  {label}...")
        click.echo(f"{'='*60}")
        func(config)
    click.echo(f"\n{'='*60}")
    click.echo("  Pipeline complete.")
    click.echo(f"{'='*60}")


if __name__ == "__main__":
    cli()
