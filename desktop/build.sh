#!/usr/bin/env bash
# Build script for the Smart Search single installer.
#
# Steps:
#   1. Build PyInstaller one-file bundle (Python backend)
#   2. Copy sidecar binary with Tauri platform suffix
#   3. Build Tauri NSIS installer
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

# Platform triple for Tauri sidecar naming convention
PLATFORM_TRIPLE="x86_64-pc-windows-msvc"

echo "=== Smart Search Single Installer Build ==="
echo ""

# Step 1: Build PyInstaller one-file bundle
echo "[1/3] Building PyInstaller bundle (one-file mode)..."
cd "$PROJECT_ROOT"
python -m PyInstaller smart_search.spec --noconfirm --clean
echo "  -> dist/smart-search.exe"

# Step 2: Copy sidecar with platform suffix
echo "[2/3] Copying sidecar binary..."
mkdir -p "$SIDECAR_DIR"
cp "$PROJECT_ROOT/dist/smart-search.exe" \
   "$SIDECAR_DIR/smart-search-${PLATFORM_TRIPLE}.exe"
SIDECAR_SIZE=$(du -h "$SIDECAR_DIR/smart-search-${PLATFORM_TRIPLE}.exe" | cut -f1)
echo "  -> binaries/smart-search-${PLATFORM_TRIPLE}.exe ($SIDECAR_SIZE)"

# Step 3: Build Tauri app with NSIS installer
echo "[3/3] Building Tauri NSIS installer..."
cd "$SCRIPT_DIR"
npm run build
export PATH="$HOME/.cargo/bin:$PATH"
npx tauri build

echo ""
echo "=== Build Complete ==="
echo "Installer location: desktop/src-tauri/target/release/bundle/nsis/"
ls -lh "$SCRIPT_DIR/src-tauri/target/release/bundle/nsis/"*.exe 2>/dev/null || echo "(check the nsis directory for output)"
