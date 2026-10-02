"""Command line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from obloha import __version__


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(prog="obloha", description="Terminálové planetárium.")
    parser.add_argument("--version", action="version", version=f"obloha {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application."""
    build_parser().parse_args(argv)
    return 0
