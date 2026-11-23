#!/bin/bash
# Builds Thalamus.app and installs it in /Applications. Run again after editing main.swift.
set -e
cd "$(dirname "$0")"
APP=build/Thalamus.app
rm -rf build && mkdir -p $APP/Contents/MacOS $APP/Contents/Resources
python3 - <<PY
import re
b=open("logo/thalamus-dock-glyph.svg").read()
b=re.sub(r"^<svg[^>]*>|</svg>\s*$","",b.strip())
open("WelcomeLogo.swift","w").write('let glyphBody = """\n'+b+'\n"""\n')
PY
swiftc -O main.swift Welcome.swift WelcomeLogo.swift -o $APP/Contents/MacOS/Thalamus -framework Cocoa -framework WebKit
cat > $APP/Contents/Info.plist <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Thalamus</string>
<key>CFBundleDisplayName</key><string>Thalamus</string>
<key>CFBundleIdentifier</key><string>com.morguewhite.thalamus</string>
<key>CFBundleExecutable</key><string>Thalamus</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PL
[ -f logo/Thalamus.icns ] && cp logo/Thalamus.icns Thalamus.icns
[ -f Thalamus.icns ] && cp Thalamus.icns $APP/Contents/Resources/ && /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string Thalamus" $APP/Contents/Info.plist
xattr -cr $APP; codesign --force --sign - $APP
rm -rf /Applications/Thalamus.app && cp -R $APP /Applications/
echo "installed /Applications/Thalamus.app"
