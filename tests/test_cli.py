"""Tests for the CLI interface."""

import subprocess
import sys

import pytest


def test_cli_stats_runs():
    """smart-search stats runs without error."""
    result = subprocess.run(
        [sys.executable, "-m", "smart_search.cli", "stats"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0


def test_cli_config_show_runs():
    """smart-search config show runs without error."""
    result = subprocess.run(
        [sys.executable, "-m", "smart_search.cli", "config", "show"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0


def test_cli_watch_list_runs():
    """smart-search watch list runs without error."""
    result = subprocess.run(
        [sys.executable, "-m", "smart_search.cli", "watch", "list"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0


def test_cli_help():
    """smart-search --help shows usage."""
    result = subprocess.run(
        [sys.executable, "-m", "smart_search.cli", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "smart" in result.stdout.lower()
