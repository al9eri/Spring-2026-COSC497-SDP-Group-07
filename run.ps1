# Run anything in this project without activating anything.
#
#     .\run.ps1                      what you can run
#     .\run.ps1 setup                create ~\.venvs\sdp07 and install everything
#     .\run.ps1 anomaly.fleet        same as: python -m anomaly.fleet
#     .\run.ps1 anomaly.serve --source device
#     .\run.ps1 pulse_display\make_web_assets.py
#
# There is no venv to "get into". This finds the project's interpreter and runs
# it directly, so it works from any shell and any tab, with or without conda,
# and with no Activate.ps1 and no execution policy to argue with.
#
# The macOS twin is ./run -- same words, same outcomes.

[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Args)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $HOME '.venvs\sdp07'
$Py   = Join-Path $Venv 'Scripts\python.exe'

function Find-Py312 {
  # the py launcher first: it is how a python.org install exposes a version
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    $v = & $py.Source -3.12 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
    if ($LASTEXITCODE -eq 0 -and $v -eq '3.12') { return @($py.Source, '-3.12') }
  }
  foreach ($c in @('python3.12', 'python')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $v = & $cmd.Source -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
    if ($LASTEXITCODE -eq 0 -and $v -eq '3.12') { return @($cmd.Source) }
  }
  return $null
}

function Invoke-Setup {
  $found = Find-Py312
  if (-not $found) {
    Write-Host ""
    Write-Host "Python 3.12 isn't installed, and this project needs exactly 3.12 --"
    Write-Host "tensorflow-cpu has no wheels for 3.13 or 3.14, so pip cannot resolve it."
    Write-Host ""
    Write-Host "    winget install --id Python.Python.3.12 -e"
    Write-Host ""
    Write-Host "then open a NEW terminal and run  .\run.ps1 setup  again."
    Write-Host ""
    exit 1
  }
  Write-Host ""
  Write-Host "Using $($found -join ' ')"
  Write-Host "Creating $Venv ..."
  & $found[0] @($found[1..($found.Count - 1)]) -m venv $Venv
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host "Installing dependencies (about 1 GB, a few minutes) ..."
  & $Py -m pip install --upgrade --quiet pip
  & $Py -m pip install -r (Join-Path $Repo 'baselines\requirements.txt') `
                       -r (Join-Path $Repo 'pipeline\requirements.txt')
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host ""
  Write-Host "Done. Try:  .\run.ps1 anomaly.fleet"
  Write-Host ""
}

function Show-Usage {
  Write-Host ""
  Write-Host "  .\run.ps1 <module|script.py> [args...]     no venv to activate"
  Write-Host ""
  if (Test-Path $Py) { Write-Host "  interpreter: $Py" }
  else { Write-Host "  interpreter: NOT SET UP -- run  .\run.ps1 setup  first" }
  Write-Host ""
  Write-Host "  the demo"
  Write-Host "    .\run.ps1 anomaly.fleet                  every board on the LAN -> localhost:8002"
  Write-Host "    .\run.ps1 anomaly.fleet --hotspot        ... on this machine's own hotspot"
  Write-Host "    .\run.ps1 anomaly.serve                  WESAD replay dashboard -> localhost:8001"
  Write-Host "    .\run.ps1 anomaly.serve --source device  one board over USB"
  Write-Host ""
  Write-Host "  the board"
  Write-Host "    .\run.ps1 anomaly.device_check           is the finger on properly?"
  Write-Host "    .\run.ps1 anomaly.device_source --list-ports"
  Write-Host "    .\run.ps1 anomaly.device_wifi --status"
  Write-Host "    .\run.ps1 pulse_display\make_web_assets.py"
  Write-Host ""
  Write-Host "  the experiment"
  Write-Host "    .\run.ps1 anomaly.protocol run           induced-stress session (master first)"
  Write-Host "    .\run.ps1 anomaly.protocol report --plot"
  Write-Host ""
  Write-Host "  housekeeping"
  Write-Host "    .\run.ps1 setup                          build the venv and install everything"
  Write-Host "    .\run.ps1 doctor                         what is installed, and where"
  Write-Host "    .\run.ps1 anomaly.db                     the store"
  Write-Host ""
  Write-Host "  or build Pulse Control once (launcher\build_exe.bat) and press buttons instead."
  Write-Host "  full reference: COMMANDS-windows.md"
  Write-Host ""
}

function Invoke-Doctor {
  Write-Host ""
  Write-Host "  repo        $Repo"
  if (Test-Path $Py) {
    Write-Host "  interpreter $Py"
    Write-Host "  version     $(& $Py -c 'import sys; print(sys.version.split()[0])')"
    Write-Host ""
    $probe = @'
import importlib
for m in ("numpy", "scipy", "pandas", "sklearn", "matplotlib",
          "tensorflow", "fastapi", "uvicorn", "websockets", "serial", "tkinter"):
    try:
        importlib.import_module(m)
        print("  ok       %s" % m)
    except Exception as e:
        print("  MISSING  %s  (%s)" % (m, type(e).__name__))
'@
    # TF prints a CPU-features banner on import; not an error, and it buries the
    # one line that matters here.
    $env:TF_CPP_MIN_LOG_LEVEL = '2'
    $probe | & $Py -
    Remove-Item Env:TF_CPP_MIN_LOG_LEVEL -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "  tkinter is only used by Pulse Control's window. Everything else must say ok."
  }
  else {
    Write-Host "  interpreter NOT SET UP"
    Write-Host ""
    Write-Host "  run:  .\run.ps1 setup"
  }
  Write-Host ""
}

if (-not $Args -or $Args.Count -eq 0) { Show-Usage; exit 0 }

switch ($Args[0]) {
  'setup'   { Invoke-Setup; exit 0 }
  'doctor'  { Invoke-Doctor; exit 0 }
  'help'    { Show-Usage; exit 0 }
  '-h'      { Show-Usage; exit 0 }
  '--help'  { Show-Usage; exit 0 }
}

if (-not (Test-Path $Py)) {
  Write-Host ""
  Write-Host "The project's virtualenv isn't set up yet ($Venv)."
  Write-Host ""
  Write-Host "    .\run.ps1 setup"
  Write-Host ""
  Write-Host "does it for you (a few minutes, about 1 GB)."
  Write-Host ""
  exit 1
}

Set-Location $Repo
$rest = @()
if ($Args.Count -gt 1) { $rest = $Args[1..($Args.Count - 1)] }
if ($Args[0] -like '*.py' -or $Args[0] -like '-*') { & $Py @Args }
else { & $Py -m $Args[0] @rest }
exit $LASTEXITCODE
