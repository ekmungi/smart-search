#!/usr/bin/env python3
# install.py -- Cross-platform installer for smart-search MCP server.
# Stdlib only. No external dependencies required.

"""Automated installer for smart-search.

Discovers Python, creates a venv, installs dependencies, and registers
the MCP server with Claude Code and/or Claude Desktop.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# --- Constants ---

PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv"
SERVER_MODULE = "smart_search.server"
MCP_SERVER_NAME = "smart-search"

# Platform-specific Obsidian config paths
OBSIDIAN_CONFIG_PATHS = {
    "Windows": Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json",
    "Darwin": Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json",
    "Linux": Path.home() / ".config" / "obsidian" / "obsidian.json",
}

# Claude Desktop config paths
CLAUDE_DESKTOP_PATHS = {
    "Windows": Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json",
    "Darwin": Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    "Linux": Path.home() / ".config" / "Claude" / "claude_desktop_config.json",
}


# --- Python Discovery ---

def find_python():
    """Discover a Python 3.11+ interpreter.

    Checks PATH first, then probes common installation locations
    on Windows (WinPython, LocalAppData, pyenv) and Unix (pyenv, conda).

    Returns:
        Absolute path to a suitable Python interpreter, or None.
    """
    candidates = ["python3", "python"]

    # Windows-specific search locations
    if platform.system() == "Windows":
        local_app = Path(os.environ.get("LOCALAPPDATA", ""))
        user_profile = Path(os.environ.get("USERPROFILE", ""))
        extra_dirs = [
            local_app / "Programs" / "Python",
            user_profile / "AppData" / "Local" / "Programs" / "Python",
            user_profile / ".pyenv" / "pyenv-win" / "versions",
        ]
        for base in extra_dirs:
            if base.exists():
                for child in sorted(base.iterdir(), reverse=True):
                    exe = child / "python.exe"
                    if exe.exists():
                        candidates.append(str(exe))
    else:
        # Unix: pyenv, conda
        pyenv_root = Path(os.environ.get("PYENV_ROOT", str(Path.home() / ".pyenv")))
        versions_dir = pyenv_root / "versions"
        if versions_dir.exists():
            for child in sorted(versions_dir.iterdir(), reverse=True):
                exe = child / "bin" / "python3"
                if exe.exists():
                    candidates.append(str(exe))

    for candidate in candidates:
        path = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
        if path and _check_python_version(path):
            return path

    return None


def _check_python_version(python_path):
    """Check if a Python interpreter is version 3.11 or higher.

    Args:
        python_path: Absolute path to the Python executable.

    Returns:
        True if the version is 3.11+.
    """
    try:
        output = subprocess.check_output(
            [python_path, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            timeout=10,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        major, minor = output.split(".")
        return int(major) >= 3 and int(minor) >= 11
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError):
        return False


# --- Venv and Dependencies ---

def create_venv(python_path):
    """Create a virtual environment in the project directory.

    Args:
        python_path: Path to the Python interpreter to use.

    Returns:
        Path to the venv's Python executable.
    """
    if VENV_DIR.exists():
        print(f"  Venv already exists at {VENV_DIR}")
    else:
        print(f"  Creating venv at {VENV_DIR}...")
        subprocess.check_call([python_path, "-m", "venv", str(VENV_DIR)])

    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def install_dependencies(venv_python):
    """Install project dependencies into the venv.

    Tries uv first (faster), falls back to pip.

    Args:
        venv_python: Path to the venv's Python executable.
    """
    uv_path = shutil.which("uv")
    try:
        if uv_path:
            print("  Installing with uv (fast)...")
            subprocess.check_call(
                [uv_path, "pip", "install", "-e", str(PROJECT_DIR)],
                env={**os.environ, "VIRTUAL_ENV": str(VENV_DIR)},
            )
        else:
            print("  Installing with pip...")
            subprocess.check_call(
                [str(venv_python), "-m", "pip", "install", "-e", str(PROJECT_DIR)],
            )
    except subprocess.CalledProcessError as exc:
        print(f"\n  ERROR: Dependency installation failed (exit code {exc.returncode}).")
        print("  Common fixes for enterprise environments:")
        print("    - Proxy: set HTTP_PROXY and HTTPS_PROXY environment variables")
        print("    - SSL certs: pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e .")
        print(f"    - Manual: {venv_python} -m pip install -e {PROJECT_DIR}")
        sys.exit(1)


# --- Vault Discovery ---

def discover_obsidian_vaults():
    """Read Obsidian vault paths from obsidian.json (opt-in).

    Returns:
        List of vault paths found, or empty list.
    """
    config_path = OBSIDIAN_CONFIG_PATHS.get(platform.system())
    if not config_path or not config_path.exists():
        print("  Obsidian config not found. Specify vaults with --watch.")
        return []

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        vaults = data.get("vaults", {})
        paths = []
        for vault_info in vaults.values():
            vault_path = vault_info.get("path", "")
            if vault_path and Path(vault_path).exists():
                paths.append(vault_path)
        return paths
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        print(f"  Warning: Could not parse obsidian.json -- {exc}")
        return []


def prompt_vault_selection(vaults):
    """Present discovered vaults for user selection.

    Args:
        vaults: List of discovered vault paths.

    Returns:
        List of selected vault paths.
    """
    print("\n  Found Obsidian vaults:")
    for i, vault in enumerate(vaults, 1):
        print(f"    [{i}] {vault}")
    print(f"    [{len(vaults) + 1}] Enter path manually")
    print(f"    [{len(vaults) + 2}] Skip (no watch directories)")

    choice = input(f"\n  Which vaults to index? (comma-separated, e.g. 1,2): ").strip()
    selected = []
    for part in choice.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        idx = int(part)
        if 1 <= idx <= len(vaults):
            selected.append(vaults[idx - 1])
        elif idx == len(vaults) + 1:
            manual = input("  Enter vault path: ").strip()
            if manual and Path(manual).exists():
                selected.append(manual)
            else:
                print(f"  Warning: Path not found -- '{manual}'")

    return selected


# --- Claude Code Registration ---

def register_claude_code(venv_python, watch_dirs, embedding_dim):
    """Register smart-search as a user-level MCP server in Claude Code.

    Args:
        venv_python: Path to the venv's Python executable.
        watch_dirs: List of directories to watch.
        embedding_dim: Embedding dimensions to use.

    Returns:
        True if registration succeeded.
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        print("  WARNING: 'claude' not found on PATH. Skipping Claude Code registration.")
        print("  Manual registration:")
        print(f'    claude mcp add -s user {MCP_SERVER_NAME} -- {venv_python} -m {SERVER_MODULE}')
        return False

    cmd = [
        claude_path, "mcp", "add",
        "-s", "user",
        "--transport", "stdio",
    ]

    # Add environment variables
    watch_json = json.dumps([str(Path(d).resolve()) for d in watch_dirs])
    cmd.extend(["-e", f"SMART_SEARCH_WATCH_DIRECTORIES={watch_json}"])
    cmd.extend(["-e", f"SMART_SEARCH_EMBEDDING_DIMENSIONS={embedding_dim}"])

    cmd.extend([
        MCP_SERVER_NAME,
        "--",
        str(venv_python), "-m", SERVER_MODULE,
    ])

    try:
        subprocess.check_call(cmd)
        print(f"  Registered '{MCP_SERVER_NAME}' with Claude Code (user-level).")
        return True
    except subprocess.CalledProcessError:
        print("  ERROR: Claude Code registration failed.")
        return False


