#!/bin/bash
# Freeze a STANDALONE "Pulse Control (standalone).app" into the repo root: a
# self-contained bundle with its own Python and Tk inside, for a Mac that has
# neither.
#
#     bash launcher/build_app.sh          # build if it is out of date
#     bash launcher/build_app.sh force    # rebuild anyway
#
# Most people do not need this. "Pulse Control.app" -- the committed wrapper
# from launcher/make_app.sh -- is already in the repo, opens faster, and never
# goes stale. Reach for this one only if make_app.sh's bundle tells you no
# Python on the Mac has Tk.
#
# The .app is only the launcher window: every button runs the real code with
# the project's virtualenv, so pulling new code never needs a rebuild. Rebuild
# only when launcher/pulse_control.py itself changes.
#
# PyInstaller goes into a separate build environment, not the project's venv.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
# PULSE_PYTHON overrides it, to match the app's own Advanced > Choose Python
BASE="${PULSE_PYTHON:-$HOME/.venvs/sdp07/bin/python}"
BUILD="$HOME/Library/Caches/pulse_control_build"
APP="$REPO/Pulse Control (standalone).app"

fail() { echo; echo "Build failed - $1"; exit 1; }

# Already built and newer than the app's code? Nothing to do -- just use it.
if [ "${1:-}" != "force" ] && [ -d "$APP" ]; then
  if [ ! "$HERE/pulse_control.py" -nt "$APP" ]; then
    echo "\"Pulse Control (standalone).app\" is already up to date."
    echo "(to rebuild anyway: bash launcher/build_app.sh force)"
    exit 0
  fi
fi

if [ ! -x "$BASE" ]; then
  echo "Can't find the project's Python at $BASE"
  echo "Set up the virtualenv first: COMMANDS-macos.md, section 1."
  exit 1
fi

# Tk is a separate Homebrew formula, and a venv without it builds an app that
# dies on launch with a traceback no user can act on. Catch it here instead.
if ! "$BASE" -c "import tkinter" >/dev/null 2>&1; then
  echo "This Python has no Tk, so the app would not open:"
  echo
  echo "    brew install python-tk@3.12"
  echo
  echo "then run this script again. See COMMANDS-macos.md, section 1."
  exit 1
fi

if [ ! -x "$BUILD/venv/bin/python" ]; then
  echo "Creating the build environment..."
  "$BASE" -m venv "$BUILD/venv" || fail "could not create $BUILD/venv"
fi
echo "Installing PyInstaller into the build environment..."
"$BUILD/venv/bin/python" -m pip install --quiet --upgrade pip pyinstaller \
  || fail "could not install PyInstaller"

echo "Building..."
# Not --onefile: on macOS the .app bundle IS the single draggable thing, and a
# onedir bundle starts in well under a second instead of unpacking itself into
# /tmp on every launch. We build into the cache and copy only the .app over, so
# the repo root never collects PyInstaller's loose onedir folder beside it.
rm -rf "$BUILD/dist"
"$BUILD/venv/bin/python" -m PyInstaller --noconfirm --clean --windowed \
  --name "Pulse Control" \
  --osx-bundle-identifier "edu.ku.cosc497.sdp07.pulsecontrol" \
  --distpath "$BUILD/dist" \
  --workpath "$BUILD/work" \
  --specpath "$BUILD" \
  "$HERE/pulse_control.py" || fail "see the messages above."

[ -d "$BUILD/dist/Pulse Control.app" ] || fail "PyInstaller produced no .app bundle."
rm -rf "$APP"
cp -R "$BUILD/dist/Pulse Control.app" "$APP" || fail "could not copy the bundle into $REPO"
ICNS="$HERE/icon/PulseControl.icns"
[ -f "$ICNS" ] && cp "$ICNS" "$APP/Contents/Resources/icon-windowed.icns" 2>/dev/null
# A locally built bundle is not quarantined, but clear it anyway in case the
# repo itself arrived as a download -- otherwise Gatekeeper refuses the app
# with "damaged", which it is not.
xattr -dr com.apple.quarantine "$APP" 2>/dev/null

echo
echo "Done: \"Pulse Control (standalone).app\" is in the project folder."
echo "(unsigned, so the first launch may need right-click > Open)"
