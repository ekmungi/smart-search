#!/usr/bin/env bash
# Build all installer variants for Smart Search.
#
# Produces:
#   - NSIS setup exe (user/all-users choice dialog)
#   - MSI per-user installer (no admin required)
#   - MSI per-machine installer (requires admin, for enterprise deployment)

set -e

BUNDLE_DIR="src-tauri/target/release/bundle"

echo "=== Building NSIS + MSI (per-machine) ==="
npx tauri build

# Save the per-machine MSI
if [ -f "$BUNDLE_DIR/msi/"*"_en-US.msi" ]; then
    for f in "$BUNDLE_DIR/msi/"*"_en-US.msi"; do
        SYSTEM_MSI="${f/_en-US.msi/_system_en-US.msi}"
        cp "$f" "$SYSTEM_MSI"
        echo "Saved system MSI: $SYSTEM_MSI"
    done
fi

echo ""
echo "=== Building MSI (per-user) ==="
npx tauri build -b msi -c '{"bundle":{"windows":{"wix":{"installScope":"perUser"}}}}'

# Rename the per-user MSI
if [ -f "$BUNDLE_DIR/msi/"*"_en-US.msi" ]; then
    for f in "$BUNDLE_DIR/msi/"*"_en-US.msi"; do
        USER_MSI="${f/_en-US.msi/_user_en-US.msi}"
        cp "$f" "$USER_MSI"
        echo "Saved user MSI: $USER_MSI"
    done
fi

echo ""
echo "=== Build complete ==="
echo "Installers:"
echo "  NSIS (choice):  $BUNDLE_DIR/nsis/"*"-setup.exe"
echo "  MSI (per-user): $BUNDLE_DIR/msi/"*"_user_en-US.msi"
echo "  MSI (system):   $BUNDLE_DIR/msi/"*"_system_en-US.msi"