# --- Claude Desktop Registration ---

def register_claude_desktop(venv_python, watch_dirs, embedding_dim):
    """Register smart-search in Claude Desktop's config file.

    Merges the server entry into the existing config without
    overwriting other servers.

    Args:
        venv_python: Path to the venv's Python executable.
        watch_dirs: List of directories to watch.
        embedding_dim: Embedding dimensions to use.

    Returns:
        True if registration succeeded.
    """
    config_path = CLAUDE_DESKTOP_PATHS.get(platform.system())
    if not config_path:
        print("  WARNING: Unsupported platform for Claude Desktop.")
        return False

    watch_json = json.dumps([str(Path(d).resolve()) for d in watch_dirs])

    server_entry = {
        "command": str(venv_python),
        "args": ["-m", SERVER_MODULE],
        "cwd": str(PROJECT_DIR),
        "env": {
            "SMART_SEARCH_WATCH_DIRECTORIES": watch_json,
            "SMART_SEARCH_EMBEDDING_DIMENSIONS": str(embedding_dim),
        },
    }

    # Read existing config or start fresh
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    servers = config.setdefault("mcpServers", {})
    servers[MCP_SERVER_NAME] = server_entry

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"  Registered '{MCP_SERVER_NAME}' in Claude Desktop config.")
    print(f"  Config: {config_path}")
    return True


# --- Uninstall ---

def uninstall():
    """Deregister smart-search from Claude Code and Desktop."""
    print("\nUninstalling smart-search...")

    # Claude Code
    claude_path = shutil.which("claude")
    if claude_path:
        try:
            subprocess.check_call(
                [claude_path, "mcp", "remove", "-s", "user", MCP_SERVER_NAME]
            )
            print("  Removed from Claude Code.")
        except subprocess.CalledProcessError:
            print("  Not registered in Claude Code (or removal failed).")
    else:
        print("  'claude' not on PATH -- skip Claude Code removal.")

    # Claude Desktop
    config_path = CLAUDE_DESKTOP_PATHS.get(platform.system())
    if config_path and config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            servers = config.get("mcpServers", {})
            if MCP_SERVER_NAME in servers:
                del servers[MCP_SERVER_NAME]
                config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
                print("  Removed from Claude Desktop config.")
            else:
                print("  Not registered in Claude Desktop.")
        except (json.JSONDecodeError, OSError):
            print("  Could not read Claude Desktop config.")

    print("Done.")


# --- Main ---

