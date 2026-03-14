# Entry point for `python -m smart_search` and PyInstaller bundle.
#
# Routes to the CLI dispatcher which handles all modes:
# serve (HTTP), mcp (MCP stdio), and all CLI subcommands.

from smart_search.cli import main

main()
