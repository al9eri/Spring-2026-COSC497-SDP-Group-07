#!/bin/bash
# Build "Pulse Control.app" in the repo root -- the double-click icon.
#
#     bash launcher/make_app.sh
#
# This bundle is a ~160 KB wrapper, not a frozen copy of the project: it finds a
# Python with Tk and runs launcher/pulse_control.py from the repo it sits in. So
# it opens in well under a second, and `git pull` changes what the buttons do
# with no rebuild -- there is nothing in here to go stale. It is committed, so a
# fresh clone already has the icon.
#
# Re-run this only if you change the launch script or the icon below.
# For a Mac with no usable Python at all, launcher/build_app.sh freezes a
# standalone bundle with PyInstaller instead.

set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
APP="$REPO/Pulse Control.app"
ICNS="$HERE/icon/PulseControl.icns"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

printf 'APPL????' > "$APP/Contents/PkgInfo"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>                  <string>Pulse Control</string>
  <key>CFBundleDisplayName</key>           <string>Pulse Control</string>
  <key>CFBundleExecutable</key>            <string>pulse-control</string>
  <key>CFBundleIconFile</key>              <string>PulseControl</string>
  <key>CFBundleIdentifier</key>            <string>edu.ku.cosc497.sdp07.pulsecontrol</string>
  <key>CFBundleInfoDictionaryVersion</key> <string>6.0</string>
  <key>CFBundlePackageType</key>           <string>APPL</string>
  <key>CFBundleShortVersionString</key>    <string>1.0</string>
  <key>CFBundleVersion</key>               <string>1.0</string>
  <key>LSApplicationCategoryType</key>     <string>public.app-category.healthcare-fitness</string>
  <key>LSMinimumSystemVersion</key>        <string>11.0</string>
  <key>NSHighResolutionCapable</key>       <true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/pulse-control" <<'LAUNCH'
#!/bin/bash
# Pulse Control's launcher. Finder runs this with cwd=/ and almost no PATH, so
# everything here is absolute.
#
# Picks a Python that can open a window and hands it launcher/pulse_control.py.
# That is a LOWER bar than running the project: the app only draws the window
# and shells out to the project's own virtualenv for every button, which it
# finds by itself. So a Python that could never import tensorflow is still a
# perfectly good host.
#
# "Can open a window" means **Tk 8.6 or newer**, not merely that tkinter
# imports. macOS still bundles Tk 8.5.9 -- a 2010 build Apple has deprecated
# for years -- and under it ttk.PanedWindow silently never lays out: every pane
# stays 1x1 and unmapped, and Pulse Control opens as an empty grey rectangle
# with no error anywhere. Checking the version is the whole difference between
# a working app and that.

BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
REPO="$(dirname "$BUNDLE")"
APP="$REPO/launcher/pulse_control.py"

die() {
  /usr/bin/osascript -e "display dialog \"$1\" with title \"Pulse Control\" \
    buttons {\"OK\"} default button 1 with icon stop" >/dev/null 2>&1
  exit 1
}

[ -f "$APP" ] || die "Pulse Control must stay inside the project folder.\n\nIt looked for:\n$APP\n\nMove the app back next to the anomaly/ and launcher/ folders."

# Apple's /usr/bin/python3 is deliberately NOT in this list: it is the one
# Python on a Mac whose Tk is too old to draw this window (see above).
CANDIDATES=(
  "$HOME/.venvs/sdp07/bin/python"
  "$HOME/miniforge3/bin/python3"
  "$HOME/anaconda3/bin/python3"
  "$HOME/miniconda3/bin/python3"
  /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3
  /usr/local/bin/python3.12 /usr/local/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3
)

for PY in "${CANDIDATES[@]}"; do
  [ -x "$PY" ] || continue
  "$PY" -c 'import sys, tkinter; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)' \
    >/dev/null 2>&1 || continue
  cd "$REPO" || die "Could not open $REPO"
  exec "$PY" "$APP" "$@"
done

die "Pulse Control needs a Python with Tk 8.6 or newer, and none on this Mac has one.\n\nmacOS's own python3 does not count: it ships Tk 8.5 from 2010, which draws this app as an empty window.\n\nFix it with:\n    brew install python@3.12 python-tk@3.12\n\nSee COMMANDS-macos.md, section 1."
LAUNCH

chmod +x "$APP/Contents/MacOS/pulse-control"

if [ -f "$ICNS" ]; then
  cp "$ICNS" "$APP/Contents/Resources/PulseControl.icns"
else
  echo "warning: $ICNS is missing, so the app gets the generic icon."
  echo "         rebuild it with: python launcher/icon/make_icon.py"
fi

# Finder caches the icon per bundle; touching the directory makes it re-read.
touch "$APP"
echo "Built \"Pulse Control.app\" ($(du -sh "$APP" | cut -f1)) in the project folder."
echo "Double-click it."
