#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
swift build -c release
binary_dir=$(swift build -c release --show-bin-path)
app="build/Vault Approval.app"
mkdir -p "$app/Contents/MacOS"
cp "$binary_dir/VaultApproval" "$app/Contents/MacOS/VaultApproval"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.nikita.VaultApproval</string>
<key>CFBundleName</key><string>Vault Approval</string>
<key>CFBundleExecutable</key><string>VaultApproval</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - --options runtime "$app"
printf '%s\n' "Built $PWD/$app (local ad-hoc signature; not notarized)."
