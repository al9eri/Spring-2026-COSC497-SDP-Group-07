@echo off
rem Build "Pulse Control.exe" into the repo root. Double-click this file.
rem
rem The exe is only the launcher window: every button runs the real code with the
rem project's virtualenv, so pulling new code never needs a rebuild. Rebuild only
rem when launcher\pulse_control.py itself changes.
rem
rem PyInstaller goes into a separate build environment, not the project's venv.

setlocal
set "HERE=%~dp0"
set "BASE=%USERPROFILE%\.venvs\sdp07\Scripts\python.exe"
set "BUILD=%LOCALAPPDATA%\pulse_control_build"
set "EXE=%HERE%..\Pulse Control.exe"

rem Already built and newer than the app's code? Nothing to do -- just use it.
rem (build_exe.bat force rebuilds anyway.)
if /i not "%~1"=="force" if exist "%EXE%" (
  powershell -NoProfile -Command "if ((Get-Item -LiteralPath '%EXE%').LastWriteTime -ge (Get-Item -LiteralPath '%HERE%pulse_control.py').LastWriteTime) { exit 0 } else { exit 1 }"
  if not errorlevel 1 (
    echo "Pulse Control.exe" is already up to date - just double-click it.
    echo ^(to rebuild anyway: build_exe.bat force^)
    pause
    exit /b 0
  )
)

if not exist "%BASE%" (
  echo Can't find the project's Python at %BASE%
  echo Set up the virtualenv first: COMMANDS.md, section 1.
  pause
  exit /b 1
)

if not exist "%BUILD%\venv\Scripts\python.exe" (
  echo Creating the build environment...
  "%BASE%" -m venv "%BUILD%\venv" || goto :fail
)
echo Installing PyInstaller into the build environment...
"%BUILD%\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip pyinstaller || goto :fail

echo Building...
"%BUILD%\venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Pulse Control" ^
  --distpath "%HERE%.." ^
  --workpath "%BUILD%\work" ^
  --specpath "%BUILD%" ^
  "%HERE%pulse_control.py" || goto :fail

echo.
echo Done: "Pulse Control.exe" is in the project folder. Double-click it.
pause
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
