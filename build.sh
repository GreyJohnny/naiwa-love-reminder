#!/bin/bash
# 奶蛙的爱意提醒物语 - 一键构建脚本
# 需要 macOS 14.0+ 和 Xcode Command Line Tools（xcode-select --install）
set -e

cd "$(dirname "$0")"

APP="奶蛙的爱意提醒物语.app"
BIN="naiwa"
BUILD_DIR="/tmp/naiwa_build"
CACHE_DIR="/tmp/naiwa_swift_module_cache"

echo "🔨 编译 Swift 源码..."
mkdir -p "$BUILD_DIR"
swiftc -O -parse-as-library \
  -o "$BUILD_DIR/$BIN" app/NaiwaApp.swift \
  -target arm64-apple-macosx14.0 \
  -module-cache-path "$CACHE_DIR"

echo "📦 组装 App 包..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD_DIR/$BIN" "$APP/Contents/MacOS/$BIN"
cp assets/laugh*.png assets/naiwa_laugh.mp3 "$APP/Contents/Resources/"

echo "🎨 生成图标..."
ICONSET="/tmp/NaiwaIcon.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s assets/laugh2.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1
done
sips -z 32 32   assets/laugh2.png --out "$ICONSET/icon_16x16@2x.png"   >/dev/null 2>&1
sips -z 64 64   assets/laugh2.png --out "$ICONSET/icon_32x32@2x.png"   >/dev/null 2>&1
sips -z 256 256 assets/laugh2.png --out "$ICONSET/icon_128x128@2x.png" >/dev/null 2>&1
sips -z 512 512 assets/laugh2.png --out "$ICONSET/icon_256x256@2x.png" >/dev/null 2>&1
sips -z 1024 1024 assets/laugh2.png --out "$ICONSET/icon_512x512@2x.png" >/dev/null 2>&1
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
    <key>CFBundleDisplayName</key><string>奶蛙的爱意提醒物语</string>
    <key>CFBundleExecutable</key><string>naiwa</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundleIdentifier</key><string>com.naiwa.reminder</string>
    <key>CFBundleName</key><string>奶蛙的爱意提醒物语</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

echo "✅ 构建完成：$APP"
echo "   双击即可运行（首次打开如提示无法验证开发者，请右键→打开）"