def main():
    """Entry point for the installer."""
    parser = argparse.ArgumentParser(
        description="Install and register smart-search MCP server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python install.py --watch "C:/Obsidian/Vault"\n'
            '  python install.py --watch "/home/user/notes" --watch "/home/user/docs"\n'
            "  python install.py --discover-vaults\n"
            "  python install.py --claude-desktop\n"
            "  python install.py --uninstall\n"
        ),
    )
    parser.add_argument(
        "--watch", action="append", default=[], metavar="PATH",
        help="Directory to index (repeatable)",
    )
    parser.add_argument(
        "--discover-vaults", action="store_true",
        help="Auto-detect Obsidian vaults from obsidian.json",
    )
    parser.add_argument(
        "--claude-desktop", action="store_true",
        help="Also register with Claude Desktop",
    )
    parser.add_argument(
        "--python", metavar="PATH", default=None,
        help="Explicit Python path (skip auto-discovery)",
    )
    parser.add_argument(
        "--embedding-dim", type=int, default=256,
        help="Embedding dimensions (default: 256)",
    )
    parser.add_argument(
        "--skip-venv", action="store_true",
        help="Use current Python instead of creating venv",
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="Deregister from Claude Code and Desktop",
    )
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
        return

    print("smart-search installer")
    print("=" * 40)

    # Step 1: Find Python
    print("\n[1/5] Finding Python...")
    if args.python:
        python_path = args.python
        if not _check_python_version(python_path):
            print(f"  ERROR: {python_path} is not Python 3.11+")
            sys.exit(1)
        print(f"  Using: {python_path}")
    else:
        python_path = find_python()
        if not python_path:
            print("  ERROR: Python 3.11+ not found.")
            print("  Install Python 3.11+ or use --python /path/to/python")
            sys.exit(1)
        print(f"  Found: {python_path}")

    # Step 2: Create venv
    print("\n[2/5] Setting up virtual environment...")
    if args.skip_venv:
        venv_python = Path(python_path)
        print("  Skipping venv (--skip-venv)")
    else:
        venv_python = create_venv(python_path)
    print(f"  Python: {venv_python}")

    # Step 3: Install dependencies
    print("\n[3/5] Installing dependencies...")
    install_dependencies(venv_python)
    print("  Done.")

    # Step 4: Configure watch directories
    print("\n[4/5] Configuring watch directories...")
    watch_dirs = list(args.watch)
    if args.discover_vaults:
        discovered = discover_obsidian_vaults()
        if discovered:
            selected = prompt_vault_selection(discovered)
            watch_dirs.extend(selected)

    if not watch_dirs:
        print("  No watch directories specified.")
        manual = input("  Enter a directory path to watch (or press Enter to skip): ").strip()
        if manual and Path(manual).exists():
            watch_dirs.append(manual)
        elif manual:
            print(f"  Warning: Path not found -- '{manual}'")

    if watch_dirs:
        for d in watch_dirs:
            print(f"  Watching: {d}")
    else:
        print("  No directories configured. Add later via SMART_SEARCH_WATCH_DIRECTORIES env var.")

    # Step 5: Register with Claude
    print("\n[5/5] Registering MCP server...")
    register_claude_code(venv_python, watch_dirs, args.embedding_dim)

    if args.claude_desktop:
        register_claude_desktop(venv_python, watch_dirs, args.embedding_dim)

    # Persist watch directories to config.json
    if watch_dirs:
        from smart_search.data_dir import get_data_dir as _get_data_dir
        from smart_search.config_manager import ConfigManager as _CM

        data_dir = _get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        cm_inst = _CM(data_dir)
        for d in watch_dirs:
            cm_inst.add_watch_dir(d)
        print(f"\n  Config saved to: {cm_inst.config_path}")

    # Summary
    print("\n" + "=" * 40)
    print("Installation complete!")
    print()
    print("Verify with:")
    print("  claude --mcp-debug")
    print()
    if watch_dirs:
        print("Configured directories:")
        for d in watch_dirs:
            print(f"  {d}")
    print()
    print("Data directory:")
    from smart_search.data_dir import get_data_dir as _gdd
    print(f"  {_gdd()}")
    print()
    print("MCP tools available:")
    print("  knowledge_search       -- Semantic search across indexed files")
    print("  knowledge_stats        -- Index health check")
    print("  knowledge_ingest       -- Trigger indexing of files/folders")
    print("  knowledge_add_folder   -- Add a watch directory at runtime")
    print("  knowledge_remove_folder-- Remove a watch directory")
    print("  knowledge_list_folders -- List watched directories")
    print("  knowledge_list_files   -- List all indexed files")
    print("  find_related           -- Find notes similar to a given note")
    print("  read_note              -- Read note content by path")
    print()
    print("CLI commands (after activating venv):")
    print("  smart-search stats         -- Show index statistics")
    print("  smart-search config show   -- Show configuration")
    print("  smart-search watch list    -- List watched directories")
    print("  smart-search search <q>    -- Search the knowledge base")
    print()
    print("To uninstall:")
    print("  python install.py --uninstall")


if __name__ == "__main__":
    main()
