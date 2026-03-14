"""Tests for the CLI interface."""

import subprocess
import sys
from unittest.mock import patch

import pytest

from smart_search.cli import main


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


def test_cli_serve_subcommand_exists():
    """smart-search serve --help shows serve options."""
    result = subprocess.run(
        [sys.executable, "-m", "smart_search.cli", "serve", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "host" in result.stdout.lower()
    assert "port" in result.stdout.lower()


def test_cli_serve_calls_http_main():
    """serve subcommand delegates to http.main with correct args."""
    with patch("smart_search.http.main") as mock_http:
        main(["serve", "--host", "0.0.0.0", "--port", "8080"])
        mock_http.assert_called_once_with(host="0.0.0.0", port=8080)


def test_cli_mcp_subcommand_exists():
    """smart-search mcp --help shows MCP server option."""
    result = subprocess.run(
        [sys.executable, "-m", "smart_search.cli", "mcp", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "mcp" in result.stdout.lower()


def test_cli_mcp_calls_server_main():
    """mcp subcommand delegates to server.main."""
    with patch("smart_search.server.main") as mock_mcp:
        main(["mcp"])
        mock_mcp.assert_called_once()
