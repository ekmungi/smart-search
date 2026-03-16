#!/usr/bin/env bash
# Build script for the Smart Search single installer.
#
# Steps:
#   1. Build PyInstaller one-file bundle (Python backend)
#   2. Verify the bundle works (CLI, serve, MCP)
#   3. Copy sidecar binary with Tauri platform suffix
#   4. Build Tauri NSIS installer
#
# Prerequisites:
#   - Python venv with smart-search[bundle] installed
#   - Node.js + npm (for Tauri frontend)
#   - Rust toolchain (for Tauri backend)
#
# Output: desktop/src-tauri/target/release/bundle/nsis/SmartSearch_*_x64-setup.exe

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SIDECAR_DIR="$SCRIPT_DIR/src-tauri/binaries"
EXE="$PROJECT_ROOT/dist/smart-search.exe"

# Platform triple for Tauri sidecar naming convention
PLATFORM_TRIPLE="x86_64-pc-windows-msvc"

echo "=== Smart Search Single Installer Build ==="
echo ""

# Step 1: Build PyInstaller one-file bundle
echo "[1/4] Building PyInstaller bundle (one-file mode)..."
cd "$PROJECT_ROOT"
python -m PyInstaller smart_search.spec --noconfirm --clean
echo "  -> dist/smart-search.exe"

# Step 2: Verify the bundle works before proceeding
echo "[2/4] Verifying bundle..."
VERIFY_FAILED=0

# 2a: CLI help
echo -n "  CLI help: "
if "$EXE" --help > /dev/null 2>&1; then
    echo "OK"
else
    echo "FAIL"
    VERIFY_FAILED=1
fi

# 2b: stats (tests import chain: config, data_dir, store, lancedb, sqlite)
echo -n "  stats: "
if "$EXE" stats > /dev/null 2>&1; then
    echo "OK"
else
    echo "FAIL"
    VERIFY_FAILED=1
fi

# 2c: serve (tests FastAPI, uvicorn, HTTP stack)
echo -n "  serve: "
"$EXE" serve --port 19742 > /dev/null 2>&1 &
SERVE_PID=$!
sleep 4
if kill -0 "$SERVE_PID" 2>/dev/null; then
    echo "OK"
    kill "$SERVE_PID" 2>/dev/null
    wait "$SERVE_PID" 2>/dev/null || true
else
    echo "FAIL (process died)"
    VERIFY_FAILED=1
fi

# 2d: mcp (tests FastMCP, importlib.metadata, stdio transport)
echo -n "  mcp: "
MCP_RESPONSE=$(echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' \
    | "$EXE" mcp 2>/dev/null | grep -o '"serverInfo"' || true)
if [ -n "$MCP_RESPONSE" ]; then
    echo "OK"
else
    # Check crash log for details
    CRASH_LOG="${LOCALAPPDATA:-$HOME}/smart-search/mcp_crash.log"
    if [ -f "$CRASH_LOG" ]; then
        echo "FAIL (see $CRASH_LOG)"
        cat "$CRASH_LOG"
    else
        echo "FAIL (no response, no crash log)"
    fi
    VERIFY_FAILED=1
fi

if [ "$VERIFY_FAILED" -eq 1 ]; then
    echo ""
    echo "ERROR: Bundle verification failed. Fix issues before building installer."
    exit 1
fi
echo "  All checks passed."
echo ""

# Step 3: Copy sidecar with platform suffix
echo "[3/4] Copying sidecar binary..."
mkdir -p "$SIDECAR_DIR"
cp "$EXE" "$SIDECAR_DIR/smart-search-${PLATFORM_TRIPLE}.exe"
SIDECAR_SIZE=$(du -h "$SIDECAR_DIR/smart-search-${PLATFORM_TRIPLE}.exe" | cut -f1)
echo "  -> binaries/smart-search-${PLATFORM_TRIPLE}.exe ($SIDECAR_SIZE)"

# Step 4: Build Tauri app with NSIS installer
echo "[4/4] Building Tauri NSIS installer..."
cd "$SCRIPT_DIR"
npm run build
export PATH="$HOME/.cargo/bin:$PATH"
npx tauri build

echo ""
echo "=== Build Complete ==="
echo "Installer location: desktop/src-tauri/target/release/bundle/nsis/"
ls -lh "$SCRIPT_DIR/src-tauri/target/release/bundle/nsis/"*.exe 2>/dev/null || echo "(check the nsis directory for output)"
